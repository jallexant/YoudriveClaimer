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
echo Interface YouDrive. Le navigateur va s'ouvrir. Fermez cette fenetre pour quitter.
".venv\Scripts\python.exe" -m youdrive ui
if errorlevel 1 pause
popd
