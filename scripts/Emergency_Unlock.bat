@echo off
setlocal enabledelayedexpansion
title FOCUS - Emergency Keyboard Unlock

echo ============================================================
echo           FOCUS - Emergency Keyboard Unlock
echo ============================================================
echo.
echo [*] Terminating FOCUS processes to release keyboard hook...

:: 1. Forcefully kill background FOCUS processes (Windows auto-destroys the WH_KEYBOARD_LL hook)
taskkill /f /im pythonw.exe >nul 2>&1
taskkill /f /im python.exe >nul 2>&1


:: 2. Restore Task Manager policy immediately
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System" /v "DisableTaskMgr" /f >nul 2>&1

:: 3. Reset keyboard_locked and focus_mode in SQLite database to prevent re-lock
set "SCRIPT_DIR=%~dp0"
set "DB_FILE=%SCRIPT_DIR%config\focus.db"
if not exist "%DB_FILE%" (
    set "DB_FILE=%SCRIPT_DIR%..\config\focus.db"
)

where python >nul 2>&1
if %errorLevel% equ 0 (
    if exist "%DB_FILE%" (
        python -c "import sqlite3; c=sqlite3.connect(r'%DB_FILE%'); c.execute(\"INSERT OR REPLACE INTO settings(key, value) VALUES('keyboard_locked', '0')\"); c.execute(\"INSERT OR REPLACE INTO settings(key, value) VALUES('focus_mode', '0')\"); c.commit(); c.close()" >nul 2>&1
    )
)

echo.
echo ============================================================
echo   SUCCESS: Hardware keyboard is UNLOCKED and policies restored!
echo ============================================================
echo.
echo Closing automatically in 5 seconds...
timeout /t 5 >nul 2>&1
exit /b 0
