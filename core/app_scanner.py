"""
FOCUS: Installed Applications Scanner
Scans the Windows Registry and Start Menu to enumerate all software installed on the PC.
Extracts application names, publishers, and target executable names (.exe).
Implemented purely with Python standard library (winreg, os, sys).
"""

import os
import re
import sys
import winreg
from typing import Dict, List, Set


def get_installed_apps() -> List[Dict[str, str]]:
    """
    Enumerates all installed desktop applications from 64-bit and 32-bit Windows Registry
    and the user-specific software registry.
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
                            # Read DisplayName
                            try:
                                display_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                display_name = str(display_name).strip()
                            except (FileNotFoundError, OSError):
                                continue

                            if not display_name:
                                continue

                            # Skip system updates, patches, and runtime redistributables
                            if display_name.startswith("KB") or "Update for Windows" in display_name or "Security Update" in display_name:
                                continue

                            clean_name_key = display_name.lower()
                            if clean_name_key in seen_names:
                                continue

                            # Read Publisher
                            publisher = ""
                            try:
                                publisher, _ = winreg.QueryValueEx(app_key, "Publisher")
                                publisher = str(publisher).strip()
                            except (FileNotFoundError, OSError):
                                pass

                            # Attempt to discover main executable (.exe)
                            exe_name = ""

                            # Try DisplayIcon first
                            try:
                                display_icon, _ = winreg.QueryValueEx(app_key, "DisplayIcon")
                                display_icon = str(display_icon).split(",")[0].strip('"')
                                if display_icon.lower().endswith(".exe"):
                                    exe_name = os.path.basename(display_icon).lower()
                            except (FileNotFoundError, OSError):
                                pass

                            # Try InstallLocation if icon wasn't an exe
                            if not exe_name:
                                try:
                                    install_loc, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                    install_loc = str(install_loc).strip('"')
                                    if install_loc and os.path.isdir(install_loc):
                                        for root, _, files in os.walk(install_loc):
                                            for f in files:
                                                if f.lower().endswith(".exe"):
                                                    exe_name = f.lower()
                                                    break
                                            if exe_name:
                                                break
                                except (FileNotFoundError, OSError):
                                    pass

                            # Fallback: estimate from DisplayName
                            if not exe_name:
                                candidate = re.sub(r"[^a-zA-Z0-9]", "", display_name).lower()
                                exe_name = f"{candidate}.exe" if candidate else "app.exe"

                            seen_names.add(clean_name_key)
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
    for a in installed[:15]:
        print(f" - {a['name']} ({a['exe']}) by {a['publisher']}")
