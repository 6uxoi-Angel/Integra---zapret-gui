@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0install.bat" --quiet
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" scripts\check_project.py
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" (
  echo.
  echo All project checks passed.
) else (
  echo.
  echo Project checks failed.
)
pause
exit /b %RESULT%
