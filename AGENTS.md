# AGENTS.md

## What this is

Single-purpose, Spanish-language local dashboard for "Espacio OX" medidor readings (water, electricity, diesel, gas). No build step, package manager, tests, or lint config. Five source files + two data files.

## Run

- Double-click `abrir_visualizador.bat`, or from anywhere run `python servidor_visualizador.py` (it resolves files via `__file__`).
- The server is **stdlib-only**: no `pip install` needed to view. It auto-opens `http://127.0.0.1:8050`; if 8050 is busy it silently tries up to 8099, so read the console for the real URL. Ctrl+C stops it.
- `index.html` loads Tailwind, Chart.js and lucide from CDNs — expect an unstyled/broken UI offline.

## Layout

- `servidor_visualizador.py` — the entire backend (`http.server` + `sqlite3`). Endpoints: `/api/kpis`, `/api/consumos`, `/api/graficos`, `/api/tablas`, `/api/explorar`, and `POST /api/query` (SELECT/WITH only, auto-appends `LIMIT 200`).
- `index.html` — the entire frontend, no bundler; calls those endpoints directly via `fetch`.
- `esquema_registro_medidores.sql` — **not just DDL**: also seeds `instalaciones`, the six `puntos_medicion` rows, and defines the `v_consumos_diarios` view (`user_version = 2`).
- `Registro_Medidores_Espacio_OX.sqlite` — checked-in runtime data the viewer reads (10,350 lecturas, 92 observaciones, 2020-09-23 → 2026-11-21). Treat as live data, not a disposable build artifact.
- `Registro_Medidores_Espacio_OX.xlsx` — upstream spreadsheet, sheet `Control de Medidores.`.

## Gotchas

- **Do not run `migrar_excel_a_sqlite.py` as-is.** It backs up the DB to `..._backup_v1.sqlite`, **deletes** the current DB, rebuilds from the SQL schema, then crashes with `sqlite3.IntegrityError: UNIQUE constraint failed: instalaciones.id` — the schema already inserts ids 1–6 and the script inserts them again (verified on an isolated copy). Remove those duplicate INSERTs first, and only ever run it against a copy.
- That migration uses **relative** paths, so it only works when launched from the repo root (the `.bat` does `cd /d "%~dp0"` for the same reason). `openpyxl` is imported only there; the server never needs it.
- Measurement-point IDs 1–6 are magic numbers hard-coded in two places: the `v_consumos_diarios` pivot `CASE`s and the migration's Excel column map (cols 2, 4, 6, 10, 12 → water/luz/diesel; 16–17 gas, 18 observaciones, rows 2–2252). Renumbering points silently breaks consumption math.
- The `v_consumos_diarios` view is defined twice — in `esquema_registro_medidores.sql` and again in the migration script. Keep both in sync if it is ever changed.
