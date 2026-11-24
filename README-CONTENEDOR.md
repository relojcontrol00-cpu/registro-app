# Correr el visualizador en un contenedor con Kiri (Windows)

Kiri es un runtime de contenedores en beta que corre un daemon Linux dentro de WSL2 y
expone la Docker Engine API en el pipe `\\.\pipe\kiri`. Por eso el `docker` CLI,
`docker compose` y `docker buildx` funcionan igual que con Docker Desktop: nuestra app
es un contenedor Linux corriendo en WSL2.

## 1. Instalar Kiri

1. Descarga el MSI de Windows desde <https://runkiri.com/download/>:
   - PCs x64 (Intel/AMD): `Kiri-<version>-x86_64.msi`
   - ARM (Snapdragon/Surface): `Kiri-<version>-arm64.msi`
2. La instalación es por usuario (no pide administrador), pero el MSI **no está
   firmado**: Windows SmartScreen pedirá confirmación.
3. Al abrir Kiri por primera vez, el asistente instala WSL2 si falta (requiere un
   reinicio y aprobación de administrador), luego pide elegir distro:
   **Kiri Linux** (recomendada, ~15 MB) o Ubuntu 26.04 (~418 MB).
4. Termina el paso de "Docker tools". Si dejas **Make Kiri the default for docker**
   activado, `docker` apunta a Kiri. Si tienes Docker Desktop instalado, el `bin` de
   Kiri se agrega al **final** del PATH, así que `docker` puede seguir apuntando a
   Docker Desktop. En ese caso usa siempre `docker --context kiri` o cambia el
   contexto una vez:

   ```powershell
   docker context use kiri
   docker context show          # debe imprimir: kiri
   ```

   Si `docker build` sigue construyendo en Docker Desktop, fuerza Kiri:

   ```powershell
   kiri build-with kiri
   ```

## 2. Levantar la app

Desde esta carpeta (la misma donde está `Dockerfile`):

```powershell
Set-Location 'C:\Users\Recepcion Bowling 2\Desktop\Jaime\registro-app'
docker compose build
docker compose up -d
```

`docker compose up -d --build` también funciona como atajo. Si no cambiaste el
contexto, agrega `--context kiri` a cada comando:

```powershell
docker --context kiri compose build
docker --context kiri compose up -d
```

Abre <http://127.0.0.1:8050>. El contenedor se llama `registro-medidores`, así que
Kiri también lo anuncia como `http://registro-medidores.kiri.localhost` (si el router
de nombres elige el puerto expuesto 8050; `127.0.0.1:8050` siempre funciona).

**Acceso desde otros dispositivos de la red local**: el compose publica `8050:8050`,
pero el motor Docker de Kiri corre dentro de WSL2 con red NAT: Windows solo reenvía
el puerto publicado a `127.0.0.1` (`wslrelay.exe`). Para que otros equipos puedan
abrir `http://<IP-local-de-este-equipo>:8050` hacen falta dos cosas más (como
administrador):

1. Un `netsh interface portproxy` que escuche en `0.0.0.0:8050` y reenvíe a la IP
   de la VM de Kiri dentro de WSL (p. ej. `172.23.115.64:8050`).
2. Una regla de firewall de Windows que permita TCP 8050 entrante (perfil privado).

El script `habilitar_acceso_lan.ps1` hace ambas cosas y detecta la IP de WSL
automáticamente: clic derecho → "Ejecutar con PowerShell" (acepta el aviso UAC).

**Ya está automatizado**: la tarea programada de Windows `Registro Medidores - LAN`
ejecuta ese script **al iniciar sesión y cada 10 minutos**, con privilegios máximos
y en **sesión sin interfaz** (`S4U` + `-WindowStyle Hidden`): no abre ninguna terminal
y funciona incluso si no hay nadie logueado. La IP de la VM de WSL cambia tras
reiniciar Windows o hacer `wsl --shutdown`, pero la tarea la detecta y repara el
portproxy sola, sin intervención. Solo reescribe la regla si la IP cambió, así que
no corta la conexión en cada ejecución.

```powershell
Get-ScheduledTaskInfo -TaskName 'Registro Medidores - LAN' | Select-Object LastRunTime, LastTaskResult, NextRunTime
Start-ScheduledTask -TaskName 'Registro Medidores - LAN'  # forzar una reparación
```

