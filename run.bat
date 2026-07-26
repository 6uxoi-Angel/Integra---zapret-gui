@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" goto :install
if not exist ".venv\.ready" goto :install
".venv\Scripts\python.exe" -c "from PySide6.QtWidgets import QApplication; import psutil" >nul 2>nul
if errorlevel 1 goto :install
goto :launch

:install
echo Preparing Integra dependencies...
call "%~dp0install.bat" --quiet
if errorlevel 1 (
  echo.
  echo Startup preparation failed.
  pause
  exit /b 1
)

:launch
wscript.exe //nologo "%~dp0run.vbs" --show
exit /b %errorlevel%
