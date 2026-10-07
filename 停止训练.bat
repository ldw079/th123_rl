@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== 停止训练 (树杀全部fleet/单实例/剥削者进程) =====
D:\temp\pyenv\python.exe -X utf8 tools\train_start.py --stop
pause
