"""
FOCUS: Low-Level Windows Keyboard Interceptor
Blocks keyboard hardware input using WH_KEYBOARD_LL hook.
Provides a secret emergency hotkey override (Ctrl + Alt + Shift + P) to open the Parent Unlock prompt.

Key Architecture Directives:
  - ON-DEMAND HOOKING: The WH_KEYBOARD_LL hook is ONLY installed when keyboard is actually locked.
    When unlocked, NO hook is installed in Windows at all, guaranteeing 0ms input latency,
    zero CPU overhead on low-spec CPUs (like i3), and zero possibility of boot-time lockouts.
  - Proper blocking GetMessage() pump ensures hook callbacks are processed promptly.
"""

import ctypes
from ctypes import wintypes
import threading
import sys
from typing import Callable, Optional

# Win32 Constants
WH_KEYBOARD_LL  = 13
WM_QUIT         = 0x0012
WM_KEYDOWN      = 0x0100
WM_KEYUP        = 0x0101
WM_SYSKEYDOWN   = 0x0104
WM_SYSKEYUP     = 0x0105

# Virtual Key Codes
VK_SHIFT   = 0x10
VK_CONTROL = 0x11
VK_MENU    = 0x12   # Alt key
VK_LWIN    = 0x5B
VK_RWIN    = 0x5C
VK_KEY_P   = 0x50

# 64-bit safe HOOKPROC function type (LRESULT on x64 is pointer-sized: LPARAM)
HOOKPROC = ctypes.WINFUNCTYPE(wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode",      wintypes.DWORD),
        ("scanCode",    wintypes.DWORD),
        ("flags",       wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


def _is_key_pressed(vk: int) -> bool:
    """Returns True if virtual key is held down via authoritative Win32 GetAsyncKeyState."""
    try:
        state = ctypes.windll.user32.GetAsyncKeyState(vk)
        return bool(state & 0x8000)
    except Exception:
        return False


def _ctrl_held() -> bool:
    return _is_key_pressed(0xA2) or _is_key_pressed(0xA3) or _is_key_pressed(VK_CONTROL)

def _alt_held() -> bool:
    return _is_key_pressed(0xA4) or _is_key_pressed(0xA5) or _is_key_pressed(VK_MENU)

def _shift_held() -> bool:
    return _is_key_pressed(0xA0) or _is_key_pressed(0xA1) or _is_key_pressed(VK_SHIFT)


class KeyboardGuard:
    def __init__(self, on_emergency_unlock: Optional[Callable[[], None]] = None):
        self.is_locked = False
        self.on_emergency_unlock = on_emergency_unlock
        self._hook_id   = None
        self._hook_thread: Optional[threading.Thread] = None
        self._hook_thread_id: Optional[int] = None
        self._c_hook_proc = None
        self._lock = threading.Lock()

    def set_locked(self, locked: bool) -> None:
        """Enables or disables keyboard input suppression on demand."""
        with self._lock:
            if locked == self.is_locked:
                return
            self.is_locked = locked
            state_str = "LOCKED" if locked else "UNLOCKED"
            print(f"[FOCUS Keyboard] Hardware keyboard is now {state_str}")

            if locked:
                self._start_hook_thread()
            else:
                self._stop_hook_thread()

    def _hook_callback(self, nCode: int, wParam: wintypes.WPARAM, lParam: wintypes.LPARAM) -> int:
        try:
            if nCode >= 0:
                kbd_struct = KBDLLHOOKSTRUCT.from_address(lParam)
                vk_code = kbd_struct.vkCode
                is_down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)

                # Emergency Hotkey: Ctrl + Alt + Shift + P
                if is_down and vk_code == VK_KEY_P and _ctrl_held() and _alt_held() and _shift_held():
                    print("[FOCUS Keyboard] Emergency hotkey (Ctrl+Alt+Shift+P) detected! Unlocking keyboard.")
                    self.set_locked(False)
                    if self.on_emergency_unlock:
                        threading.Thread(target=self.on_emergency_unlock, daemon=True).start()
                    return 1

                # Consume all other keystrokes when locked
                if self.is_locked:
                    return 1
        except Exception:
            pass

        return ctypes.windll.user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

    def _run_message_pump(self):
        user32   = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.SetWindowsHookExW.argtypes  = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype   = wintypes.HHOOK
        user32.CallNextHookEx.argtypes     = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype      = wintypes.LPARAM
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype  = wintypes.HMODULE

        self._c_hook_proc = HOOKPROC(self._hook_callback)
        h_mod = kernel32.GetModuleHandleW(None)
        self._hook_id = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._c_hook_proc, h_mod, 0)

        if not self._hook_id:
            err = kernel32.GetLastError()
            print(f"[FOCUS Keyboard] Failed to install low-level keyboard hook (Win32 Err: {err}).", file=sys.stderr)
            return

        self._hook_thread_id = kernel32.GetCurrentThreadId()
        print("[FOCUS Keyboard] Keyboard lock hook successfully installed.")

        # Blocking message pump required for WH_KEYBOARD_LL dispatch
        msg = wintypes.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook_id:
            user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
            print("[FOCUS Keyboard] Keyboard lock hook uninstalled.")

    def _start_hook_thread(self):
        if self._hook_thread and self._hook_thread.is_alive():
            return
        self._hook_thread = threading.Thread(target=self._run_message_pump, daemon=True)
        self._hook_thread.start()

    def _stop_hook_thread(self):
        thread_id = self._hook_thread_id
        if thread_id:
            ctypes.windll.user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
        self._hook_thread = None
        self._hook_thread_id = None

    def start(self) -> None:
        """Called on daemon boot. If locked, starts hook. If unlocked, leaves hook uninstalled."""
        if self.is_locked:
            self._start_hook_thread()

    def stop(self) -> None:
        """Stops and unhooks keyboard guard completely."""
        self.set_locked(False)


if __name__ == "__main__":
    import time

    def on_unlock():
        print("[Demo] Emergency unlock callback fired — keyboard is now unlocked!")

    guard = KeyboardGuard(on_emergency_unlock=on_unlock)
    guard.set_locked(True)
    print("Keyboard guard running and LOCKED. Press Ctrl+Alt+Shift+P to unlock. Ctrl+C to exit.")
    try:
        while guard.is_locked:
            time.sleep(1)
    except KeyboardInterrupt:
        guard.stop()
