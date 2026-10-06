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
echo Synchronisation YouDrive. Le telephone doit etre branche en USB et deverrouille.
".venv\Scripts\python.exe" -m youdrive sync
popd
pause
