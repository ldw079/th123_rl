@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== 全量审计 (健康/红线/日志/COM难度/fleet状态) =====
D:\temp\pyenv\python.exe -X utf8 tools\audit_all.py
pause
