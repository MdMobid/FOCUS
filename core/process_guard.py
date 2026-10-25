"""
FOCUS: Active Window Monitor
Reports the active foreground window title and application name to the parent dashboard.
Implemented using pure Python ctypes (Win32 user32/kernel32) with ZERO external dependencies.
"""

import ctypes
from ctypes import wintypes
from typing import Dict, List, Tuple

# Win32 Constants
TH32CS_SNAPPROCESS = 0x00000002
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
        processes.append((entry.th32ProcessID, entry.szExeFile))
        success = kernel32.Process32NextW(h_snap, ctypes.byref(entry))

    kernel32.CloseHandle(h_snap)
    return processes


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
