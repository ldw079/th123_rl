@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=D:\temp\pyenv\python.exe
if not exist "%PY%" set PY=python
echo ==== TH123 RL One-Click ====
"%PY%" -X utf8 tools\launcher.py
