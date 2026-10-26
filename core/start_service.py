"""
FOCUS Service Launcher & Autostart Enforcer
(TARGET / BROTHER'S PC ONLY)

Ensures FOCUS daemon starts automatically on every Windows boot and user logon,
and launches the daemon immediately in the background without any visible console window.
Do NOT run this on your personal developer PC unless you want this PC to be the one controlled!
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


def stop_service():
    """Stops all running instances of FOCUS daemon and watchdog, and removes startup entries."""
    print("[FOCUS Service] Stopping all background daemons...")
    subprocess.run(["taskkill", "/f", "/im", "pythonw.exe"], capture_output=True, check=False)
    setup_startup_entry(enable=False)
    print("[FOCUS Service] Background service stopped and autostart removed.")


def launch_daemon():
    # 1. Enforce dual autostart entries (HKCU Run key + %APPDATA% Startup folder)
    setup_startup_entry(enable=True)

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

    print("[FOCUS Launcher] Launching background daemon on target PC silently...")
    subprocess.run(["wscript.exe", launcher_vbs], check=False)
    time.sleep(2)
    try:
        os.remove(launcher_vbs)
    except Exception:
        pass

    print("[FOCUS Launcher] Daemon started. Verifying status...")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--stop", "--uninstall", "stop"):
        stop_service()
    else:
        launch_daemon()
