@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=D:\temp\pyenv\python.exe
if not exist "%PY%" set PY=python
echo ==== Start ====
"%PY%" -X utf8 tools\train_start.py --mode fleet --actors 3 --tps 360
pause
