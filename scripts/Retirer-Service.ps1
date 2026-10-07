# Arrete et supprime le service Windows YouDrive Claimer.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$serviceName = 'YouDriveClaimer'

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -Verb RunAs -Wait -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`""
    )
    exit
}

$nssm = Join-Path $root 'docs\nssm.exe'
if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
    & $nssm stop $serviceName | Out-Null
    & $nssm remove $serviceName confirm | Out-Null
    Write-Output "Service retire : $serviceName"
} else {
    Write-Output "Aucun service $serviceName."
}
Read-Host 'Entree pour fermer'
