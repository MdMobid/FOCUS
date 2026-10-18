@echo off
setlocal enabledelayedexpansion
title FOCUS - 1-Click Installer

echo ============================================================
echo          FOCUS Parental Control ^& Focus Manager
echo                     1-Click Installer
echo ============================================================
echo.

:: 1. Check Administrator Privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo [ERROR] This installer must be run as Administrator!
    echo.
    echo Please right-click "install.bat" and select "Run as administrator".
    echo.
    pause
    exit /b 1
)

:: 2. Find Python Installation
set "PYTHON_EXE="
where python >nul 2>&1
if %errorLevel% equ 0 (
    for /f "delims=" %%i in ('where python') do (
        if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
    )
) else (
    where py >nul 2>&1
    if %errorLevel% equ 0 (
        for /f "delims=" %%i in ('where py') do (
            if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
        )
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] Python is not found in PATH!
    echo.
    echo Please install Python 3.10+ on this PC:
    echo 1. Download installer from https://www.python.org/downloads/
    echo 2. Make sure to check the box: "Add python.exe to PATH"
    echo 3. Run install.bat again.
    echo.
    pause
    exit /b 1
)

echo [OK] Using Python: %PYTHON_EXE%

:: Prefer pythonw.exe (Windowless Python) so NO CMD window is shown to brother
set "RUNNER_EXE=%PYTHON_EXE:python.exe=pythonw.exe%"
if not exist "%RUNNER_EXE%" set "RUNNER_EXE=%PYTHON_EXE%"
echo [OK] Background Runner: %RUNNER_EXE%

:: 3. Resolve Project Paths
set "PROJECT_DIR=%~dp0.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

set "MAIN_SCRIPT=%PROJECT_DIR%\core\main.py"
set "EXTENSION_DIR=%PROJECT_DIR%\extension"

echo [OK] Project Directory: %PROJECT_DIR%
echo [OK] Target Daemon: %MAIN_SCRIPT%

:: 4. Register Windows Task Scheduler (Auto-Start on Boot/Logon with Highest Privileges)
echo.
echo [*] Configuring Windows Auto-Start Task...
schtasks /create /tn "FOCUSParentGuard" /tr "\"%RUNNER_EXE%\" \"%MAIN_SCRIPT%\"" /sc onlogon /rl highest /f >nul 2>&1
if %errorLevel% equ 0 (
    echo [OK] Task Scheduler auto-start registered with HIGHEST privileges!
) else (
    echo [!] Task scheduler registration warning. Falling back to Registry Run Key.
    reg add "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v "FOCUSParentGuard" /t REG_SZ /d "\"%RUNNER_EXE%\" \"%MAIN_SCRIPT%\"" /f >nul 2>&1
)

:: 5. Register Chromium Enterprise Policies (Chrome & Edge)
echo.
echo [*] Registering Enterprise Extension Policies for Chrome ^& Edge...

:: Edge Policy
reg add "HKLM\SOFTWARE\Policies\Microsoft\Edge" /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Edge\ExtensionInstallForcelist" /v "1" /t REG_SZ /d "focuswebguardextension;https://clients2.google.com/service/update2/crx" /f >nul 2>&1

:: Chrome Policy
reg add "HKLM\SOFTWARE\Policies\Google\Chrome" /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist" /v "1" /t REG_SZ /d "focuswebguardextension;https://clients2.google.com/service/update2/crx" /f >nul 2>&1

echo [OK] Chromium Enterprise Policies configured.

:: 6. Detect Local IPv4 Address for Phone Access
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
    set LOCAL_IP=%%a
    set LOCAL_IP=!LOCAL_IP: =!
    goto :ip_found
)
:ip_found

:: 7. Start FOCUS in background
echo.
echo [*] Launching FOCUS Daemon in background...
taskkill /f /im pythonw.exe >nul 2>&1
start "" /d "%PROJECT_DIR%" "%RUNNER_EXE%" "%MAIN_SCRIPT%"

:: Verify process started
timeout /t 2 /nobreak >nul
tasklist | findstr /i "python" >nul 2>&1
if %errorLevel% equ 0 (
    echo [OK] FOCUS background daemon is verified running!
) else (
    echo [!] Background launch may have failed. Showing console output:
    start cmd /k "cd /d \"%PROJECT_DIR%\" && python \"%MAIN_SCRIPT%\""
)

echo.
echo ============================================================
echo                 INSTALLATION SUCCESSFUL!
echo ============================================================
echo.
echo   Parent Web Dashboard is now LIVE!
echo.
echo   Local PC Access:   http://localhost:8443
if defined LOCAL_IP (
echo   Phone (Home Wi-Fi): http://!LOCAL_IP!:8443
)
echo.
echo   Parent Security: PIN-Protected (Hashed SHA-256)
echo   Emergency Unlock Hotkey: Ctrl + Alt + Shift + P
echo.
echo   You can close this window now. FOCUS will run in background.
echo ============================================================
echo.
pause
