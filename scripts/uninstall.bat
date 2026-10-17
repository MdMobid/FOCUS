@echo off
setlocal enabledelayedexpansion
title FOCUS - Uninstaller

echo ============================================================
echo          FOCUS Parental Control ^& Focus Manager
echo                        Uninstaller
echo ============================================================
echo.

:: 1. Check Administrator Privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] This uninstaller must be run as Administrator!
    pause
    exit /b 1
)

:: 2. Prompt for Parent PIN Verification
set /p ENTERED_PIN="Enter Parent Master PIN to authorize uninstallation: "

set PROJECT_DIR=%~dp0..
pushd "%PROJECT_DIR%"
set PROJECT_DIR=%CD%
popd

python -c "import sys; sys.path.insert(0, r'%PROJECT_DIR%\core'); from config_manager import config; sys.exit(0 if config.verify_pin('%ENTERED_PIN%') else 1)"
if %errorLevel% neq 0 (
    echo.
    echo [DENIED] Invalid Parent PIN! Uninstallation aborted.
    pause
    exit /b 1
)

echo.
echo [VERIFIED] Master PIN confirmed. Proceeding with clean removal...

:: 3. Terminate running FOCUS processes
echo [*] Stopping background services...
taskkill /f /im python.exe /fi "WINDOWTITLE eq FOCUS*" >nul 2>&1

:: 4. Remove Task Scheduler task
echo [*] Removing Task Scheduler startup task...
schtasks /delete /tn "FOCUSParentGuard" /f >nul 2>&1
reg delete "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v "FOCUSParentGuard" /f >nul 2>&1

:: 5. Restore Task Manager Policy
echo [*] Restoring Windows policies...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v "DisableTaskMgr" /t REG_DWORD /d 0 /f >nul 2>&1

:: 6. Clean Chromium Extension Policies
reg delete "HKLM\SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist" /v "1" /f >nul 2>&1
reg delete "HKLM\SOFTWARE\Policies\Microsoft\Edge\ExtensionInstallForcelist" /v "1" /f >nul 2>&1

echo.
echo ============================================================
echo               UNINSTALLATION COMPLETE
echo ============================================================
echo FOCUS has been cleanly uninstalled and all policies restored.
echo.
pause
