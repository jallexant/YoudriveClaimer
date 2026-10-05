@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
pushd "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo Environnement Python absent. Voir README.md.
    pause
    popd
    exit /b 1
)
echo Synchronisation YouDrive. Une page de connexion s'ouvre si la session a expire.
".venv\Scripts\python.exe" -m youdrive sync
popd
pause
