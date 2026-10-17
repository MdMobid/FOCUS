"""
FOCUS: Low-Level Windows Keyboard Interceptor
Blocks keyboard hardware input using WH_KEYBOARD_LL hook.
Provides a secret emergency hotkey override (Ctrl + Alt + Shift + P) to open the Parent Unlock prompt.
"""

import ctypes
from ctypes import wintypes
import threading
import sys
import time
from typing import Callable, Optional

# Win32 Constants
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

# Virtual Key Codes
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt key
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_KEY_P = 0x50

# Type definitions
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class KeyboardGuard:
    def __init__(self, on_emergency_unlock: Optional[Callable[[], None]] = None):
        self.is_locked = False
        self.on_emergency_unlock = on_emergency_unlock
        self._hook_id = None
        self._hook_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._c_hook_proc = None

        # Key state tracking for emergency combination (Ctrl + Alt + Shift + P)
        self._ctrl_down = False
        self._alt_down = False
        self._shift_down = False

    def set_locked(self, locked: bool) -> None:
        """Enables or disables keyboard input suppression."""
        self.is_locked = locked
        state_str = "LOCKED" if locked else "UNLOCKED"
        print(f"[FOCUS Keyboard] Hardware keyboard is now {state_str}")

    def _hook_callback(self, nCode: int, wParam: wintypes.WPARAM, lParam: wintypes.LPARAM) -> int:
        if nCode >= 0:
            kbd_struct = KBDLLHOOKSTRUCT.from_address(lParam)
            vk_code = kbd_struct.vkCode
            is_down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
            is_up = wParam in (WM_KEYUP, WM_SYSKEYUP)

            # Update modifier keys tracking
            if vk_code in (VK_CONTROL, 0xA2, 0xA3):  # VK_LCONTROL, VK_RCONTROL
                self._ctrl_down = is_down
            elif vk_code in (VK_MENU, 0xA4, 0xA5):   # VK_LMENU, VK_RMENU (Alt)
                self._alt_down = is_down
            elif vk_code in (VK_SHIFT, 0xA0, 0xA1):  # VK_LSHIFT, VK_RSHIFT
                self._shift_down = is_down

            # Check Emergency Hotkey: Ctrl + Alt + Shift + P
            if is_down and vk_code == VK_KEY_P and self._ctrl_down and self._alt_down and self._shift_down:
                print("[FOCUS Keyboard] Emergency hotkey (Ctrl+Alt+Shift+P) detected!")
                self.is_locked = False
                if self.on_emergency_unlock:
                    # Execute callback in a separate thread so message hook is not blocked
                    threading.Thread(target=self.on_emergency_unlock, daemon=True).start()
                return 1  # Consume hotkey event

            # If locked, block all keystrokes
            if self.is_locked:
                return 1  # Non-zero return consumes key, preventing OS propagation

        return ctypes.windll.user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

    def _run_message_pump(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # Define 64-bit Windows function prototypes to prevent pointer truncation
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        # Keep reference to callback to prevent garbage collection
        self._c_hook_proc = HOOKPROC(self._hook_callback)

        h_mod = kernel32.GetModuleHandleW(None)
        self._hook_id = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._c_hook_proc,
            h_mod,
            0
        )

        if not self._hook_id:
            err = kernel32.GetLastError()
            print(f"[FOCUS Keyboard] Failed to install low-level keyboard hook (Win32 Err: {err}).", file=sys.stderr)
            return

        print("[FOCUS Keyboard] Keyboard hook successfully installed.")

        # Standard Win32 Message Pump
        msg = wintypes.MSG()
        while not self._stop_event.is_set():
            # Use PeekMessage with PM_REMOVE to keep loop responsive
            has_msg = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)  # 1 = PM_REMOVE
            if has_msg:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.01)

        # Unhook when stop requested
        if self._hook_id:
            user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
            print("[FOCUS Keyboard] Keyboard hook uninstalled.")

    def start(self) -> None:
        """Starts keyboard hook in a background thread."""
        if self._hook_thread and self._hook_thread.is_alive():
            return
        self._stop_event.clear()
        self._hook_thread = threading.Thread(target=self._run_message_pump, daemon=True)
        self._hook_thread.start()

    def stop(self) -> None:
        """Stops the keyboard hook."""
        self._stop_event.set()
        if self._hook_thread:
            self._hook_thread.join(timeout=1.0)


if __name__ == "__main__":
    def on_unlock():
        print("[Demo] Emergency unlock callback fired!")

    guard = KeyboardGuard(on_emergency_unlock=on_unlock)
    guard.start()
    print("Keyboard guard running. Press Ctrl+C to exit demo.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        guard.stop()
