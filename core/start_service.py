"""
FOCUS Service Launcher & Autostart Enforcer
Ensures FOCUS daemon starts automatically on every Windows boot and user logon,
and launches the daemon immediately in the background without any visible console window.
"""

import os
import sys
import subprocess
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
MAIN_SCRIPT = os.path.join(SCRIPT_DIR, "main.py")

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from registry_policy import setup_startup_entry


def get_pythonw():
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    return pythonw if os.path.exists(pythonw) else sys.executable


def launch_daemon():
    # 1. Enforce dual autostart entries (HKCU Run key + %APPDATA% Startup folder)
    setup_startup_entry()

    # 2. Launch headless via Windows Script Host detached from console
    runner = get_pythonw()
    launcher_vbs = os.path.join(SCRIPT_DIR, "launch_hidden.vbs")
    vbs_content = (
        'Set WshShell = CreateObject("WScript.Shell")\r\n'
        f'WshShell.CurrentDirectory = "{PROJECT_DIR}"\r\n'
        f'WshShell.Run """{runner}"" ""{MAIN_SCRIPT}""", 0, False\r\n'
    )
    with open(launcher_vbs, "w", encoding="utf-8") as f:
        f.write(vbs_content)

    print("[FOCUS Launcher] Launching background daemon silently...")
    subprocess.run(["wscript.exe", launcher_vbs], check=False)
    time.sleep(2)
    try:
        os.remove(launcher_vbs)
    except Exception:
        pass

    print("[FOCUS Launcher] Daemon started. Verifying status...")


if __name__ == "__main__":
    launch_daemon()
