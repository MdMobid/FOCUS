"""
FOCUS: Installed Applications Scanner
Scans the Windows Registry to enumerate software installed on the PC.
Extracts application names, publishers, and target executable names (.exe).
Filters out core OS daemons, runtimes, .NET/Visual C++ redistributables,
and developer environment tools.
Implemented purely with Python standard library (winreg, os, sys).
"""

import os
import re
import sys
import winreg
from typing import Dict, List, Set

# Substrings in DisplayName that identify system updates, redistributables, or internal dev tools
SKIP_NAME_SUBSTRINGS = (
    "update for windows", "security update", "hotfix", "service pack",
    "windows software development kit", "windows driver package",
    "microsoft .net", ".net runtime", ".net host", ".net framework",
    "microsoft visual c++", "visual c++ 20",
    "microsoft asp.net",
    "microsoft edge webview",
    "meeting add-in",
    "desktop runtime",
    "compatibility fix database",
    "maintenance service",
    "antigravity",
    "pyrefly",
)

# Core OS processes that must never be presented as blockable/whitelisted apps
SYSTEM_EXES = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe",
    "dwm.exe", "explorer.exe", "sihost.exe", "taskhostw.exe", "ctfmon.exe",
    "conhost.exe", "audiodg.exe", "searchhost.exe", "shellexperiencehost.exe",
    "startmenuexperiencehost.exe", "textinputhost.exe", "runtimebroker.exe",
    "securityhealthservice.exe", "smartscreen.exe", "spoolsv.exe",
    "winlogon.exe", "logonui.exe", "userinit.exe", "usoclient.exe",
    "msmpeng.exe", "nissrv.exe", "wuauclt.exe", "trustedinstaller.exe",
    "antigravity.exe", "node.exe", "python.exe", "pythonw.exe",
}


def get_installed_apps() -> List[Dict[str, str]]:
    """
    Enumerates installed user applications from Windows Registry.
    Filters out core OS daemons, runtimes, .NET/Visual C++ redistributables,
    and developer environment tools.
    """
    apps: List[Dict[str, str]] = []
    seen_names: Set[str] = set()

    registry_paths = [
        # 64-bit Machine-wide
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_WOW64_64KEY),
        # 32-bit on 64-bit Windows
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_WOW64_32KEY),
        # Current User Software (e.g. Chrome, VS Code, Discord)
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall", 0),
    ]

    for root_hkey, subkey_path, flags in registry_paths:
        try:
            with winreg.OpenKey(root_hkey, subkey_path, 0, winreg.KEY_READ | flags) as key:
                num_subkeys = winreg.QueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as app_key:
                            # Skip system components marked by Windows
                            try:
                                is_sys, _ = winreg.QueryValueEx(app_key, "SystemComponent")
                                if is_sys == 1:
                                    continue
                            except (FileNotFoundError, OSError):
                                pass

                            # Read DisplayName
                            try:
                                display_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                display_name = str(display_name).strip()
                            except (FileNotFoundError, OSError):
                                continue

                            if not display_name or len(display_name) < 2:
                                continue

                            name_lower = display_name.lower()

                            # Filter KB patches and runtime redistributables
                            if (name_lower.startswith("kb") and name_lower[2:8].isdigit()) or any(s in name_lower for s in SKIP_NAME_SUBSTRINGS):
                                continue

                            if name_lower in seen_names:
                                continue

                            # Read Publisher
                            publisher = ""
                            try:
                                publisher, _ = winreg.QueryValueEx(app_key, "Publisher")
                                publisher = str(publisher).strip()
                            except (FileNotFoundError, OSError):
                                pass

                            # Discover main executable (.exe)
                            exe_name = ""

                            # Try DisplayIcon first
                            try:
                                display_icon, _ = winreg.QueryValueEx(app_key, "DisplayIcon")
                                display_icon = str(display_icon).split(",")[0].strip('"')
                                base = os.path.basename(display_icon).lower()
                                if base.endswith(".exe") and not any(u in base for u in ("unins", "uninstall", "setup", "installer")):
                                    exe_name = base
                            except (FileNotFoundError, OSError):
                                pass

                            # Try InstallLocation if icon wasn't an app exe
                            if not exe_name:
                                try:
                                    install_loc, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                    install_loc = str(install_loc).strip('"')
                                    if install_loc and os.path.isdir(install_loc):
                                        for root, _, files in os.walk(install_loc):
                                            for f in files:
                                                fl = f.lower()
                                                if fl.endswith(".exe") and not any(u in fl for u in ("unins", "uninstall", "setup", "installer", "update", "crash")):
                                                    exe_name = fl
                                                    break
                                            if exe_name:
                                                break
                                except (FileNotFoundError, OSError):
                                    pass

                            # Fallback: estimate clean exe name from DisplayName
                            if not exe_name:
                                candidate = re.sub(r"[^a-zA-Z0-9]", "", display_name).lower()
                                exe_name = f"{candidate}.exe" if candidate else "app.exe"

                            # Strip any uninstaller artifacts
                            if any(u in exe_name for u in ("unins", "uninstall", "remove", "installer")):
                                candidate = re.sub(r"[^a-zA-Z0-9]", "", display_name).lower()
                                exe_name = f"{candidate}.exe" if candidate else "app.exe"

                            # Skip if identified as core system daemon
                            if exe_name in SYSTEM_EXES or exe_name.replace(".exe", "") in SYSTEM_EXES:
                                continue

                            seen_names.add(name_lower)
                            apps.append({
                                "name": display_name,
                                "exe": exe_name,
                                "publisher": publisher or "Unknown"
                            })

                    except (PermissionError, OSError):
                        continue
        except (FileNotFoundError, PermissionError, OSError):
            continue

    # Sort alphabetically by application name
    apps.sort(key=lambda x: x["name"].lower())
    return apps


if __name__ == "__main__":
    installed = get_installed_apps()
    print(f"Total installed applications found: {len(installed)}")
    for a in installed:
        print(f" - {a['name']} ({a['exe']}) by {a['publisher']}")
