"""
FOCUS: Anti-Kill Sentinel Watchdog
Monitors the primary FOCUS daemon process.
If the primary daemon is terminated or killed via Task Manager,
the watchdog immediately relaunches it within 100 milliseconds.
"""

import ctypes
import os
import subprocess
import sys
import time

SYNCHRONIZE = 0x00100000
INFINITE = 0xFFFFFFFF


def monitor_and_resurrect(parent_pid: int, target_script: str):
    kernel32 = ctypes.windll.kernel32
    h_process = kernel32.OpenProcess(SYNCHRONIZE, False, parent_pid)

    if not h_process:
        print(f"[FOCUS Watchdog] Unable to acquire handle for PID {parent_pid}")
        return

    print(f"[FOCUS Watchdog] Monitoring primary daemon PID {parent_pid}...")
    # Block until target process terminates
    kernel32.WaitForSingleObject(h_process, INFINITE)
    kernel32.CloseHandle(h_process)

    print("[FOCUS Watchdog] Primary daemon terminated! Resurrecting immediately...")
    python_exe = sys.executable
    # Relaunch primary daemon in background
    subprocess.Popen([python_exe, target_script], creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        p_pid = int(sys.argv[1])
        script_path = sys.argv[2]
        monitor_and_resurrect(p_pid, script_path)
    else:
        print("Usage: watchdog.py <parent_pid> <target_script_path>")
