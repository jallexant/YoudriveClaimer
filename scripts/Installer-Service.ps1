# Place YouDrive Claimer in the Windows Startup folder for this session.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) {
    throw "Environnement Python absent : $pythonw"
}
$startup = [Environment]::GetFolderPath('Startup')
$launcher = Join-Path $startup 'YouDrive Claimer.vbs'
$vbs = @(
    'Set shell = CreateObject("WScript.Shell")'
    ('shell.CurrentDirectory = "{0}"' -f $root)
    'WScript.Sleep 20000'
    ('shell.Run """{0}"" -m youdrive ui", 0, False' -f $pythonw)
) -join "`r`n"
Set-Content -LiteralPath $launcher -Value $vbs -Encoding ASCII
Write-Output "Lanceur enregistre : $launcher"
Write-Output "YouDrive Claimer demarre 20 secondes apres l'ouverture de session."
