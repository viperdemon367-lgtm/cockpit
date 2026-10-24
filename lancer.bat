@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Cockpit

python --version >nul 2>&1
if errorlevel 1 goto nopython
goto haspython

:nopython
echo Python n'est pas installé. Installation automatique en cours...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto manual
echo.
echo Python est installé. Ferme cette fenêtre puis relance lancer.bat.
pause
exit /b 0

:manual
echo.
echo Installation automatique impossible. Installe Python 3.12 depuis python.org
echo en cochant "Add Python to PATH", puis relance ce fichier.
start https://www.python.org/downloads/
pause
exit /b 1

:haspython
if exist .venv\Scripts\python.exe goto run
echo Première installation : 1 à 2 minutes...
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip -q
.venv\Scripts\python -m pip install -r requirements.txt -q
if errorlevel 1 goto deps

:run
.venv\Scripts\python run.py
pause
exit /b 0

:deps
echo Échec de l'installation des dépendances. Vérifie ta connexion internet puis relance.
rmdir /s /q .venv
pause
exit /b 1
