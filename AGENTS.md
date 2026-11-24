# AGENTS.md

## What this is

Single-purpose, Spanish-language local dashboard for "Espacio OX" medidor readings (water, electricity, diesel, gas). No build step, package manager, tests, or lint config. Five source files + two data files, plus container files (`Dockerfile`, `docker-compose.yml`, `.dockerignore`), `README-CONTENEDOR.md`, `habilitar_acceso_lan.ps1` (LAN access helper) and `registrar_tarea_lan.ps1` (creates/recreates the scheduled task that automates it).

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

## Container (Kiri / Docker on Windows)

- `README-CONTENEDOR.md` has the full Windows + Kiri guide (beta MSI, WSL2, docker context, backups). `docker compose build` then `docker compose up -d` publishes port 8050 on all interfaces — but Kiri's engine lives in WSL2 behind NAT, so Windows only forwards it to `127.0.0.1` (`wslrelay`). LAN access (`http://<host-ip>:8050`, no auth!) additionally needs `habilitar_acceso_lan.ps1` run as admin: portproxy `0.0.0.0:8050` → the kiri distro's WSL IP + private-profile firewall rule. **Fully automated**: scheduled task `Registro Medidores - LAN` runs that script at logon and every 10 minutes with highest privileges in a non-interactive S4U session with `-WindowStyle Hidden` (no console window pops up, works even when logged out), re-detecting the WSL IP after reboots/`wsl --shutdown` and rewriting portproxy only when it changed (script retries up to 6× if WSL is slow to start). Task log: `%TEMP%\opencode\habilitar_acceso_lan.log`. To revert to localhost-only: restore `127.0.0.1:8050:8050`, `Disable-ScheduledTask -TaskName 'Registro Medidores - LAN'`, and delete the portproxy.
- `servidor_visualizador.py` reads `HOST`, `PORT`, `DB_FILE` and `OPEN_BROWSER` env vars; local defaults are unchanged (`127.0.0.1`, `8050`, DB next to the script, browser opens). In the container set `HOST=0.0.0.0`, `OPEN_BROWSER=0`, `DB_FILE=/app/data/Registro_Medidores_Espacio_OX.sqlite` — otherwise port mapping and data persistence break.
- **The Windows `.sqlite` is the single source of truth.** Compose bind-mounts it read-only at `/app/data/Registro_Medidores_Espacio_OX.sqlite` (WSL2 path `/mnt/c/...`). Edits in Windows are visible immediately, no rebuild needed, and the container cannot write to it. A rebuild only affects code, never data. The image's seed COPY is a fallback for running the image without the mount. Never mount over `/app` (that would hide `index.html`). If the `.sqlite` file is *replaced* rather than edited in place, `docker compose restart medidores` is needed to re-resolve the bind mount.
