@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Fabrique dist\Cockpit.exe (Windows uniquement)
if not exist .venv\Scripts\python.exe goto first
.venv\Scripts\python -m pip install pyinstaller -q
.venv\Scripts\python -m PyInstaller --noconfirm --onefile --name Cockpit --add-data "static;static" run.py
if exist distribution.json copy /y distribution.json dist\ >nul
echo.
echo Terminé : dist\Cockpit.exe
echo Distribue ce .exe, avec distribution.json à côté si tu en as un.
pause
exit /b 0
:first
echo Lance d'abord lancer.bat une fois.
pause
