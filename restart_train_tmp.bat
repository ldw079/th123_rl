@echo off
taskkill /F /PID 18316 /PID 30032 /PID 33636 /PID 34484 /PID 29712 /PID 50008
timeout /t 3 /nobreak >nul
taskkill /F /PID 27128 /PID 30448 /PID 43692 /PID 41240 2>nul
cd /d %USERPROFILE%\Desktop\workplace\th123_rl
start "th123_train" /min D:\temp\pyenv\python.exe -X utf8 -u run_parallel.py 500
timeout /t 5 /nobreak >nul
start "th123_selfplay_exp" /min cmd /c "D:\temp\pyenv\python.exe -X utf8 -u train_tm.py --char reimu --port 20940 --slot 3 --tps 480 --episodes 500 --ep-timeout 240 --opp marisa --opp suika --suffix _exp > D:\temp\train_reimu_exp.log 2>&1"
echo ALL-RELAUNCHED
