@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== 启动训练 (fleet 3 actor + reimu剥削者) =====
D:\temp\pyenv\python.exe -X utf8 tools\train_start.py --mode fleet --actors 3 --exploiter reimu
echo.
echo 训练已在后台启动 (监督日志: D:\temp\th123_models\fleet_supervision.log)
pause