Cada ejecución deja un registro en `%TEMP%\opencode\habilitar_acceso_lan.log`.
Si la tarea no existe (equipo nuevo o se borró), créala ejecutando
`registrar_tarea_lan.ps1` como administrador (clic derecho → "Ejecutar con
PowerShell"). Es seguro repetirlo: reemplaza la tarea existente.

⚠️ El dashboard **no tiene autenticación**: cualquiera en la LAN puede leer los datos
(la DB es de solo lectura, nadie puede modificarla). Para volver a solo localhost:
cambia el mapeo a `"127.0.0.1:8050:8050"`, recrea con `docker compose up -d`, desactiva
la tarea con `Disable-ScheduledTask -TaskName 'Registro Medidores - LAN'` y elimina
el portproxy con `netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=8050`.

Comandos útiles:

```powershell
docker compose ps
docker compose logs -f medidores
curl http://127.0.0.1:8050/api/kpis
docker compose down          # para el contenedor; tus datos están en Windows
docker compose up -d --build # reconstruye la imagen tras cambiar código
docker compose restart medidores # si reemplazaste el archivo .sqlite completo
```

Alternativa sin Compose:

```powershell
docker build -t registro-medidores-espacio-ox:local .
docker run -d --name registro-medidores `
  -p 8050:8050 `
  -v "${PWD}\Registro_Medidores_Espacio_OX.sqlite:/app/data/Registro_Medidores_Espacio_OX.sqlite:ro" `
  registro-medidores-espacio-ox:local
```

## 3. Datos: la DB de Windows es la única fuente de verdad

La DB **no se copia** al contenedor ni vive en un volumen: se monta como bind mount
**solo lectura** desde tu carpeta:

```
./Registro_Medidores_Espacio_OX.sqlite → /app/data/Registro_Medidores_Espacio_OX.sqlite  (ro)
```

Dentro de WSL2 eso es `/mnt/c/Users/.../registro-app/Registro_Medidores_Espacio_OX.sqlite`.

Consecuencias:

- **Si la DB crece o cambia en Windows, el contenedor lo ve al instante.** No hace
  falta rebuild, ni `docker cp`, ni reiniciar. Cada request abre una conexión nueva.
- **El contenedor no puede modificar tu DB**: el montaje es `:ro` y SQLite responde
  `attempt to write a readonly database`. El dashboard es de solo lectura de todos
  modos (`/api/query` solo admite SELECT/WITH/EXPLAIN/PRAGMA).
- **Un rebuild nunca pisa tus datos**: el rebuild solo afecta al código de la imagen.
- La única copia que importa es tu `.sqlite` en Windows. Haz backups de ese archivo
  (copiarlo a otra carpeta basta). No hay volumen que se pueda perder al desinstalar
  Kiri.
- La imagen todavía incluye una copia semilla de la DB; solo se usa si corres la
  imagen **sin** el montaje. Con Compose siempre queda tapada por el bind mount.

⚠️ Si regeneras la DB **reemplazando el archivo** (p. ej. borrándolo y creando uno
nuevo, o un `os.replace`), el bind mount puede seguir apuntando al archivo viejo.
En ese caso: `docker compose restart medidores`. Si el archivo se modifica en el
lugar (SQLite normal), no hace falta nada.

**No ejecutes `migrar_excel_a_sqlite.py` directamente**: borra la DB y falla con
`UNIQUE constraint failed: instalaciones.id` (ver `AGENTS.md`).

## 4. Cambios aplicados al proyecto

- `Dockerfile`: imagen `python:3.12-slim`, sin dependencias, usuario no-root, puerto
  8050 y healthcheck en `/api/kpis`.
- `docker-compose.yml`: publica `8050:8050` (accesible desde la LAN; sin
  autenticación) y monta la DB de Windows como bind mount solo lectura. Ya no usa
  volumen nombrado.
- `.dockerignore`: excluye `.git`, Excel, backups y archivos que el runtime no necesita.
- `habilitar_acceso_lan.ps1`: habilita el acceso desde la LAN (portproxy hacia la VM
  de Kiri en WSL2 + regla de firewall en perfil privado). Detecta la IP actual de WSL,
  reintenta si WSL arranca tarde y solo reconfigura si la IP cambió. La tarea
  programada `Registro Medidores - LAN` lo ejecuta al iniciar sesión y cada 10 min.
- `registrar_tarea_lan.ps1`: crea/recrea esa tarea programada con privilegios
  máximos. Ejecutar una sola vez (o cada vez que se migre el equipo).
- `servidor_visualizador.py`: ahora respeta variables de entorno, sin cambiar el
  comportamiento local:
  - `HOST` (por defecto `127.0.0.1`; el contenedor usa `0.0.0.0`).
  - `PORT` (por defecto `8050`).
  - `DB_FILE` (por defecto el SQLite al lado del script).
  - `OPEN_BROWSER=0` evita el `webbrowser.open()` dentro del contenedor.

## 5. Limitaciones / troubleshooting

- **El frontend necesita internet**: `index.html` carga Tailwind, Chart.js y lucide
  desde CDNs. El contenedor solo necesita internet para descargar la imagen base
  durante el `docker build` (y Kiri maneja proxies en `127.0.0.1` automáticamente).
- **Kiri en Windows es beta**: si un comando falla con "Kiri's setup isn't finished",
  abre la ventana de Kiri y termina el asistente.
- Si `docker ps` muestra contenedores de Docker Desktop, estás en el contexto
  equivocado: `docker context use kiri`.
- Si el puerto 8050 está ocupado en Windows, cambia el lado izquierdo del mapeo,
  p. ej. `"8051:8050"` (el servidor dentro del contenedor sigue en 8050).
- Si otro dispositivo de la LAN no puede conectar: revisa la tarea programada
  (`Get-ScheduledTaskInfo -TaskName 'Registro Medidores - LAN'`: `LastTaskResult`
  debe ser `0`) y su log en `%TEMP%\opencode\habilitar_acceso_lan.log`; fuerza una
  reparación con `Start-ScheduledTask -TaskName 'Registro Medidores - LAN'`. Verifica
  que la red de Windows esté clasificada como **Privada** (la regla solo aplica a ese
  perfil) y que ambos equipos estén en la misma red/subred. En redes de hotel o
  corporativas puede haber "aislamiento de clientes" que bloquee el tráfico entre
  dispositivos aunque todo esté bien configurado.
- `abrir_visualizador.bat` es solo para ejecución local; en contenedor el navegador
  se abre desde Windows apuntando a `http://127.0.0.1:8050`.
