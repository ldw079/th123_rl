@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "%TEMP%\pyenv\python.exe" (
  "%TEMP%\pyenv\python.exe" loop.py %*
  goto :done
)
py -3 --version >nul 2>nul
if not errorlevel 1 (
  py -3 loop.py %*
  goto :done
)
echo [ERROR] No usable Python found. Install Python 3.8+, or put a portable one at %%TEMP%%\pyenv\
goto :done
:done
if errorlevel 1 (
  echo.
  echo [STOPPED] See error above, or check logs\last_run.log . Press any key to close...
  pause >nul
)
