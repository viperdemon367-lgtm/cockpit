@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe goto first
echo === Tests du moteur, hors ligne ===
.venv\Scripts\python -m pytest -q
echo.
echo === Vérification en conditions réelles ===
.venv\Scripts\python -m app.selfcheck
pause
exit /b 0
:first
echo Lance d'abord lancer.bat une fois.
pause
