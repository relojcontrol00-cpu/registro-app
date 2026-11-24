"""
Servidor local para el Visualizador Interactivo de Registro de Medidores - Espacio OX
Utiliza únicamente librerías estándar de Python (sin dependencias adicionales).
"""

import http.server
import socketserver
import json
import sqlite3
import urllib.parse
import os
import webbrowser
import sys

PORT = int(os.environ.get("PORT", "8050"))
HOST = os.environ.get("HOST", "127.0.0.1")
DB_FILE = os.environ.get("DB_FILE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "Registro_Medidores_Espacio_OX.sqlite")
HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
OPEN_BROWSER = os.environ.get("OPEN_BROWSER", "1") != "0"


def get_db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.serve_file(HTML_FILE, "text/html; charset=utf-8")
        elif path == "/api/kpis":
            self.serve_kpis()
        elif path == "/api/consumos":
            self.serve_consumos(params)
        elif path == "/api/graficos":
            self.serve_graficos(params)
        elif path == "/api/tablas":
            self.serve_tablas()
        elif path == "/api/explorar":
            self.serve_explorar(params)
        else:
            self.send_error(404, "Ruta no encontrada")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/query":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8"))
                sql = data.get("query", "").strip()
                self.serve_custom_query(sql)
            except Exception as e:
                self.send_json({"error": str(e)}, status=400)
        else:
            self.send_error(404, "Ruta no encontrada")

    def serve_file(self, filepath, content_type):
        if not os.path.exists(filepath):
            self.send_error(404, "Archivo no encontrado")
            return
        with open(filepath, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(content))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, data, status=200):
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(content))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def serve_kpis(self):
        con = get_db()
        cur = con.cursor()

        # Última fecha y métricas del último día
        cur.execute("SELECT * FROM v_consumos_diarios ORDER BY fecha DESC LIMIT 1")
        last_row = dict(cur.fetchone() or {})

        # Penúltima fecha para variaciones
        cur.execute("SELECT * FROM v_consumos_diarios ORDER BY fecha DESC LIMIT 1 OFFSET 1")
        prev_row = dict(cur.fetchone() or {})

        # Totales generales
        cur.execute("SELECT count(DISTINCT fecha), min(fecha), max(fecha) FROM lecturas")
        dias_total, min_fecha, max_fecha = cur.fetchone()

        cur.execute("SELECT count(*) FROM lecturas")
        total_lecturas = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM observaciones_diarias")
        total_obs = cur.fetchone()[0]

        # Promedios de los últimos 7 y 30 registros diarios
        def promedios(limite):
            cur.execute("""
                SELECT
                    ROUND(AVG(consumo_agua_mg), 2) as agua_mg,
                    ROUND(AVG(consumo_agua_hotel), 2) as agua_hotel,
                    ROUND(AVG(consumo_agua_piscina), 2) as agua_piscina,
                    ROUND(AVG(consumo_agua_bow_gym), 2) as agua_rest,
                    ROUND(AVG(consumo_luz_hotel), 2) as luz_hotel,
                    ROUND(AVG(consumo_diesel), 2) as diesel
                FROM (SELECT * FROM v_consumos_diarios ORDER BY fecha DESC LIMIT ?)
            """, (limite,))
            return dict(cur.fetchone() or {})

        avg7 = promedios(7)
        avg30 = promedios(30)

        con.close()

        self.send_json({
            "dias_total": dias_total,
            "min_fecha": min_fecha,
            "max_fecha": max_fecha,
            "total_lecturas": total_lecturas,
            "total_obs": total_obs,
            "ultimo_registro": last_row,
            "penultimo_registro": prev_row,
            "promedios_7d": avg7,
            "promedios_30d": avg30
        })

    def serve_consumos(self, params):
        con = get_db()
        cur = con.cursor()

        desde = params.get("desde", [""])[0]
        hasta = params.get("hasta", [""])[0]
        search = params.get("search", [""])[0].strip()
        limit = int(params.get("limit", [50])[0])
        offset = int(params.get("offset", [0])[0])

        where_clauses = ["1=1"]
        query_params = []

        if desde:
            where_clauses.append("fecha >= ?")
            query_params.append(desde)
        if hasta:
            where_clauses.append("fecha <= ?")
            query_params.append(hasta)
        if search:
            where_clauses.append("(observacion LIKE ? OR gas_registro LIKE ? OR fecha LIKE ?)")
            query_params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        where_sql = " AND ".join(where_clauses)

        # Count total
        cur.execute(f"SELECT count(*) FROM v_consumos_diarios WHERE {where_sql}", query_params)
        total_filtrado = cur.fetchone()[0]

        # Select data
        query = f"""
            SELECT * FROM v_consumos_diarios 
            WHERE {where_sql}
            ORDER BY fecha DESC
            LIMIT ? OFFSET ?
        """
        cur.execute(query, query_params + [limit, offset])
        rows = [dict(r) for r in cur.fetchall()]

        con.close()

        self.send_json({
            "total": total_filtrado,
            "limit": limit,
            "offset": offset,
            "rows": rows
        })

    def serve_graficos(self, params):
        con = get_db()
        cur = con.cursor()

        periodo = params.get("periodo", ["90d"])[0]
        limites_periodo = {"30d": 30, "90d": 90, "1y": 365, "all": None}
        limite = limites_periodo.get(periodo, 90)

        query = """
            WITH graficos_suavizados AS (
                SELECT
                    v.*,
                    AVG(v.consumo_diesel) OVER (
                        ORDER BY julianday(v.fecha)
                        RANGE BETWEEN 3 PRECEDING AND 3 FOLLOWING
                    ) AS promedio_diesel_7d,
                    MIN(julianday(v.fecha)) OVER () AS primera_fecha,
                    MAX(julianday(v.fecha)) OVER () AS ultima_fecha,
                    ROW_NUMBER() OVER (ORDER BY v.fecha DESC) AS orden_periodo
                FROM v_consumos_diarios v
            )
            SELECT 
                fecha,
                agua_mg,
                consumo_agua_mg,
                agua_bow,
                consumo_agua_bow,
                agua_piscina,
                consumo_agua_piscina,
                consumo_agua_hotel,
                consumo_agua_bow_gym,
                luz_hotel,
                consumo_luz_hotel,
                nivel_diesel,
                consumo_diesel,
                CASE
                    WHEN julianday(fecha) >= primera_fecha + 3
                     AND julianday(fecha) <= ultima_fecha - 3
                    THEN ROUND(promedio_diesel_7d, 2)
                    ELSE NULL
                END AS consumo_diesel_promedio_7d,
                gas_registro
            FROM graficos_suavizados
            WHERE (? IS NULL OR orden_periodo <= ?)
            ORDER BY fecha ASC
        """
        cur.execute(query, (limite, limite))
        rows = [dict(r) for r in cur.fetchall()]
        con.close()

        self.send_json({"periodo": periodo, "data": rows})

    def serve_tablas(self):
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY type, name")
        tablas = []
        for row in cur.fetchall():
            name = row[0]
            try:
                cur.execute(f"SELECT count(*) FROM {name}")
                count = cur.fetchone()[0]
            except Exception:
                count = 0
            tablas.append({"nombre": name, "filas": count})
        con.close()
        self.send_json({"tablas": tablas})

    def serve_explorar(self, params):
        con = get_db()
        cur = con.cursor()

        tabla = params.get("tabla", ["lecturas"])[0]
        limit = int(params.get("limit", [50])[0])
        offset = int(params.get("offset", [0])[0])

        # Validar nombre seguro de tabla
        cur.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name=?", (tabla,))
        if not cur.fetchone():
            con.close()
            self.send_json({"error": "Tabla no válida"}, status=400)
            return

        cur.execute(f"SELECT count(*) FROM {tabla}")
        total = cur.fetchone()[0]

        cur.execute(f"SELECT * FROM {tabla} LIMIT ? OFFSET ?", (limit, offset))
        rows = [dict(r) for r in cur.fetchall()]
        
        # Obtener columnas
        cols = [desc[0] for desc in cur.description] if cur.description else []
        con.close()

        self.send_json({
            "tabla": tabla,
            "total": total,
            "columnas": cols,
            "rows": rows,
            "limit": limit,
            "offset": offset
        })

    def serve_custom_query(self, sql):
        sql_clean = sql.strip()
        # Eliminar punto y coma al final si el usuario lo ingresó
        while sql_clean.endswith(";"):
            sql_clean = sql_clean[:-1].strip()

        if not sql_clean:
            self.send_json({"error": "La consulta está vacía."}, status=400)
            return

        # Solo permitir sentencias SELECT o WITH
        first_word = sql_clean.split()[0].upper() if sql_clean else ""
        if first_word not in ("SELECT", "WITH", "EXPLAIN", "PRAGMA"):
            self.send_json({"error": "Solo se permiten consultas de lectura (SELECT o WITH)."}, status=400)
            return

        con = get_db()
        cur = con.cursor()
        try:
            # Forzar límite de seguridad si no viene especificado
            if "LIMIT" not in sql_clean.upper():
                sql_exec = f"{sql_clean} LIMIT 200"
            else:
                sql_exec = sql_clean
            
            cur.execute(sql_exec)
            rows = [dict(r) for r in cur.fetchall()]
            cols = [desc[0] for desc in cur.description] if cur.description else []
            con.close()
            self.send_json({"columnas": cols, "rows": rows, "count": len(rows)})
        except Exception as e:
            con.close()
            self.send_json({"error": str(e)}, status=400)


def find_free_port(start_port=8050):
    import socket
    port = start_port
    while port < start_port + 50:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
            port += 1
    return start_port


if __name__ == "__main__":
    port = find_free_port(PORT)
    server_address = (HOST, port)
    
    # Manejar inicio limpio
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(server_address, DashboardHandler) as httpd:
        url = f"http://127.0.0.1:{port}"
        print(f"\n=========================================================")
        print(f"  VISUALIZADOR DE BASE DE DATOS - ESPACIO OX")
        print(f"  Base de datos: {DB_FILE}")
        print(f"  Servidor iniciado en: {url}")
        print(f"  Presiona Ctrl+C para detener el servidor.")
        print(f"=========================================================\n")
        
        # Abrir navegador automáticamente (desactivado dentro del contenedor)
        if OPEN_BROWSER:
            webbrowser.open(url)
        else:
            print("  Navegador automático desactivado (OPEN_BROWSER=0).")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor detenido.")
            sys.exit(0)
