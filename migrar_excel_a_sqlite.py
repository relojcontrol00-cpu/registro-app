"""
Script de migración: Registro_Medidores_Espacio_OX.xlsx -> Registro_Medidores_Espacio_OX.sqlite
Espacio OX - Noviembre 2026
"""

import os
import shutil
import sqlite3
import datetime
import openpyxl

EXCEL_FILE = "Registro_Medidores_Espacio_OX.xlsx"
SHEET_NAME = "Control de Medidores."
SQL_SCHEMA_FILE = "esquema_registro_medidores.sql"
DB_FILE = "Registro_Medidores_Espacio_OX.sqlite"
BACKUP_DB_FILE = "Registro_Medidores_Espacio_OX_backup_v1.sqlite"


def format_gas_value(nest, pgas):
    if nest is None and pgas is None:
        return None
    
    # Si solo viene estanque
    if pgas is None or str(pgas).strip() == "":
        return f"({str(nest).strip()})" if nest is not None else None
    
    # Si solo viene gas (sin estanque)
    if nest is None:
        if isinstance(pgas, (int, float)):
            if 0 < pgas <= 1:
                return f"{int(round(pgas * 100))}%"
            return f"{pgas}%"
        s = str(pgas).strip()
        return s if s else None
    
    # Vienen ambos
    nest_str = str(nest).strip()
    if isinstance(pgas, (int, float)):
        if 0 < pgas <= 1:
            return f"({nest_str}) {int(round(pgas * 100))}%"
        return f"({nest_str}) {pgas}%"
    
    s = str(pgas).strip()
    if s.startswith("("):
        return s
    return f"({nest_str}) {s}"


