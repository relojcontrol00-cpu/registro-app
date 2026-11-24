# Habilita el acceso al dashboard desde otros dispositivos de la red local.
#
# Por que hace falta: el motor Docker de Kiri vive dentro de WSL2 (red NAT),
# asi que Windows solo reenvia el puerto publicado a 127.0.0.1 (wslrelay).
# Este script crea un portproxy 0.0.0.0:8050 -> IP de la VM de Kiri:8050
# y abre el firewall de Windows (perfil privado).
#
# Uso manual: clic derecho -> "Ejecutar con PowerShell" (pide elevacion UAC), o:
#   pwsh -NoProfile -ExecutionPolicy Bypass -File .\habilitar_acceso_lan.ps1
#
# Uso automatico (recomendado): tarea programada "Registro Medidores - LAN",
# con privilegios maximos, disparador al iniciar sesion + repeticion cada
# 10 minutos. Tras un reinicio o "wsl --shutdown" detecta la IP nueva de WSL
# y repara el portproxy sin intervencion.

$ErrorActionPreference = 'Stop'
$Puerto = 8050

# Auto-elevacion: si no somos administrador, relanzar con UAC y dejar la
# ventana abierta para ver el resultado. La tarea programada ya corre elevada,
# asi que esta rama no se usa en ese caso.
$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    if (-not [Environment]::UserInteractive) {
        throw 'Se necesitan privilegios de administrador: configure la tarea con "Ejecutar con privilegios maximos".'
    }
    Start-Process pwsh -Verb RunAs -ArgumentList '-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`""
    exit
}

# Dejar registro de lo que ocurre (util porque la ventana elevada se cierra al terminar).
$logDir = Join-Path $env:TEMP 'opencode'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
Start-Transcript -Path (Join-Path $logDir 'habilitar_acceso_lan.log') -Force | Out-Null
Write-Host "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="

# 1. IP actual de la VM de Kiri en WSL2, con reintentos por si WSL arranca tarde.
$ipKiri = $null
for ($intento = 1; $intento -le 6; $intento++) {
    $salida = (wsl -d kiri -- ip -4 addr show eth0 2>$null) -join "`n"
    if ($salida -match 'inet (\d+\.\d+\.\d+\.\d+)') {
        $ipKiri = $Matches[1]
        break
    }
    if ($intento -lt 6) { Start-Sleep -Seconds 10 }
}
if (-not $ipKiri) {
    throw "No se pudo obtener la IP de la distro 'kiri' en WSL tras 6 intentos. Esta Kiri encendido?"
}
Write-Host "IP de la VM de Kiri: $ipKiri"

# 2. El portproxy necesita el servicio IP Helper (iphlpsvc).
if ((Get-Service iphlpsvc).Status -ne 'Running') { Start-Service iphlpsvc }

# 3. Portproxy: escuchar en todas las interfaces de Windows y reenviar a la VM.
# Solo se reconfigura si la IP cambio, para no cortar la conexion cada 10 min.
$linea = netsh interface portproxy show v4tov4 | Where-Object { $_ -match "0\.0\.0\.0\s+$Puerto" } | Select-Object -First 1
$ipActual = $null
if ($linea -and $linea -match "0\.0\.0\.0\s+$Puerto\s+(\d+\.\d+\.\d+\.\d+)\s+$Puerto") {
    $ipActual = $Matches[1]
}
if ($ipActual -ne $ipKiri) {
    netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$Puerto 2>$null
    netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$Puerto connectaddress=$ipKiri connectport=$Puerto
    if ($LASTEXITCODE -ne 0) { throw 'Fallo al crear el portproxy.' }
    Write-Host "Portproxy actualizado 0.0.0.0:$Puerto -> ${ipKiri}:$Puerto (antes: $ipActual)."
} else {
    Write-Host "Portproxy ya apuntaba a ${ipKiri}:$Puerto, sin cambios."
}

# 4. Firewall: permitir TCP de entrada solo en redes privadas.
if (-not (Get-NetFirewallRule -DisplayName 'Registro Medidores LAN 8050' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName 'Registro Medidores LAN 8050' -Direction Inbound -Protocol TCP -LocalPort $Puerto -Action Allow -Profile Private | Out-Null
    Write-Host 'Regla de firewall creada (perfil privado).'
} else {
    Write-Host 'La regla de firewall ya existia.'
}

# 5. Mostrar las URLs de acceso desde otros dispositivos.
$ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.InterfaceAlias -notlike 'vEthernet*'
}
Write-Host ''
Write-Host 'Otros dispositivos de la red pueden abrir:'
foreach ($ip in $ips) {
    Write-Host ("  http://{0}:{1}   ({2})" -f $ip.IPAddress, $Puerto, $ip.InterfaceAlias)
}
Write-Host ''
Write-Host 'Nota: el dashboard no tiene autenticacion; cualquiera en la red puede LEER los datos.'

Stop-Transcript | Out-Null
