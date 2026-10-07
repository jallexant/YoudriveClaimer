# Retire le demarrage automatique de YouDrive Claimer.
$ErrorActionPreference = 'Stop'
$startup = [Environment]::GetFolderPath('Startup')
$launcher = Join-Path $startup 'YouDrive Claimer.vbs'
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Aucun lanceur trouve : $launcher"
}
Remove-Item -LiteralPath $launcher
Write-Output "Lanceur retire : $launcher"
