# Crea (o recrea) la tarea programada que mantiene el acceso LAN automatico.
#
# La tarea "Registro Medidores - LAN" ejecuta habilitar_acceso_lan.ps1 al iniciar
# sesion y cada 10 minutos, con privilegios maximos. Asi se repara solo el
# portproxy cuando la IP de WSL cambia tras un reinicio o un "wsl --shutdown".
#
# Uso: clic derecho -> "Ejecutar con PowerShell" (acepta el aviso UAC).
# Es seguro ejecutarlo varias veces: reemplaza la tarea si ya existe.

$ErrorActionPreference = 'Stop'

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    if (-not [Environment]::UserInteractive) {
        throw 'Se necesitan privilegios de administrador para registrar la tarea.'
    }
    Start-Process pwsh -Verb RunAs -ArgumentList '-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`""
    exit
}

$logDir = Join-Path $env:TEMP 'opencode'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
Start-Transcript -Path (Join-Path $logDir 'registrar_tarea_lan.log') -Force | Out-Null

$nombre = 'Registro Medidores - LAN'
$script = Join-Path $PSScriptRoot 'habilitar_acceso_lan.ps1'
if (-not (Test-Path $script)) { throw "No se encontro $script" }
Write-Host "Script a ejecutar: $script"

Unregister-ScheduledTask -TaskName $nombre -Confirm:$false -ErrorAction SilentlyContinue

# -WindowStyle Hidden: oculta la consola de pwsh.
# LogonType S4U: ejecuta en sesion sin interfaz (no abre ventana ni aunque el
# usuario este deslogueado). -Hidden solo oculta la tarea en el Programador,
# no basta para evitar que aparezca la terminal.
$accion     = New-ScheduledTaskAction -Execute 'pwsh.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $script)
$alLogon    = New-ScheduledTaskTrigger -AtLogOn
$repeticion = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
$ajustes    = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -Hidden
$usuario    = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType S4U -RunLevel Highest

Register-ScheduledTask -TaskName $nombre `
    -Action $accion `
    -Trigger $alLogon, $repeticion `
    -Settings $ajustes `
    -Principal $usuario `
    -Description 'Mantiene el portproxy LAN 8050 apuntando a la IP actual de WSL (Kiri). Se autorrepara tras reinicios o wsl --shutdown.' `
    -Force | Out-Null

Write-Host "Tarea '$nombre' registrada:"
Get-ScheduledTaskInfo -TaskName $nombre | Select-Object LastRunTime, LastTaskResult, NextRunTime | Format-List

Stop-Transcript | Out-Null
