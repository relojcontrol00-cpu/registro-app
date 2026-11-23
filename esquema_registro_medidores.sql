PRAGMA foreign_keys = ON;
PRAGMA user_version = 2;

-- 1. Instalaciones
CREATE TABLE IF NOT EXISTS instalaciones (
    id INTEGER PRIMARY KEY,
    codigo TEXT NOT NULL COLLATE NOCASE UNIQUE,
    nombre TEXT NOT NULL,
    activa INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0, 1)),
    creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Registro de importaciones
CREATE TABLE IF NOT EXISTS importaciones (
    id INTEGER PRIMARY KEY,
    archivo TEXT NOT NULL,
    hoja TEXT NOT NULL,
    fecha_importacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    filas_origen INTEGER NOT NULL DEFAULT 0,
    notas TEXT
);

-- 3. Catálogo de puntos de medición
CREATE TABLE IF NOT EXISTS puntos_medicion (
    id INTEGER PRIMARY KEY,
    instalacion_id INTEGER NOT NULL REFERENCES instalaciones(id) ON DELETE RESTRICT,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('medidor', 'remarcador', 'nivel', 'registro_texto')),
    magnitud TEXT NOT NULL,
    unidad TEXT,
    estado_unidad TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado_unidad IN ('confirmada', 'inferida', 'pendiente')),
    modo_lectura TEXT NOT NULL CHECK (modo_lectura IN ('acumulativa', 'nivel', 'texto')),
    punto_padre_id INTEGER REFERENCES puntos_medicion(id) ON DELETE RESTRICT,
    activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    notas TEXT,
    UNIQUE (instalacion_id, codigo),
    CHECK (punto_padre_id IS NULL OR punto_padre_id <> id)
);

