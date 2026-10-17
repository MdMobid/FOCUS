"""
FOCUS: Windows Registry Policy Manager
Manages Task Manager lockdown during Focus Mode and Chromium Enterprise Policies.
Uses Python's built-in 'winreg' module with zero external dependencies.
"""

import sys
import winreg
from typing import Optional


def set_task_manager_disabled(disabled: bool) -> bool:
    """
    Enables or disables Windows Task Manager.
    When disabled (1), user cannot open Task Manager to kill processes.
    """
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
        # Open or create key under HKCU
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        value = 1 if disabled else 0
        winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, value)
        winreg.CloseKey(key)
        state_str = "DISABLED" if disabled else "ENABLED"
        print(f"[FOCUS Policy] Windows Task Manager is now {state_str}")
        return True
    except Exception as exc:
        print(f"[FOCUS Policy] Failed to update Task Manager policy: {exc}", file=sys.stderr)
        return False


def register_extension_for_browser(browser: str, extension_id: str, update_url: Optional[str] = None) -> bool:
    """
    Registers an extension in Chromium Enterprise ExtensionInstallForcelist.
    Forces Chrome or Edge to install the extension, prevents uninstallation, and forces Incognito support.
    
    :param browser: 'chrome' or 'edge'
    :param extension_id: 32-character extension ID
    :param update_url: URL for updates (default Google/Edge update service)
    """
    try:
        if browser.lower() == "chrome":
            key_path = r"SOFTWARE\Policies\Google\Chrome\ExtensionInstallForcelist"
            if not update_url:
                update_url = "https://clients2.google.com/service/update2/crx"
        elif browser.lower() == "edge":
            key_path = r"SOFTWARE\Policies\Microsoft\Edge\ExtensionInstallForcelist"
            if not update_url:
                update_url = "https://edge.microsoft.com/extensionproxy/service/update2/crx"
        else:
            return False

        # Value entry format: "<extension_id>;<update_url>"
        entry_value = f"{extension_id};{update_url}"

        # Register in HKEY_LOCAL_MACHINE or HKEY_CURRENT_USER
        for root_hkey in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                key = winreg.CreateKeyEx(root_hkey, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY)
                winreg.SetValueEx(key, "1", 0, winreg.REG_SZ, entry_value)
                winreg.CloseKey(key)
                print(f"[FOCUS Policy] Registered enterprise extension for {browser.capitalize()} in {root_hkey}")
            except PermissionError:
                # If non-elevated, try HKCU
                continue

        return True
    except Exception as exc:
        print(f"[FOCUS Policy] Failed to register extension for {browser}: {exc}", file=sys.stderr)
        return False


def setup_startup_entry(app_path: str, enable: bool = True) -> bool:
    """
    Registers or unregisters FOCUS to auto-start on Windows user logon.
    Uses HKCU Run key for reliable user-level startup.
    """
    try:
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, "FOCUSParentGuard", 0, winreg.REG_SZ, f'"{app_path}"')
            print(f"[FOCUS Policy] Startup entry enabled: {app_path}")
        else:
            try:
                winreg.DeleteValue(key, "FOCUSParentGuard")
                print("[FOCUS Policy] Startup entry removed.")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as exc:
        print(f"[FOCUS Policy] Failed to modify startup registry key: {exc}", file=sys.stderr)
        return False


if __name__ == "__main__":
    print("Testing registry policy module...")
    # Check read capability
    set_task_manager_disabled(False)
