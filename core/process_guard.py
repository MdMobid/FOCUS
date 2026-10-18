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


# Core Windows OS and essential development/system processes that must NEVER be terminated
ESSENTIAL_SYSTEM_PROCESSES: Set[str] = {
    # Core OS
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe",
    "dwm.exe", "explorer.exe", "sihost.exe", "taskhostw.exe", "ctfmon.exe",
    "conhost.exe", "audiodg.exe", "searchhost.exe", "shellexperiencehost.exe",
    "startmenuexperiencehost.exe", "textinputhost.exe", "runtimebroker.exe",
    "securityhealthservice.exe", "smartscreen.exe", "spoolsv.exe",
    "workloadssessionhost.exe", "workloadssessionmanager.exe",
    # Session / logon — killing these causes the screen to lock or session to end
    "winlogon.exe", "logonui.exe", "userinit.exe", "usoclient.exe",
    "lsm.exe", "wlrmdr.exe",
    # Networking & Wi-Fi — killing these drops internet connectivity
    "wlanext.exe", "wifisvc.exe", "netsh.exe", "nettcpip.exe",
    "wifioptimizationservice.exe", "wifitaskmgr.exe",
    "dnscache.exe", "iphlpsvc.exe", "nlasvc.exe", "netprofm.exe",
    "nlaapi.dll", "dnsapi.dll",
    "w32tm.exe", "msdtc.exe", "rasman.exe", "rasphone.exe",
    "mobilityextensions.exe", "wcmsvc.exe",
    # Security / Defender / Antivirus
    "msmpeng.exe", "nissrv.exe", "mssecces.exe", "mpcmdrun.exe",
    "antimalwareserviceexecutable.exe", "securityhealthsystray.exe",
    # Windows Update
    "wuauclt.exe", "wusa.exe", "trustedinstaller.exe", "tiworker.exe",
    "updateassistant.exe", "windowsupdatebox.exe",
    # GPU / Display drivers (killing causes black screen)
    "nvvsvc.exe", "nvdisplay.container.exe", "nvspcaps64.exe", "nvsphelper64.exe",
    "igfxtray.exe", "igfxem.exe", "igfxext.exe", "igfxpers.exe",
    "amdow.exe", "radeoninstaller.exe",
    # Audio
    "audiodg.exe", "audiosrv.dll",
    # Dev tools (immune so FOCUS can be managed during dev)
    "antigravity ide.exe", "antigravity.exe", "antigravity-ide.exe",
    "code.exe", "node.exe", "language_server_windows_x64.exe", "pyrefly.exe",
    "cmd.exe", "powershell.exe", "powershell_ise.exe", "pwsh.exe",
    "git.exe", "rg.exe", "bash.exe",
    # Task Scheduler / COM / RPC
    "taskeng.exe", "taskhost.exe", "mstask.exe",
    "rpcss.exe", "rpcsvc.exe", "dcomlaunch.exe",
    "comhost.exe", "dllhost.exe",
}


def get_process_image_path(pid: int) -> str:
    """Returns the full executable file path for a process PID."""
    kernel32 = ctypes.windll.kernel32
    h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h_proc:
        return ""
    buff = ctypes.create_unicode_buffer(MAX_PATH * 2)
    size = wintypes.DWORD(MAX_PATH * 2)
    path = ""
    if kernel32.QueryFullProcessImageNameW(h_proc, 0, buff, ctypes.byref(size)):
        path = buff.value
    kernel32.CloseHandle(h_proc)
    return path


def get_running_processes_with_parent() -> List[Tuple[int, int, str]]:
    """Returns a list of (pid, parent_pid, exe_name) for all active processes."""
    processes = []
    kernel32 = ctypes.windll.kernel32

    h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if h_snap == ctypes.c_void_p(-1).value:
        return processes

    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)

    success = kernel32.Process32FirstW(h_snap, ctypes.byref(entry))
    while success:
        processes.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile))
        success = kernel32.Process32NextW(h_snap, ctypes.byref(entry))

    kernel32.CloseHandle(h_snap)
    return processes


def get_running_processes() -> List[Tuple[int, str]]:
    """Returns a list of (pid, exe_name) for all currently active processes."""
    return [(pid, name) for pid, _, name in get_running_processes_with_parent()]


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

                    processes = get_running_processes_with_parent()

                    # First pass: collect all Antigravity & immune PIDs so their children are also immune
                    immune_pids: Set[int] = {self.own_pid, 0, 4}
                    for pid, ppid, exe_name in processes:
                        exe_lower = exe_name.lower()
                        if "antigravity" in exe_lower or exe_lower in ESSENTIAL_SYSTEM_PROCESSES:
                            immune_pids.add(pid)

                    # Second pass: check and terminate unauthorized apps
                    for pid, ppid, exe_name in processes:
                        if pid in immune_pids or pid <= 4 or pid == self.own_pid:
                            continue

                        # If parent process is immune (e.g. Antigravity IDE terminal/subtask), protect it
                        if ppid in immune_pids:
                            immune_pids.add(pid)
                            continue

                        exe_lower = exe_name.lower()
                        if "antigravity" in exe_lower or exe_lower in ESSENTIAL_SYSTEM_PROCESSES:
                            immune_pids.add(pid)
                            continue

                        # Check if process executable path belongs to Antigravity, .antigravity, or .gemini
                        img_path = get_process_image_path(pid).lower()
                        if "antigravity" in img_path or ".antigravity" in img_path or ".gemini" in img_path:
                            immune_pids.add(pid)
                            continue

                        # Check if process is explicitly whitelisted
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
