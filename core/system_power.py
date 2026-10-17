"""
FOCUS: Win32 System Power & Session Manager
Handles workstation locking, signing out, restarting, and shutting down.
Uses native Windows APIs and system utilities with zero external dependencies.
"""

import ctypes
import os
import subprocess
import sys


def lock_workstation() -> bool:
    """Instantly locks the Windows workstation (equivalent to Win + L)."""
    try:
        user32 = ctypes.windll.user32
        result = user32.LockWorkStation()
        return bool(result)
    except Exception as exc:
        print(f"[FOCUS System] Failed to lock workstation: {exc}", file=sys.stderr)
        return False


def sign_out() -> bool:
    """Logs out the current Windows user session."""
    try:
        # EWX_LOGOFF (0x00000000) | EWX_FORCEIFHUNG (0x00000010)
        user32 = ctypes.windll.user32
        result = user32.ExitWindowsEx(0x00000000 | 0x00000010, 0)
        if not result:
            # Fallback to native shutdown /l
            subprocess.run(["shutdown", "/l"], check=False)
        return True
    except Exception as exc:
        print(f"[FOCUS System] Failed to sign out: {exc}", file=sys.stderr)
        return False


def restart_pc(delay_seconds: int = 0) -> bool:
    """Restarts the computer."""
    try:
        cmd = ["shutdown", "/r", "/t", str(delay_seconds), "/c", "FOCUS: Restarting by Parent"]
        subprocess.run(cmd, check=False)
        return True
    except Exception as exc:
        print(f"[FOCUS System] Failed to restart: {exc}", file=sys.stderr)
        return False


def shutdown_pc(delay_seconds: int = 0) -> bool:
    """Shuts down the computer."""
    try:
        cmd = ["shutdown", "/s", "/t", str(delay_seconds), "/c", "FOCUS: Shutdown by Parent"]
        subprocess.run(cmd, check=False)
        return True
    except Exception as exc:
        print(f"[FOCUS System] Failed to shutdown: {exc}", file=sys.stderr)
        return False


def cancel_shutdown() -> bool:
    """Aborts any pending scheduled shutdown or restart."""
    try:
        subprocess.run(["shutdown", "/a"], check=False)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    print("FOCUS System Power module loaded. Run functions via main coordinator.")
