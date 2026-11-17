@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo =========================================================
echo      RSR SmartStock - Enterprise WMS Launch System
echo =========================================================
echo.

:: 1. Check if virtual environment already exists
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    goto :RunApp
)

:: 2. Find system python to create virtual environment
set "FOUND_PYTHON="

:: Try standard PATH commands
where py >nul 2>&1
if !errorlevel! equ 0 (
    set "FOUND_PYTHON=py"
    goto :CreateVenv
)

where python >nul 2>&1
if !errorlevel! equ 0 (
    set "FOUND_PYTHON=python"
    goto :CreateVenv
)

:: Try specific known Windows paths
if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    set "FOUND_PYTHON=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
    goto :CreateVenv
)

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if exist "%%D\python.exe" (
        set "FOUND_PYTHON=%%D\python.exe"
        goto :CreateVenv
    )
)

for /d %%D in ("C:\Python*") do (
    if exist "%%D\python.exe" (
        set "FOUND_PYTHON=%%D\python.exe"
        goto :CreateVenv
    )
)

if "!FOUND_PYTHON!"=="" (
    echo [ERROR] Python was not found on your system.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo or ensure Python is added to your Windows PATH environment variable.
    pause
    exit /b 1
)

:CreateVenv
echo [INFO] Creating Python virtual environment using "!FOUND_PYTHON!"...
"!FOUND_PYTHON!" -m venv .venv
if !errorlevel! neq 0 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)
set "PYTHON_EXE=.venv\Scripts\python.exe"

:RunApp
echo [INFO] Verifying dependencies...
"!PYTHON_EXE!" -m pip install -r requirements.txt --quiet

echo.
echo =========================================================
echo  RSR SmartStock is starting up!
echo.
echo  Access URL: http://127.0.0.1:5000
echo.
echo  Default Demo Logins:
echo    - Administrator: admin   / admin123  (Full system control)
echo    - Manager:       manager / manager123 (Inventory & Reports)
echo    - Staff:         staff   / staff123   (Scanner & Operations)
echo.
echo  Press CTRL + C in this terminal window to stop the server.
echo =========================================================
echo.

start "" "http://127.0.0.1:5000"
"!PYTHON_EXE!" app.py
pause
