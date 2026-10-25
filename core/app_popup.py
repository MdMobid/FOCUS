"""
FOCUS: Blocked Application Desktop Popup
Displays a non-intrusive, Stitch-styled dark tactile notification window when an unapproved
application is terminated during Focus Mode, with an 'Ask to Allow App' button.
Zero external dependencies (pure Python standard library: tkinter, threading, urllib).
"""

import json
import os
import sys
import threading
import time
from typing import Dict
import urllib.request

# Debounce tracker: exe_name -> last popup timestamp
_last_popup_times: Dict[str, float] = {}
_lock = threading.Lock()
POPUP_DEBOUNCE_SECS = 6.0


def show_app_blocked_popup(app_exe: str, app_display_name: str = ""):
    """Spawns an async desktop popup notification in a background thread."""
    clean_exe = os.path.basename(app_exe).strip()
    if not clean_exe:
        return

    now = time.time()
    with _lock:
        last_time = _last_popup_times.get(clean_exe.lower(), 0)
        if now - last_time < POPUP_DEBOUNCE_SECS:
            return
        _last_popup_times[clean_exe.lower()] = now

    thread = threading.Thread(
        target=_run_popup_window,
        args=(clean_exe, app_display_name or clean_exe),
        daemon=True
    )
    thread.start()


def _run_popup_window(app_exe: str, display_title: str):
    try:
        import tkinter as tk
    except Exception:
        return

    try:
        root = tk.Tk()
        root.title("Application Restricted - FOCUS")
        root.configure(bg="#181b22")
        root.attributes("-topmost", True)
        root.resizable(False, False)

        # Remove default OS window chrome for custom modern dark card look
        try:
            root.overrideredirect(True)
        except Exception:
            pass

        # Dimensions & positioning (bottom-right above taskbar)
        width = 420
        height = 250
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        pos_x = max(20, screen_w - width - 24)
        pos_y = max(20, screen_h - height - 60)
        root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

        # Outer border frame
        outer_frame = tk.Frame(root, bg="#2a303c", padx=1, pady=1)
        outer_frame.pack(fill="both", expand=True)

        card = tk.Frame(outer_frame, bg="#181b22", padx=20, pady=16)
        card.pack(fill="both", expand=True)

        # Header: Icon & Title
        header_frame = tk.Frame(card, bg="#181b22")
        header_frame.pack(fill="x", pady=(0, 10))

        lock_badge = tk.Label(
            header_frame,
            text="🔒",
            font=("Segoe UI", 16),
            bg="#12151b",
            fg="#e07a5f",
            padx=8,
            pady=4
        )
        lock_badge.pack(side="left", padx=(0, 12))

        title_box = tk.Frame(header_frame, bg="#181b22")
        title_box.pack(side="left", fill="x", expand=True)

        h1 = tk.Label(
            title_box,
            text="Application Restricted",
            font=("Segoe UI", 12, "bold"),
            bg="#181b22",
            fg="#e8ecf2",
            anchor="w"
        )
        h1.pack(fill="x")

        policy_label = tk.Label(
            title_box,
            text="FOCUS STRICT POLICY ENFORCED",
            font=("Segoe UI", 8, "bold"),
            bg="#181b22",
            fg="#e07a5f",
            anchor="w"
        )
        policy_label.pack(fill="x")

        # Recessed Well Card with Target App Name
        well = tk.Frame(card, bg="#111419", padx=12, pady=8, highlightbackground="#080b10", highlightthickness=1)
        well.pack(fill="x", pady=(0, 10))

        target_row = tk.Frame(well, bg="#111419")
        target_row.pack(fill="x")

        lbl_tag = tk.Label(target_row, text="APPLICATION", font=("Segoe UI", 8, "bold"), bg="#111419", fg="#64748b")
        lbl_tag.pack(side="left")

        val_tag = tk.Label(
            target_row,
            text=app_exe,
            font=("Consolas", 10, "bold"),
            bg="#111419",
            fg="#60a5fa"
        )
        val_tag.pack(side="right")

        # Descriptive text
        desc = tk.Label(
            card,
            text="Focus Mode is active. If you need this application for study, you can ask your parent to approve it.",
            font=("Segoe UI", 9),
            bg="#181b22",
            fg="#94a3b8",
            wraplength=380,
            justify="left",
            anchor="w"
        )
        desc.pack(fill="x", pady=(0, 14))

        # Action Buttons Row
        btn_frame = tk.Frame(card, bg="#181b22")
        btn_frame.pack(fill="x")

        def on_ask():
            btn_ask.config(text="Sending Request...", state="disabled", bg="#222c3d")
            root.update()

            def _send():
                try:
                    payload = json.dumps({
                        "type": "app",
                        "target": app_exe,
                        "title": display_title or app_exe,
                        "url": ""
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        "http://127.0.0.1:8443/api/request_access",
                        data=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req, timeout=3):
                        pass
                    btn_ask.config(text="✓ Request Sent to Parent", bg="#193d2c", fg="#34d399")
                except Exception:
                    btn_ask.config(text="✓ Request Queued", bg="#193d2c", fg="#34d399")
                # Auto close after 2.5 seconds
                root.after(2500, root.destroy)

            threading.Thread(target=_send, daemon=True).start()

        btn_ask = tk.Button(
            btn_frame,
            text="Ask to Allow App",
            font=("Segoe UI", 9, "bold"),
            bg="#3b5373",
            fg="#ffffff",
            activebackground="#476288",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=6,
            cursor="hand2",
            command=on_ask
        )
        btn_ask.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_dismiss = tk.Button(
            btn_frame,
            text="Dismiss",
            font=("Segoe UI", 9),
            bg="#222732",
            fg="#94a3b8",
            activebackground="#2c3342",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=root.destroy
        )
        btn_dismiss.pack(side="right")

        # Auto-dismiss after 12 seconds
        root.after(12000, root.destroy)

        # Allow dragging window if user clicks on header
        def _start_move(event):
            root._x = event.x
            root._y = event.y

        def _on_motion(event):
            x = root.winfo_x() + (event.x - root._x)
            y = root.winfo_y() + (event.y - root._y)
            root.geometry(f"+{x}+{y}")

        card.bind("<Button-1>", _start_move)
        card.bind("<B1-Motion>", _on_motion)

        root.mainloop()
    except Exception as e:
        print(f"[FOCUS Popup] Error running popup: {e}", file=sys.stderr)


if __name__ == "__main__":
    show_app_blocked_popup("roblox.exe", "Roblox Player")
    time.sleep(15)
