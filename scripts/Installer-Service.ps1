# Installe YouDrive Claimer comme service Windows (NSSM), demarrage automatique, sans fenetre.
param(
    [string]$AdbPath,
    [string]$AdbKey
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$serviceName = 'YouDriveClaimer'

# The service runs as LocalSystem, which has neither this user's PATH nor ~/.android.
if (-not $AdbPath) {
    $found = Get-Command adb -ErrorAction SilentlyContinue
    $AdbPath = if ($found) { $found.Source } else { Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe' }
}
if (-not $AdbKey) {
    $AdbKey = Join-Path $env:USERPROFILE '.android\adbkey'
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
        '-AdbPath', "`"$AdbPath`"", '-AdbKey', "`"$AdbKey`""
    )
    Start-Process powershell -Verb RunAs -ArgumentList $arguments -Wait
    exit
}

$nssm = Join-Path $root 'docs\nssm.exe'
$python = Join-Path $root '.venv\Scripts\python.exe'
foreach ($path in @($nssm, $python)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Fichier absent : $path" }
}
if (-not (Test-Path -LiteralPath $AdbPath)) { Write-Warning "adb introuvable : $AdbPath" }
if (-not (Test-Path -LiteralPath $AdbKey)) { Write-Warning "Cle adb introuvable : $AdbKey" }

$startupLauncher = Join-Path ([Environment]::GetFolderPath('Startup')) 'YouDrive Claimer.vbs'
if (Test-Path -LiteralPath $startupLauncher) { Remove-Item -LiteralPath $startupLauncher }

$logs = Join-Path $root 'data\logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$log = Join-Path $logs 'service.log'

if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
    & $nssm stop $serviceName | Out-Null
} else {
    & $nssm install $serviceName $python | Out-Null
}
& $nssm set $serviceName Application $python | Out-Null
& $nssm set $serviceName AppParameters '-m youdrive ui --no-browser' | Out-Null
& $nssm set $serviceName AppDirectory $root | Out-Null
& $nssm set $serviceName DisplayName 'YouDrive Claimer' | Out-Null
& $nssm set $serviceName Description "Interface locale YouDrive Claimer sur http://127.0.0.1:8765. Aucun message n'est envoye." | Out-Null
& $nssm set $serviceName Start SERVICE_AUTO_START | Out-Null
& $nssm set $serviceName AppEnvironmentExtra 'PYTHONUTF8=1' "YOUDRIVE_ADB=$AdbPath" "ADB_VENDOR_KEYS=$AdbKey" | Out-Null
& $nssm set $serviceName AppStdout $log | Out-Null
& $nssm set $serviceName AppStderr $log | Out-Null
& $nssm set $serviceName AppRotateFiles 1 | Out-Null
& $nssm set $serviceName AppRotateBytes 1048576 | Out-Null
& $nssm set $serviceName AppExit Default Restart | Out-Null
& $nssm set $serviceName AppRestartDelay 10000 | Out-Null
& $nssm start $serviceName | Out-Null

Start-Sleep -Seconds 3
Get-Service -Name $serviceName | Format-Table -AutoSize Name, DisplayName, Status, StartType
Write-Output 'Interface : http://127.0.0.1:8765'
Write-Output "Journal : $log"
Read-Host 'Entree pour fermer'
