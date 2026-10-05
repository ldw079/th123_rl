@echo off
chcp 65001 >nul
rem 一键开训(2026-09-21重定向): 旧懒人版(train_rl.py抓屏管线)已归档 _archive\
rem 现行通道 = run_parallel.py 三角色并行(TM锁步, 见 AGENTS.md)
cd /d "%~dp0"
set EPISODES=500
if not "%~1"=="" set EPISODES=%~1
rem 解释器优先级: 便携runtime > D:\temp\pyenv > PATH
set PY=%~dp0runtime\python.exe
if not exist "%PY%" set PY=D:\temp\pyenv\python.exe
if not exist "%PY%" set PY=python
echo [一键开训] %EPISODES%局/角色 · 灵梦20800 魔理沙20810 萃香20820 · tps480
"%PY%" -X utf8 run_parallel.py %EPISODES%
echo.
echo 训练已退出。日志: D:\temp\train_{char}.log · 模型: D:\temp\th123_models\
pause >nul
