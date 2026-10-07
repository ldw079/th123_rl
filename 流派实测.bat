@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== 流派/系别/逐SC matchup 实测 =====
echo  1=L1流派  2=L2必杀系别  3=L3逐SC(reimu)  4=L3系统卡组
choice /c 1234 /n /m "选择模式: "
if errorlevel 4 goto sys
if errorlevel 3 goto sc
if errorlevel 2 goto skillset
goto arch
:arch
D:\temp\pyenv\python.exe -X utf8 tools\deck_matchup.py --games 3
goto end
:skillset
D:\temp\pyenv\python.exe -X utf8 tools\deck_matchup.py --games 3 --mode skillset
goto end
:sc
D:\temp\pyenv\python.exe -X utf8 tools\deck_matchup.py --games 2 --mode sc --chars reimu
goto end
:sys
D:\temp\pyenv\python.exe -X utf8 tools\deck_matchup.py --games 3 --mode sys
goto end
:end
pause
