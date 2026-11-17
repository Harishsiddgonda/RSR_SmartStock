@echo off
setlocal
cd /d "%~dp0"

echo =========================================================
echo       RSR SmartStock - Push to GitHub Repository
echo =========================================================
echo.

set /p REPO_URL="Enter your GitHub Repository URL (e.g. https://github.com/Harishsiddgonda/RSR_SmartStock.git): "

if "%REPO_URL%"=="" (
    echo [ERROR] No repository URL entered.
    pause
    exit /b 1
)

echo [INFO] Configuring git remote origin...
git remote remove origin 2>nul
git remote add origin %REPO_URL%

echo [INFO] Renaming branch to main...
git branch -M main

echo [INFO] Pushing code to GitHub...
git push -u origin main

if %ERRORLEVEL% equ 0 (
    echo.
    echo =========================================================
    echo  SUCCESS! All code has been pushed to GitHub!
    echo =========================================================
) else (
    echo.
    echo [ERROR] Push failed. If authentication failed, ensure you have
    echo created a Personal Access Token or signed in with GitHub CLI.
)

pause
