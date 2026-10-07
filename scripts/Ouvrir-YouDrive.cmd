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
echo YouDrive Claimer. Le navigateur va s'ouvrir.
echo Si cette fenetre reste ouverte, la fermer arrete l'interface.
".venv\Scripts\python.exe" -m youdrive ui
if errorlevel 1 pause
popd
