@echo off
setlocal EnableExtensions
cd /d "%~dp0"

call "%~dp0install.bat" --quiet
if errorlevel 1 exit /b 1

set "VENV_PY=.venv\Scripts\python.exe"
"%VENV_PY%" -c "import PyInstaller; from PySide6.QtWidgets import QApplication; import psutil" >nul 2>nul
if errorlevel 1 (
  "%VENV_PY%" -m pip install --disable-pip-version-check --prefer-binary -r requirements-dev.txt
  if errorlevel 1 goto :error
)

"%VENV_PY%" scripts\check_project.py
if errorlevel 1 goto :error

"%VENV_PY%" scripts\build_app.py --arch x64
if errorlevel 1 goto :error

echo.
echo Build ready in ..\app\Integra\.
pause
exit /b 0

:error
echo.
echo Build failed.
pause
exit /b 1
