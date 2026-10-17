"""
FOCUS: Process Guardian & Whitelist Enforcer
Monitors active processes and terminates non-whitelisted applications during Focus Mode.
Reports the active foreground window and application title to the parent dashboard.
Implemented using pure Python ctypes (Win32 kernel32/user32) with ZERO external dependencies.
"""

import ctypes
from ctypes import wintypes
import os
import sys
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

# Win32 Constants
TH32CS_SNAPPROCESS = 0x00000002
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MAX_PATH = 260


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    ]


# Core Windows OS processes that must never be terminated
ESSENTIAL_SYSTEM_PROCESSES: Set[str] = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe",
    "dwm.exe", "explorer.exe", "sihost.exe", "taskhostw.exe", "ctfmon.exe",
    "conhost.exe", "audiodg.exe", "searchhost.exe", "shellexperiencehost.exe",
    "startmenuexperiencehost.exe", "textinputhost.exe", "runtimebroker.exe",
    "securityhealthservice.exe", "smartscreen.exe", "spoolsv.exe"
}


def get_running_processes() -> List[Tuple[int, str]]:
    """Returns a list of (pid, exe_name) for all currently active processes."""
    processes = []
    kernel32 = ctypes.windll.kernel32

    h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if h_snap == ctypes.c_void_p(-1).value:
        return processes

    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)

    success = kernel32.Process32FirstW(h_snap, ctypes.byref(entry))
    while success:
        exe_name = entry.szExeFile
        pid = entry.th32ProcessID
        processes.append((pid, exe_name))
        success = kernel32.Process32NextW(h_snap, ctypes.byref(entry))

    kernel32.CloseHandle(h_snap)
    return processes


def terminate_process_by_pid(pid: int) -> bool:
    """Terminates a process by its PID using TerminateProcess."""
    kernel32 = ctypes.windll.kernel32
    h_proc = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not h_proc:
        return False
    result = kernel32.TerminateProcess(h_proc, 1)
    kernel32.CloseHandle(h_proc)
    return bool(result)


def get_active_window_info() -> Dict[str, str]:
    """
    Returns the title and process name of the current foreground active window.
    Useful for parent live monitoring on the web dashboard.
    """
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return {"app": "Desktop", "title": "Idle"}

    # Window title
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    window_title = buff.value or "Active Window"

    # Process ID & Name
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    app_name = "Unknown"
    for p_pid, p_name in get_running_processes():
        if p_pid == pid.value:
            app_name = p_name
            break

    return {"app": app_name, "title": window_title, "pid": str(pid.value)}


class ProcessGuardian:
    def __init__(self, config_manager):
        self.config = config_manager
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self.own_pid = os.getpid()

    def _guardian_loop(self):
        print("[FOCUS Guardian] Process guardian background thread started.")
        while not self._stop_event.is_set():
            try:
                focus_active = self.config.get("focus_mode", False)
                expires_at = self.config.get("focus_expires_at", 0)

                # Check Focus Mode Timer auto-expiry
                if focus_active and expires_at > 0 and time.time() >= expires_at:
                    print("[FOCUS Guardian] Focus Mode duration has expired. Disabling.")
                    self.config.set("focus_mode", False)
                    self.config.set("focus_expires_at", 0)
                    focus_active = False

                if focus_active:
                    allowed_apps_raw = self.config.get("allowed_apps", [])
                    allowed_set = {app.strip().lower() for app in allowed_apps_raw}

                    # Always allow own process and python
                    allowed_set.add("python.exe")
                    allowed_set.add("pythonw.exe")
                    allowed_set.add("focus.exe")

                    processes = get_running_processes()
                    for pid, exe_name in processes:
                        if pid == self.own_pid or pid <= 4:
                            continue

                        exe_lower = exe_name.lower()
                        if exe_lower in ESSENTIAL_SYSTEM_PROCESSES:
                            continue

                        # Check if process is whitelisted
                        if exe_lower not in allowed_set:
                            # Terminate unauthorized application
                            if terminate_process_by_pid(pid):
                                print(f"[FOCUS Guardian] Terminated unauthorized app: {exe_name} (PID: {pid})")

            except Exception as exc:
                print(f"[FOCUS Guardian] Loop error: {exc}", file=sys.stderr)

            # Sleep 1 second between scans
            time.sleep(1.0)

    def start(self):
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._guardian_loop, daemon=True)
        self._worker_thread.start()

    def stop(self):
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=1.5)


if __name__ == "__main__":
    from config_manager import config
    guardian = ProcessGuardian(config)
    print("Active Window Info:", get_active_window_info())
    print("Running process count:", len(get_running_processes()))
