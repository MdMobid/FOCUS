"""
FOCUS: Main Coordinator & Background Daemon
Integrates Win32 power management, keyboard hook, process whitelist guardian,
embedded web server, registry policies, and the anti-kill watchdog.
"""

import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict

# Ensure local imports work regardless of working directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
os.chdir(PROJECT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from config_manager import config
from keyboard_hook import KeyboardGuard
from process_guard import ProcessGuardian, get_active_window_info
from registry_policy import set_task_manager_disabled, setup_startup_entry
import system_power
from web_server import EmbeddedWebServer
from firebase_bridge import FirebaseCloudBridge


class MainCoordinator:
    def __init__(self):
        self.config = config
        self.start_time = time.time()

        # 1. Initialize Keyboard Interceptor
        self.keyboard_guard = KeyboardGuard(on_emergency_unlock=self.on_emergency_unlock)

        # 2. Initialize Process Guardian
        self.process_guardian = ProcessGuardian(self.config)

        # 3. Initialize Embedded Web Server (Local LAN fallback)
        port = int(self.config.get("server_port", 8443))
        self.web_server = EmbeddedWebServer(port, self)

        # 4. Initialize Firebase Cloud Bridge (1,000 km remote control)
        fb_url = self.config.get("firebase_url", "")
        fb_secret = self.config.get("firebase_secret", "")
        self.cloud_bridge = FirebaseCloudBridge(fb_url, fb_secret, self)

    def on_emergency_unlock(self):
        """Called when Ctrl + Alt + Shift + P is detected on the physical keyboard."""
        print("[FOCUS Coordinator] Emergency unlock hotkey pressed. Disabling keyboard lock.")
        self.config.set("keyboard_locked", False)
        self.keyboard_guard.set_locked(False)
        if hasattr(self, 'cloud_bridge') and self.cloud_bridge:
            self.cloud_bridge.push_data("/focus/status/keyboard_locked.json", False)

    def handle_action(self, action: str, payload: Dict[str, Any]) -> bool:
        """Executes system actions requested from the Parent Web Dashboard."""
        print(f"[FOCUS Coordinator] Handling action: '{action}'")

        if action == "lock":
            return system_power.lock_workstation()

        elif action == "signout":
            return system_power.sign_out()

        elif action == "restart":
            return system_power.restart_pc()

        elif action == "shutdown":
            return system_power.shutdown_pc()

        elif action == "keylock":
            locked = bool(payload.get("enabled", False))
            self.config.set("keyboard_locked", locked)
            self.keyboard_guard.set_locked(locked)
            return True

        elif action == "focus":
            enabled = bool(payload.get("enabled", False))
            duration_mins = int(payload.get("duration_mins", 0))

            self.config.set("focus_mode", enabled)
            if enabled and duration_mins > 0:
                expires_at = time.time() + (duration_mins * 60)
                self.config.set("focus_expires_at", expires_at)
            else:
                self.config.set("focus_expires_at", 0)

            # Enforce Task Manager lockdown during Focus Mode
            set_task_manager_disabled(enabled)
            return True

        elif action == "set_tabs":
            max_tabs = int(payload.get("max_tabs", 5))
            self.config.set("max_tabs", max_tabs)
            return True

        elif action == "screenshot":
            return True

        elif action == "update_app":
            res = self.handle_remote_update(payload.get("id", ""))
            return res.get("success", False)

        return False

    def handle_remote_update(self, cmd_id: str = "") -> Dict[str, Any]:
        """Pulls latest commits from GitHub origin main and resurrects via watchdog."""
        print(f"[FOCUS Coordinator] Remote app update initiated (cmd_id: {cmd_id or 'none'})...")
        project_dir = os.path.dirname(SCRIPT_DIR)
        fetch_cmd = [
            "git",
            "-c", "http.version=HTTP/1.1",
            "-c", "http.postBuffer=524288000",
            "-c", "safe.directory=*",
            "fetch", "origin", "main"
        ]
        reset_cmd = [
            "git",
            "-c", "safe.directory=*",
            "reset", "--hard", "origin/main"
        ]
        try:
            # Capture current commit hash before update
            old_head_proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                shell=(os.name == 'nt'),
                timeout=15
            )
            old_head = old_head_proc.stdout.strip()

            # Attempt fetch
            res = subprocess.run(
                fetch_cmd,
                cwd=project_dir,
                capture_output=True,
                text=True,
                shell=(os.name == 'nt'),
                timeout=60
            )
            # Retry once on transient network drop (e.g. "remote end hung up unexpectedly")
            if res.returncode != 0:
                print(f"[FOCUS Coordinator] Git fetch attempt 1 had code {res.returncode}. Retrying in 2s...")
                time.sleep(2)
                res = subprocess.run(
                    fetch_cmd,
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    shell=(os.name == 'nt'),
                    timeout=60
                )

            is_success = (res.returncode == 0)
            has_updates = False
            output = ""

            if is_success:
                # Reset working tree cleanly to match latest origin/main
                reset_res = subprocess.run(
                    reset_cmd,
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    shell=(os.name == 'nt'),
                    timeout=30
                )
                new_head_proc = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    shell=(os.name == 'nt'),
                    timeout=15
                )
                new_head = new_head_proc.stdout.strip()
                has_updates = (old_head != new_head and bool(new_head))
                if has_updates:
                    output = f"Updated: {old_head[:7]} -> {new_head[:7]}\n{reset_res.stdout.strip()}"
                else:
                    output = f"Already up to date ({new_head[:7] or 'main'})."
            else:
                err_text = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
                output = f"Fetch failed (code {res.returncode}): {err_text}"

            status_data = {
                "success": is_success,
                "has_updates": has_updates,
                "output": output,
                "cmd_id": cmd_id,
                "timestamp": time.time()
            }

            print(f"[FOCUS Coordinator] Git pull completed (success={is_success}):\n{output}")

            if hasattr(self, 'cloud_bridge') and self.cloud_bridge:
                self.cloud_bridge.push_data("/focus/update_status.json", status_data)

            if has_updates:
                print("[FOCUS Coordinator] New updates downloaded! Relaunching daemon in 2 seconds...")
                def delayed_restart():
                    time.sleep(2)
                    os._exit(0)  # Sentinel watchdog will automatically resurrect with the new code
                threading.Thread(target=delayed_restart, daemon=True).start()

            return status_data
        except Exception as exc:
            err_data = {
                "success": False,
                "has_updates": False,
                "output": f"Update failed: {str(exc)}",
                "cmd_id": cmd_id,
                "timestamp": time.time()
            }
            if hasattr(self, 'cloud_bridge') and self.cloud_bridge:
                self.cloud_bridge.push_data("/focus/update_status.json", err_data)
            return err_data

    def update_rules(self, new_rules: Dict[str, Any]):
        """Updates whitelists from web dashboard."""
        for key in ("allowed_apps", "allowed_sites", "allowed_channels", "max_tabs", "firebase_url", "firebase_secret"):
            if key in new_rules:
                self.config.set(key, new_rules[key])

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive status dictionary for web dashboard polling."""
        return {
            "online": True,
            "uptime_secs": int(time.time() - self.start_time),
            "focus_mode": self.config.get("focus_mode", False),
            "focus_expires_at": self.config.get("focus_expires_at", 0),
            "keyboard_locked": self.config.get("keyboard_locked", False),
            "max_tabs": self.config.get("max_tabs", 5),
            "active_window": get_active_window_info(),
        }

    def start_watchdog(self):
        """Spawns the anti-kill sentinel watchdog process."""
        watchdog_script = os.path.join(SCRIPT_DIR, "watchdog.py")
        if os.path.exists(watchdog_script):
            own_pid = os.getpid()
            main_script = os.path.abspath(__file__)
            try:
                subprocess.Popen(
                    [sys.executable, watchdog_script, str(own_pid), main_script],
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                print("[FOCUS Coordinator] Sentinel watchdog spawned.")
            except Exception as exc:
                print(f"[FOCUS Coordinator] Could not spawn watchdog: {exc}")

    def run(self):
        """Starts all background services."""
        print("=" * 60)
        print("          FOCUS: Parental Control & Focus Manager          ")
        print("=" * 60)

        # ── SAFETY DEFAULTS ────────────────────────────────────────────────
        # Always boot with keyboard UNLOCKED and Focus Mode OFF, regardless
        # of whatever state Firebase may have stored from the previous session.
        # These are re-applied AFTER cloud_bridge.start() so they win any race.
        self.config.set("keyboard_locked", False)
        self.config.set("focus_mode", False)
        self.config.set("focus_expires_at", 0)
        self.keyboard_guard.set_locked(False)

        # Start subsystems
        self.keyboard_guard.start()
        self.process_guardian.start()
        self.web_server.start()
        self.cloud_bridge.start()

        # Re-apply safety defaults a second time after cloud bridge startup
        # (firebase_bridge._sync_initial_rules may run during .start() and
        # overwrite local config if rules arrive before our set() calls above)
        self.config.set("keyboard_locked", False)
        self.config.set("focus_mode", False)
        self.config.set("focus_expires_at", 0)
        self.keyboard_guard.set_locked(False)

        # Spawn watchdog
        self.start_watchdog()

        print("[FOCUS Coordinator] All systems online.")
        print("[FOCUS Coordinator] Parent PIN security active.")
        print("[FOCUS Coordinator] Keep this process running or installed as Windows Service.")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        print("[FOCUS Coordinator] Shutting down...")
        self.keyboard_guard.stop()
        self.process_guardian.stop()
        self.web_server.stop()
        self.cloud_bridge.stop()
        # Restore task manager before exiting
        set_task_manager_disabled(False)
        sys.exit(0)


if __name__ == "__main__":
    coordinator = MainCoordinator()
    coordinator.run()