-- 4. Lecturas puras registradas día a día
CREATE TABLE IF NOT EXISTS lecturas (
    id INTEGER PRIMARY KEY,
    punto_medicion_id INTEGER NOT NULL REFERENCES puntos_medicion(id) ON DELETE RESTRICT,
    fecha TEXT NOT NULL CHECK (fecha GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    valor_numerico REAL,
    valor_texto TEXT,
    valor_original TEXT NOT NULL,
    clase TEXT NOT NULL DEFAULT 'lectura' CHECK (clase IN ('lectura', 'ajuste_manual')),
    importacion_id INTEGER REFERENCES importaciones(id) ON DELETE RESTRICT,
    hoja_origen TEXT,
    fila_origen INTEGER,
    CHECK ((valor_numerico IS NOT NULL AND valor_texto IS NULL)
        OR (valor_numerico IS NULL AND valor_texto IS NOT NULL))
);

-- 5. Observaciones diarias
CREATE TABLE IF NOT EXISTS observaciones_diarias (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL CHECK (fecha GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    observacion TEXT NOT NULL,
    importacion_id INTEGER REFERENCES importaciones(id) ON DELETE RESTRICT,
    hoja_origen TEXT,
    fila_origen INTEGER
);

-- 6. Trazabilidad de correcciones
CREATE TABLE IF NOT EXISTS correcciones_migracion (
    id INTEGER PRIMARY KEY,
    importacion_id INTEGER REFERENCES importaciones(id) ON DELETE RESTRICT,
    hoja_origen TEXT NOT NULL,
    fila_origen INTEGER NOT NULL,
    campo TEXT NOT NULL,
    valor_anterior TEXT NOT NULL,
    valor_nuevo TEXT NOT NULL,
    motivo TEXT NOT NULL,
    corregida_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (importacion_id, hoja_origen, fila_origen, campo)
);

-- Índices de consulta rápida
CREATE INDEX IF NOT EXISTS idx_lecturas_punto_fecha ON lecturas(punto_medicion_id, fecha);
CREATE INDEX IF NOT EXISTS idx_lecturas_fecha ON lecturas(fecha);
CREATE INDEX IF NOT EXISTS idx_observaciones_fecha ON observaciones_diarias(fecha);

-- 7. Vista analítica de consumos diarios (calculada mediante funciones ventana LAG)
DROP VIEW IF EXISTS v_consumos_diarios;

CREATE VIEW v_consumos_diarios AS
WITH lecturas_pivot AS (
    SELECT 
        fecha,
        MAX(CASE WHEN punto_medicion_id = 1 THEN valor_numerico END) AS agua_mg,
        MAX(CASE WHEN punto_medicion_id = 2 THEN valor_numerico END) AS agua_bow,
        MAX(CASE WHEN punto_medicion_id = 3 THEN valor_numerico END) AS agua_piscina,
        MAX(CASE WHEN punto_medicion_id = 4 THEN valor_numerico END) AS luz_hotel,
        MAX(CASE WHEN punto_medicion_id = 5 THEN valor_numerico END) AS nivel_diesel,
        MAX(CASE WHEN punto_medicion_id = 6 THEN valor_texto END) AS gas_registro
    FROM lecturas
    GROUP BY fecha
),
diffs AS (
    SELECT 
        fecha,
        agua_mg,
        ROUND(agua_mg - LAG(agua_mg) OVER (ORDER BY fecha), 2) AS consumo_agua_mg,
        agua_bow,
        ROUND(agua_bow - LAG(agua_bow) OVER (ORDER BY fecha), 2) AS consumo_agua_bow,
        agua_piscina,
        ROUND(agua_piscina - LAG(agua_piscina) OVER (ORDER BY fecha), 2) AS consumo_agua_piscina,
        luz_hotel,
        ROUND(luz_hotel - LAG(luz_hotel) OVER (ORDER BY fecha), 2) AS consumo_luz_hotel,
        nivel_diesel,
        ROUND(LAG(nivel_diesel) OVER (ORDER BY fecha) - nivel_diesel, 2) AS delta_nivel_diesel,
        gas_registro
    FROM lecturas_pivot
)
SELECT 
    d.fecha,
    d.agua_mg,
    d.consumo_agua_mg,
    d.agua_bow,
    d.consumo_agua_bow,
    d.agua_piscina,
    d.consumo_agua_piscina,
    ROUND(COALESCE(d.consumo_agua_bow, 0) - COALESCE(d.consumo_agua_piscina, 0), 2) AS consumo_agua_bow_gym,
    ROUND(COALESCE(d.consumo_agua_mg, 0) - COALESCE(d.consumo_agua_bow, 0), 2) AS consumo_agua_hotel,
    d.luz_hotel,
    d.consumo_luz_hotel,
    d.nivel_diesel,
    d.delta_nivel_diesel,
    d.gas_registro,
    obs.observacion
FROM diffs d
LEFT JOIN observaciones_diarias obs ON d.fecha = obs.fecha
ORDER BY d.fecha;

-- 8. Datos iniciales del catálogo
INSERT OR IGNORE INTO instalaciones (id, codigo, nombre, activa) 
VALUES (1, 'OX', 'Espacio OX', 1);

INSERT OR IGNORE INTO puntos_medicion 
(id, instalacion_id, codigo, nombre, tipo, magnitud, unidad, estado_unidad, modo_lectura, punto_padre_id, activo, notas)
VALUES
(1, 1, 'AGUA-MG', 'Medidor agua general', 'medidor', 'agua', 'm3', 'inferida', 'acumulativa', NULL, 1, 'Unidad inferida por el tipo de contador.'),
(2, 1, 'AGUA-BOW', 'Remarcador agua Bow', 'remarcador', 'agua', 'm3', 'inferida', 'acumulativa', 1, 1, 'Remarcador asociado al medidor general de agua.'),
(3, 1, 'AGUA-PISCINA', 'Remarcador agua piscina', 'remarcador', 'agua', 'm3', 'inferida', 'acumulativa', 1, 1, 'Remarcador asociado al medidor general de agua.'),
(4, 1, 'LUZ-HOTEL', 'Remarcador luz hotel', 'remarcador', 'electricidad', 'kWh', 'inferida', 'acumulativa', NULL, 1, 'No hay un medidor padre registrado en la hoja.'),
(5, 1, 'DIESEL-TK', 'Nivel estanque petróleo', 'nivel', 'diesel', 'L', 'inferida', 'nivel', NULL, 1, 'Unidad inferida por los valores del estanque y referencias a recargas en litros.'),
(6, 1, 'GAS-REGISTRO', 'Registro de gas', 'registro_texto', 'gas', NULL, 'pendiente', 'texto', NULL, 1, 'Se preserva como texto: la columna mezcla porcentajes, PSI y otros formatos.');
