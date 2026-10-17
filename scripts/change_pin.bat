@echo off
title FOCUS - Change Master PIN
set PROJECT_DIR=%~dp0..
pushd "%PROJECT_DIR%"

if exist ".venv\Scripts\python.exe" (
    set PYTHON_BIN=".venv\Scripts\python.exe"
) else (
    set PYTHON_BIN=python
)

%PYTHON_BIN% scripts\change_pin.py
popd
pause
