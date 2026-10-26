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

:: 3. Terminate running FOCUS processes and Watchdog
echo [*] Stopping background services and watchdog...
taskkill /f /im pythonw.exe >nul 2>&1
taskkill /f /im python.exe >nul 2>&1

:: 4. Remove Task Scheduler startup task & Registry Run keys & Startup folder
echo [*] Removing Task Scheduler startup task & autostart hooks...
schtasks /delete /tn "FOCUSParentGuard" /f >nul 2>&1
reg delete "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v "FOCUSParentGuard" /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "FOCUSParentGuard" /f >nul 2>&1
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\FOCUS_Startup.vbs" >nul 2>&1

:: 5. Restore Task Manager Policy
echo [*] Restoring Windows policies & Task Manager...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v "DisableTaskMgr" /f >nul 2>&1

:: 6. Clean Chromium Extension Policies
echo [*] Removing Chromium enterprise policies...
reg delete "HKLM\SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist" /v "1" /f >nul 2>&1
reg delete "HKLM\SOFTWARE\Policies\Microsoft\Edge\ExtensionInstallForcelist" /v "1" /f >nul 2>&1

echo.
echo ============================================================
echo               UNINSTALLATION COMPLETE
echo ============================================================
echo FOCUS background services stopped and all policies restored!
echo.
set /p PURGE_FILES="Do you also want to completely delete the FOCUS folder and all database files? [Y/N]: "
if /i "!PURGE_FILES!"=="Y" (
    echo [*] Completely deleting FOCUS directory...
    start "" cmd /c "timeout /t 2 /nobreak >nul & rmdir /s /q \"%PROJECT_DIR%\""
    echo [OK] Entire folder will be permanently removed in 2 seconds.
) else (
    echo [OK] Project files preserved on disk.
)
echo.
pause
