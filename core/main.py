"""
FOCUS: Main Coordinator & Background Daemon
Integrates Win32 power management, keyboard hook, process whitelist guardian,
embedded web server, registry policies, and the anti-kill watchdog.
"""

import json
import os
import re
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

# If running headless under pythonw or Windows background, direct outputs to service.log
if sys.stdout is None or not hasattr(sys.stdout, "write"):
    try:
        log_path = os.path.join(SCRIPT_DIR, "service.log")
        sys.stdout = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout
    except Exception:
        pass


def acquire_single_instance_mutex(name: str = "FOCUS_Daemon_SingleInstance_Mutex"):
    """Native Win32 mutex ensuring only one FOCUS background daemon runs at a time."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        mutex = kernel32.CreateMutexW(None, False, name)
        if not mutex or kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return None
        return mutex
    except Exception:
        return True

from config_manager import config
from keyboard_hook import KeyboardGuard
from process_guard import get_active_window_info
from registry_policy import set_task_manager_disabled
import system_power
from web_server import EmbeddedWebServer
from firebase_bridge import FirebaseCloudBridge


def extract_youtube_video_id(url_or_id: str) -> str:
    """Extracts 11-char YouTube video ID from watch URL, short URL, embed, or raw ID."""
    if not url_or_id:
        return ""
    val = str(url_or_id).strip()
    m = re.search(r'(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})', val)
    if m:
        return m.group(1)
    if re.match(r'^[a-zA-Z0-9_-]{11}$', val):
        return val
    return ""


class MainCoordinator:
    def __init__(self, config_manager=None):
        self.config = config_manager or config
        self.start_time = time.time()

        # 1. Initialize Keyboard Interceptor
        self.keyboard_guard = KeyboardGuard(on_emergency_unlock=self.on_emergency_unlock)

        # 2. Initialize Embedded Web Server (Local LAN fallback)
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

            # When Strict Focus Mode turns ON, respect requested or current max_tabs, clamped to min_tabs
            if enabled:
                min_tabs = int(self.config.get("min_tabs", 1))
                max_range = int(self.config.get("max_tabs_range", 15))
                req_tabs = payload.get("max_tabs")
                if req_tabs is not None:
                    target_tabs = max(min_tabs, min(int(req_tabs), max_range))
                else:
                    curr_tabs = int(self.config.get("max_tabs", min_tabs))
                    target_tabs = max(min_tabs, min(curr_tabs, max_range))
                self.config.set("max_tabs", target_tabs)
                self.update_rules({"max_tabs": target_tabs})
                if hasattr(self, 'cloud_bridge') and self.cloud_bridge:
                    try:
                        self.cloud_bridge.push_data("/focus/status/max_tabs.json", target_tabs)
                        self.cloud_bridge.push_data("/focus/rules/max_tabs.json", target_tabs)
                    except Exception:
                        pass

            # Enforce Task Manager lockdown during Focus Mode
            set_task_manager_disabled(enabled)
            return True

        elif action == "set_tabs":
            min_tabs = int(self.config.get("min_tabs", 1))
            max_range = int(self.config.get("max_tabs_range", 15))
            max_tabs = int(payload.get("max_tabs", min_tabs))
            clamped = max(min_tabs, min(max_tabs, max_range))
            self.config.set("max_tabs", clamped)
            self.update_rules({"max_tabs": clamped})
            if hasattr(self, 'cloud_bridge') and self.cloud_bridge:
                try:
                    self.cloud_bridge.push_data("/focus/status/max_tabs.json", clamped)
                    self.cloud_bridge.push_data("/focus/rules/max_tabs.json", clamped)
                except Exception:
                    pass
            return True

        elif action == "set_tab_range":
            min_tabs = max(1, int(payload.get("min_tabs", 1)))
            max_range = max(min_tabs, int(payload.get("max_tabs_range", 15)))
            self.config.set("min_tabs", min_tabs)
            self.config.set("max_tabs_range", max_range)
            current_max = int(payload.get("max_tabs", self.config.get("max_tabs", min_tabs)))
            clamped = max(min_tabs, min(current_max, max_range))
            self.config.set("max_tabs", clamped)
            self.update_rules({"min_tabs": min_tabs, "max_tabs_range": max_range, "max_tabs": clamped})
            if hasattr(self, 'cloud_bridge') and self.cloud_bridge:
                try:
                    self.cloud_bridge.push_data("/focus/status/min_tabs.json", min_tabs)
                    self.cloud_bridge.push_data("/focus/status/max_tabs_range.json", max_range)
                    self.cloud_bridge.push_data("/focus/status/max_tabs.json", clamped)
                    self.cloud_bridge.push_data("/focus/rules/min_tabs.json", min_tabs)
                    self.cloud_bridge.push_data("/focus/rules/max_tabs_range.json", max_range)
                    self.cloud_bridge.push_data("/focus/rules/max_tabs.json", clamped)
                except Exception:
                    pass
            return True

        elif action == "screenshot":
            return True

        elif action == "update_app":
            res = self.handle_remote_update(payload.get("id", ""))
            return res.get("success", False)

        elif action == "resolve_request":
            req_id = payload.get("request_id") or payload.get("id")
            decision = payload.get("decision", "reject")
            res = self.resolve_access_request(req_id, decision)
            return res.get("success", False)

        elif action == "delete_request":
            req_id = payload.get("request_id") or payload.get("id")
            target = payload.get("target", "")
            res = self.delete_access_request(req_id, target)
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
        """Updates whitelists from web dashboard and mirrors to rules.json."""
        for key in ("allowed_sites", "allowed_channels", "allowed_videos", "max_tabs", "min_tabs", "max_tabs_range", "firebase_url", "firebase_secret"):
            if key in new_rules:
                self.config.set(key, new_rules[key])

        # Atomically mirror updated rules to config/rules.json on disk
        try:
            rules_path = os.path.join(os.path.dirname(SCRIPT_DIR), "config", "rules.json")
            current = self.config.get_all()
            with open(rules_path, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2)
        except Exception as e:
            print(f"[FOCUS Coordinator] Warning: Could not write rules.json: {e}")

    def record_access_request(self, req_data: Dict[str, Any]) -> Dict[str, Any]:
        """Records an access request when a student asks to allow a channel, video, or website."""
        req_id = "req_" + str(int(time.time() * 1000)) + "_" + os.urandom(3).hex()
        target = str(req_data.get("target", "")).strip()
        req_type = str(req_data.get("type", "website")).strip().lower()
        title = str(req_data.get("title", "")).strip() or target
        url = str(req_data.get("url", "")).strip() or target
        channel = str(req_data.get("channel", "")).strip()

        if not target and not url:
            return {"success": False, "error": "Missing target or URL"}

        new_req = {
            "id": req_id,
            "type": req_type,        # "channel", "video", "website"
            "target": target,
            "title": title,
            "url": url,
            "channel": channel,
            "status": "pending",      # "pending", "approved", "rejected"
            "timestamp": time.time()
        }

        raw_requests = self.config.get("access_requests", [])
        requests = [r for r in raw_requests if isinstance(r, dict)] if isinstance(raw_requests, list) else []

        # Check if already pending for same target
        for existing in requests:
            if existing.get("status") == "pending" and existing.get("target") == target and existing.get("type") == req_type:
                return {"success": True, "id": existing.get("id"), "message": "Already pending"}

        requests.insert(0, new_req)
        self.config.set("access_requests", requests[:50])

        print(f"[FOCUS Coordinator] Student access request recorded: [{req_type.upper()}] '{target}' ({title})")

        if hasattr(self, 'cloud_bridge') and self.cloud_bridge:
            try:
                self.cloud_bridge.push_data("/focus/requests.json", self.get_access_requests())
            except Exception:
                pass

        return {"success": True, "id": req_id, "request": new_req}

    def get_access_requests(self) -> list:
        """Returns list of student access requests."""
        raw = self.config.get("access_requests", [])
        return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []

    def resolve_access_request(self, req_id: str, decision: str) -> Dict[str, Any]:
        """Resolves access request by allowing or rejecting."""
        raw_requests = self.config.get("access_requests", [])
        requests = [r for r in raw_requests if isinstance(r, dict)] if isinstance(raw_requests, list) else []
        target_req = None
        for r in requests:
            if r.get("id") == req_id:
                target_req = r
                break

        if not target_req:
            return {"success": False, "error": "Request not found"}

        decision_clean = "approved" if decision in ("allow", "approved") else "rejected"
        target_req["status"] = decision_clean
        target_req["resolved_at"] = time.time()

        # If allowed, automatically add to corresponding whitelist!
        if decision_clean == "approved":
            req_type = target_req.get("type")
            target = target_req.get("target")
            if req_type == "channel" and target:
                clean_ch = "@" + target.lstrip("@")
                allowed_channels = self.config.get("allowed_channels", [])
                if clean_ch.lower() not in [c.lower() for c in allowed_channels]:
                    allowed_channels.append(clean_ch)
                    self.config.set("allowed_channels", allowed_channels)
                    print(f"[FOCUS Coordinator] Auto-approved channel: {clean_ch}")

            elif req_type == "website" and target:
                clean_site = target.lower().replace("https://", "").replace("http://", "").split("/")[0].strip()
                allowed_sites = self.config.get("allowed_sites", [])
                if clean_site not in [s.lower() for s in allowed_sites]:
                    allowed_sites.append(clean_site)
                    self.config.set("allowed_sites", allowed_sites)
                    print(f"[FOCUS Coordinator] Auto-approved website: {clean_site}")

            elif req_type == "video":
                # Option 2: Strict single-video whitelist
                # Only add this specific video to allowed_videos; creator's channel remains restricted!
                target_val = target_req.get("target") or target_req.get("url") or ""
                video_id = extract_youtube_video_id(target_val)
                if video_id:
                    self.config.db.add_allowed_video(
                        video_id=video_id,
                        title=target_req.get("title", f"Video {video_id}"),
                        channel=target_req.get("channel", "")
                    )
                    print(f"[FOCUS Coordinator] Auto-approved specific video ID: {video_id} (channel remains restricted)")

        self.config.set("access_requests", requests)

        if hasattr(self, 'cloud_bridge') and self.cloud_bridge:
            try:
                self.cloud_bridge.push_data("/focus/requests.json", self.get_access_requests())
                self.cloud_bridge.push_data("/focus/rules/allowed_channels.json", self.config.get("allowed_channels", []))
                self.cloud_bridge.push_data("/focus/rules/allowed_sites.json", self.config.get("allowed_sites", []))
                self.cloud_bridge.push_data("/focus/rules/allowed_videos.json", self.config.get("allowed_videos", []))
            except Exception:
                pass

        return {"success": True, "status": decision_clean, "request": target_req}

    def delete_access_request(self, req_id: str, target: str = "") -> Dict[str, Any]:
        """Deletes a specific access request from history or pending list."""
        raw_requests = self.config.get("access_requests", [])
        requests = [r for r in raw_requests if isinstance(r, dict)] if isinstance(raw_requests, list) else []
        target_id_str = str(req_id).strip() if req_id else ""
        target_val_str = str(target).strip() if target else ""

        new_requests = []
        for r in requests:
            r_id = str(r.get("id", "")).strip()
            r_target = str(r.get("target") or r.get("url") or "").strip()
            if target_id_str and r_id == target_id_str:
                continue
            if target_val_str and r_target == target_val_str:
                continue
            new_requests.append(r)

        self.config.set("access_requests", new_requests)
        if hasattr(self, 'cloud_bridge') and self.cloud_bridge:
            try:
                self.cloud_bridge.push_data("/focus/requests.json", new_requests)
            except Exception:
                pass
        return {"success": True, "deleted_id": req_id, "remaining": len(new_requests)}

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive status dictionary for web dashboard polling."""
        requests = self.config.get("access_requests", [])
        return {
            "online": True,
            "uptime_secs": int(time.time() - self.start_time),
            "focus_mode": self.config.get("focus_mode", False),
            "focus_expires_at": self.config.get("focus_expires_at", 0),
            "keyboard_locked": self.config.get("keyboard_locked", False),
            "max_tabs": self.config.get("max_tabs", 1),
            "min_tabs": self.config.get("min_tabs", 1),
            "max_tabs_range": self.config.get("max_tabs_range", 15),
            "active_window": get_active_window_info(),
            "pending_requests_count": sum(1 for r in requests if r.get("status") == "pending"),
            "requests": requests[:20],
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
        # Enforce single instance to prevent race conditions from duplicate autostart triggers
        self._instance_mutex = acquire_single_instance_mutex()
        if self._instance_mutex is None:
            print("[FOCUS Coordinator] Another instance of FOCUS daemon is already active. Exiting cleanly.")
            return

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
        self.web_server.start()
        self.cloud_bridge.start()

        # Re-apply safety defaults a second time after cloud bridge startup
        # (firebase_bridge._sync_initial_rules may run during .start() and
        # overwrite local config if rules arrive before our set() calls above)
        self.config.set("keyboard_locked", False)
        self.config.set("focus_mode", False)
        self.config.set("focus_expires_at", 0)

        # Spawn watchdog
        self.start_watchdog()

        print("[FOCUS Coordinator] All systems online.")
        print("[FOCUS Coordinator] Parent PIN security active.")
        print("[FOCUS Coordinator] Keep this process running or installed as Windows Service.")

        try:
            while True:
                # Check Focus Mode auto-expiry
                focus_active = self.config.get("focus_mode", False)
                expires_at = self.config.get("focus_expires_at", 0)
                if focus_active and expires_at > 0 and time.time() >= expires_at:
                    print("[FOCUS Coordinator] Focus Mode duration expired. Resetting.")
                    self.config.set("focus_mode", False)
                    self.config.set("focus_expires_at", 0)
                    set_task_manager_disabled(False)
                    if hasattr(self, 'cloud_bridge') and self.cloud_bridge:
                        self.cloud_bridge.push_data("/focus/status/focus_mode.json", False)
                        self.cloud_bridge.push_data("/focus/status/focus_expires_at.json", 0)
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        print("[FOCUS Coordinator] Shutting down...")
        self.keyboard_guard.stop()
        self.web_server.stop()
        self.cloud_bridge.stop()
        # Restore task manager before exiting
        set_task_manager_disabled(False)
        sys.exit(0)


if __name__ == "__main__":
    try:
        coordinator = MainCoordinator()
        coordinator.run()
    except Exception as exc:
        import traceback
        err_msg = f"[FOCUS Crash] {time.strftime('%Y-%m-%d %H:%M:%S')}: {exc}\n"
        print(err_msg, file=sys.stderr)
        try:
            with open(os.path.join(SCRIPT_DIR, "service.log"), "a", encoding="utf-8") as f:
                f.write(err_msg)
                traceback.print_exc(file=f)
        except Exception:
            pass
