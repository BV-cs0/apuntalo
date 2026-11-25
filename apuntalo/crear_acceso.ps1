# Crea un acceso directo (.lnk) de Apúntalo. Se usa una sola vez, la primera vez que se
# abre Apuntalo.exe, para dejar uno en el Escritorio y otro en el menú Inicio.
param(
    [string]$Destino,
    [string]$Objetivo,
    [string]$Carpeta,
    [string]$Icono
)
$ErrorActionPreference = "Stop"

$carpetaDestino = Split-Path $Destino
if (-not (Test-Path $carpetaDestino)) { New-Item -ItemType Directory -Path $carpetaDestino -Force | Out-Null }

$ws = New-Object -ComObject WScript.Shell
$acceso = $ws.CreateShortcut($Destino)
$acceso.TargetPath = $Objetivo
$acceso.WorkingDirectory = $Carpeta
$acceso.IconLocation = $Icono
$acceso.Description = "Apuntes de clase"
$acceso.Save()