def main():
    print(f"=== INICIANDO MIGRACIÓN DE {EXCEL_FILE} A SQLITE ===")

    # 1. Respaldo de base previa si existe
    if os.path.exists(DB_FILE):
        if not os.path.exists(BACKUP_DB_FILE):
            print(f"Creando respaldo de seguridad: {BACKUP_DB_FILE}...")
            shutil.copy2(DB_FILE, BACKUP_DB_FILE)
            print("Respaldo creado con éxito.")
        else:
            print(f"El archivo de respaldo {BACKUP_DB_FILE} ya existe.")
        
        # Eliminar o reiniciar base actual para una importación limpia
        os.remove(DB_FILE)

    # 2. Crear base de datos y cargar esquema
    print(f"Aplicando esquema desde {SQL_SCHEMA_FILE}...")
    con = sqlite3.connect(DB_FILE)
    con.execute("PRAGMA foreign_keys = ON;")
    
    with open(SQL_SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    con.executescript(schema_sql)

    cur = con.cursor()

    # 3. Insertar instalación
    cur.execute(
        "INSERT INTO instalaciones (id, codigo, nombre, activa) VALUES (1, 'OX', 'Espacio OX', 1)"
    )

    # 4. Insertar puntos de medición
    puntos = [
        (1, 1, 'AGUA-MG', 'Medidor agua general', 'medidor', 'agua', 'm3', 'inferida', 'acumulativa', None, 1, 'Unidad inferida por el tipo de contador.'),
        (2, 1, 'AGUA-BOW', 'Remarcador agua Bow', 'remarcador', 'agua', 'm3', 'inferida', 'acumulativa', 1, 1, 'Remarcador asociado al medidor general de agua.'),
        (3, 1, 'AGUA-PISCINA', 'Remarcador agua piscina', 'remarcador', 'agua', 'm3', 'inferida', 'acumulativa', 1, 1, 'Remarcador asociado al medidor general de agua.'),
        (4, 1, 'LUZ-HOTEL', 'Remarcador luz hotel', 'remarcador', 'electricidad', 'kWh', 'inferida', 'acumulativa', None, 1, 'No hay un medidor padre registrado en la hoja.'),
        (5, 1, 'DIESEL-TK', 'Nivel estanque petróleo', 'nivel', 'diesel', 'L', 'inferida', 'nivel', None, 1, 'Unidad inferida por los valores del estanque y referencias a recargas en litros.'),
        (6, 1, 'GAS-REGISTRO', 'Registro de gas', 'registro_texto', 'gas', None, 'pendiente', 'texto', None, 1, 'Se preserva como texto: la columna mezcla porcentajes, PSI y otros formatos.')
    ]
    cur.executemany(
        """INSERT INTO puntos_medicion 
           (id, instalacion_id, codigo, nombre, tipo, magnitud, unidad, estado_unidad, modo_lectura, punto_padre_id, activo, notas)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        puntos
    )

    # 5. Insertar registro de importación
    cur.execute(
        """INSERT INTO importaciones (id, archivo, hoja, filas_origen, notas)
           VALUES (1, ?, ?, ?, ?)""",
        (
            EXCEL_FILE,
            SHEET_NAME,
            2251,
            "Importación oficial definitiva tras revisiones y ajustes del Excel. Filas 2 a 2252 (2020-09-23 a 2026-11-21). Filas futuras vacías omitidas."
        )
    )

    # 6. Leer Excel y cargar lecturas
    print(f"Cargando datos desde {EXCEL_FILE} [{SHEET_NAME}]...")
    wb = openpyxl.load_workbook(EXCEL_FILE, data_only=True)
    ws = wb[SHEET_NAME]

    lecturas_to_insert = []
    observaciones_to_insert = []

    # Mapeo de columnas a punto_medicion_id
    numeric_cols = [
        (2, 1),   # Medidor - Agua M. G. -> AGUA-MG
        (4, 2),   # Remarcador - Agua M.Bow -> AGUA-BOW
        (6, 3),   # Remarcador - Agua Piscina -> AGUA-PISCINA
        (10, 4),  # Remarcador - Luz M. Hotel -> LUZ-HOTEL
        (12, 5)   # Nivel TK. Petroleo -> DIESEL-TK
    ]

    total_rows = 0
    start_date = None
    end_date = None

    for r in range(2, 2253):
        f_val = ws.cell(r, 1).value
        if f_val is None:
            continue
        
        if isinstance(f_val, datetime.datetime):
            fecha_str = f_val.strftime("%Y-%m-%d")
        elif isinstance(f_val, datetime.date):
            fecha_str = f_val.strftime("%Y-%m-%d")
        else:
            fecha_str = str(f_val)[:10]

        if start_date is None:
            start_date = fecha_str
        end_date = fecha_str
        total_rows += 1

        # Cargar columnas numéricas puras
        for col_idx, pm_id in numeric_cols:
            val = ws.cell(r, col_idx).value
            if val is not None and str(val).strip() != "":
                val_float = float(val)
                # Formatear valor original como texto
                val_orig = str(val).strip()
                lecturas_to_insert.append((
                    pm_id, fecha_str, val_float, None, val_orig, 'lectura', 1, SHEET_NAME, r
                ))

        # Cargar registro de Gas (Col 16: N° de estanque, Col 17: % - Gas)
        nest = ws.cell(r, 16).value
        pgas = ws.cell(r, 17).value
        gas_text = format_gas_value(nest, pgas)
        if gas_text is not None:
            lecturas_to_insert.append((
                6, fecha_str, None, gas_text, gas_text, 'lectura', 1, SHEET_NAME, r
            ))

        # Cargar Observaciones (Col 18)
        obs_val = ws.cell(r, 18).value
        if obs_val is not None and str(obs_val).strip() != "":
            obs_clean = str(obs_val).strip()
            observaciones_to_insert.append((
                fecha_str, obs_clean, 1, SHEET_NAME, r
            ))

    wb.close()

    print(f"Insertando {len(lecturas_to_insert)} lecturas...")
    cur.executemany(
        """INSERT INTO lecturas 
           (punto_medicion_id, fecha, valor_numerico, valor_texto, valor_original, clase, importacion_id, hoja_origen, fila_origen)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        lecturas_to_insert
    )

    print(f"Insertando {len(observaciones_to_insert)} observaciones diarias...")
    cur.executemany(
        """INSERT INTO observaciones_diarias
           (fecha, observacion, importacion_id, hoja_origen, fila_origen)
           VALUES (?, ?, ?, ?, ?)""",
        observaciones_to_insert
    )

    # 7. Crear Vista Analítica de Consumos Diarios
    print("Creando vista analítica v_consumos_diarios...")
    cur.execute("""
    CREATE VIEW IF NOT EXISTS v_consumos_diarios AS
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
    """)

    con.commit()

    # 8. Verificaciones de Integridad
    print("\n=== VERIFICACIÓN DE INTEGRIDAD ===")
    cur.execute("PRAGMA integrity_check;")
    print("Integrity check:", cur.fetchone()[0])
    cur.execute("PRAGMA foreign_key_check;")
    fk_errors = cur.fetchall()
    print("Foreign key check errors:", len(fk_errors))

    cur.execute("SELECT count(*) FROM lecturas;")
    count_lecturas = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM observaciones_diarias;")
    count_obs = cur.fetchone()[0]
    cur.execute("SELECT count(DISTINCT fecha) FROM lecturas;")
    count_fechas = cur.fetchone()[0]

    print(f"Total filas procesadas del Excel: {total_rows}")
    print(f"Rango de fechas: {start_date} a {end_date}")
    print(f"Total lecturas insertadas: {count_lecturas}")
    print(f"Total días únicos con lectura: {count_fechas}")
    print(f"Total observaciones insertadas: {count_obs}")

    print("\nDesglose de lecturas por punto de medición:")
    cur.execute("""
        SELECT pm.id, pm.codigo, pm.nombre, count(l.id), min(l.fecha), max(l.fecha)
        FROM puntos_medicion pm
        LEFT JOIN lecturas l ON pm.id = l.punto_medicion_id
        GROUP BY pm.id, pm.codigo, pm.nombre
        ORDER BY pm.id
    """)
    for row in cur.fetchall():
        print(f"  Punto {row[0]} ({row[1]:12s} - {row[2]:25s}): {row[3]:5d} lecturas [{row[4]} a {row[5]}]")

    # Muestra de la vista de consumos
    print("\nPrimeras 3 filas de la vista v_consumos_diarios:")
    cur.execute("SELECT fecha, agua_mg, consumo_agua_mg, agua_bow, consumo_agua_bow, luz_hotel, consumo_luz_hotel FROM v_consumos_diarios LIMIT 3")
    for row in cur.fetchall():
        print(" ", row)

    print("\nÚltimas 3 filas de la vista v_consumos_diarios:")
    cur.execute("SELECT fecha, agua_mg, consumo_agua_mg, agua_bow, consumo_agua_bow, luz_hotel, consumo_luz_hotel FROM v_consumos_diarios ORDER BY fecha DESC LIMIT 3")
    for row in cur.fetchall():
        print(" ", row)

    con.close()
    print("\n=== MIGRACIÓN FINALIZADA CON ÉXITO ===")


if __name__ == "__main__":
    main()
