@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=D:\temp\pyenv\python.exe
if not exist "%PY%" set PY=python
echo ==== Full Audit ====
"%PY%" -X utf8 tools\audit_all.py
pause
