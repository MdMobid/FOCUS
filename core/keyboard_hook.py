"""
FOCUS: Low-Level Windows Keyboard Interceptor
Blocks keyboard hardware input using WH_KEYBOARD_LL hook.
Provides a secret emergency hotkey override (Ctrl + Alt + Shift + P) to open the Parent Unlock prompt.

IMPORTANT Win32 note:
  WH_KEYBOARD_LL hooks require a *blocking* GetMessage() pump on the hook thread.
  Windows has a LowLevelHooksTimeout (~1 second). If the hook thread does not call
  GetMessage/PeekMessage fast enough, Windows bypasses the hook entirely — meaning
  key events are never delivered and the hotkey never fires.
  We therefore use a proper blocking GetMessage loop and PostThreadMessage(WM_QUIT)
  for clean shutdown instead of the previous PeekMessage + sleep approach.
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

# HOOKPROC function type
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode",      wintypes.DWORD),
        ("scanCode",    wintypes.DWORD),
        ("flags",       wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


def _is_key_pressed(vk: int) -> bool:
    """
    Returns True if the given virtual key is currently held down.
    Uses GetAsyncKeyState — the authoritative live Win32 key state.
    More reliable than internal boolean tracking which can desync if a
    key is released while the hook is momentarily reinstalling.
    """
    state = ctypes.windll.user32.GetAsyncKeyState(vk)
    return bool(state & 0x8000)


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
        self._hook_thread_id: Optional[int] = None   # needed for PostThreadMessage(WM_QUIT)
        self._c_hook_proc = None

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

            # ── Emergency Hotkey: Ctrl + Alt + Shift + P ────────────────────
            # GetAsyncKeyState gives authoritative live modifier state — immune
            # to desync that can happen with purely internal boolean tracking.
            if is_down and vk_code == VK_KEY_P and _ctrl_held() and _alt_held() and _shift_held():
                print("[FOCUS Keyboard] Emergency hotkey (Ctrl+Alt+Shift+P) detected! Unlocking keyboard.")
                self.is_locked = False
                if self.on_emergency_unlock:
                    # Run callback off the hook thread so we return fast
                    threading.Thread(target=self.on_emergency_unlock, daemon=True).start()
                return 1  # Consume the event

            # ── Block all other keystrokes when locked ───────────────────────
            if self.is_locked:
                return 1   # Non-zero prevents OS propagation

        return ctypes.windll.user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

    def _run_message_pump(self):
        user32   = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # Explicit argtypes prevent pointer truncation on 64-bit Windows
        user32.SetWindowsHookExW.argtypes  = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype   = wintypes.HHOOK
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype  = wintypes.HMODULE

        # Strong reference — prevents GC from freeing the ctypes callback
        self._c_hook_proc = HOOKPROC(self._hook_callback)

        h_mod = kernel32.GetModuleHandleW(None)
        self._hook_id = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._c_hook_proc, h_mod, 0)

        if not self._hook_id:
            err = kernel32.GetLastError()
            print(f"[FOCUS Keyboard] Failed to install low-level keyboard hook (Win32 Err: {err}).", file=sys.stderr)
            return

        # Record thread ID so stop() can post WM_QUIT to wake us
        self._hook_thread_id = kernel32.GetCurrentThreadId()
        print("[FOCUS Keyboard] Keyboard hook successfully installed.")

        # ── Proper blocking GetMessage pump ─────────────────────────────────
        # WH_KEYBOARD_LL hook callbacks are dispatched inside GetMessage/PeekMessage.
        # Windows' LowLevelHooksTimeout means if we're not calling GetMessage fast
        # enough, it silently bypasses the hook — key events are never seen.
        # Blocking GetMessage guarantees we're always ready to receive immediately.
        msg = wintypes.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                # 0 = WM_QUIT received; -1 = error — exit in both cases
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Unhook on exit
        if self._hook_id:
            user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
            print("[FOCUS Keyboard] Keyboard hook uninstalled.")

    def start(self) -> None:
        """Starts keyboard hook in a background thread."""
        if self._hook_thread and self._hook_thread.is_alive():
            return
        self._hook_thread = threading.Thread(target=self._run_message_pump, daemon=True)
        self._hook_thread.start()

    def stop(self) -> None:
        """Stops the keyboard hook by posting WM_QUIT to unblock GetMessage."""
        thread_id = self._hook_thread_id
        if thread_id:
            ctypes.windll.user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
        if self._hook_thread:
            self._hook_thread.join(timeout=2.0)


if __name__ == "__main__":
    import time

    def on_unlock():
        print("[Demo] Emergency unlock callback fired — keyboard is now unlocked!")

    guard = KeyboardGuard(on_emergency_unlock=on_unlock)
    guard.start()
    guard.set_locked(True)
    print("Keyboard guard running and LOCKED. Press Ctrl+Alt+Shift+P to unlock. Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        guard.stop()

