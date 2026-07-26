@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
chcp 65001 >nul

set "QUIET=0"
if /I "%~1"=="--quiet" set "QUIET=1"
set "PYTHON_RESULT=%TEMP%\zapret-gui-python-%RANDOM%-%RANDOM%.txt"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_python.ps1" -InstallIfMissing > "%PYTHON_RESULT%"
if errorlevel 1 goto :python_error
set /p "PYTHON_EXE="<"%PYTHON_RESULT%"
del /q "%PYTHON_RESULT%" >nul 2>nul

if not defined PYTHON_EXE goto :python_error
if not exist "%PYTHON_EXE%" goto :python_error

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import struct,sys; assert struct.calcsize('P') * 8 == 64 and sys.version_info[0] == 3 and sys.version_info[1] in range(10, 15)" >nul 2>nul
  if errorlevel 1 (
    echo Existing virtual environment is incompatible. Recreating it...
    rmdir /s /q ".venv"
    if exist ".venv" (
      echo Could not remove the existing virtual environment. Close Integra and try again.
      goto :error
    )
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment with "%PYTHON_EXE%"...
  "%PYTHON_EXE%" -m venv ".venv"
  if errorlevel 1 goto :error
)

set "VENV_PY=.venv\Scripts\python.exe"
"%VENV_PY%" -c "from PySide6.QtWidgets import QApplication; import psutil" >nul 2>nul
if not errorlevel 1 goto :ready

"%VENV_PY%" -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
if errorlevel 1 goto :error
rem A partial PySide6 directory can still import as a namespace package. Reinstall
rem the runtime when the QtWidgets smoke check above fails so it is repaired too.
"%VENV_PY%" -m pip install --disable-pip-version-check --force-reinstall --no-cache-dir --prefer-binary -r requirements.txt
if errorlevel 1 goto :error

:ready
> ".venv\.ready" echo Integra dependencies installed.

echo.
echo Installation completed. Run run.bat.
echo Ustanovka zavershena. Zapustite run.bat.
if "%QUIET%"=="0" pause
exit /b 0

:python_error
del /q "%PYTHON_RESULT%" >nul 2>nul
echo.
echo Could not find or install a supported 64-bit Python 3.10-3.14.
echo Ne udalos nayti ili ustanovit podderzhivaemuyu 64-bit versiyu Python 3.10-3.14.
echo Check Internet access, Windows Package Manager, antivirus and proxy settings.
if "%QUIET%"=="0" pause
exit /b 1

:error
echo.
echo Dependency installation failed. See the messages above.
echo Ustanovka zavisimostey ne udalas. Proverte soobshcheniya vyshe.
if "%QUIET%"=="0" pause
exit /b 1
