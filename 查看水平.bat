@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=D:\temp\pyenv\python.exe
if not exist "%PY%" set PY=python
"%PY%" -X utf8 tools\status_dashboard.py --quick
echo.
"%PY%" -X utf8 tools\charge_usage_report.py
pause
