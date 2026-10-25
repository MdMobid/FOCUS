"""
FOCUS: Firebase Realtime Cloud Bridge
Enables secure remote control across 1,000+ km without inbound ports or tunnels.
Connects outbound to Google Firebase Realtime Database via standard HTTPS & Server-Sent Events (SSE).
Implemented with pure Python standard library (urllib.request) - ZERO third-party pip dependencies.
"""

import base64
import json
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Optional
import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


class FirebaseCloudBridge:
    def __init__(self, db_url: str, db_secret: str, coordinator):
        """
        :param db_url: e.g. "https://your-focus-project-default-rtdb.firebaseio.com"
        :param db_secret: Database Secret or Auth token for secure access
        :param coordinator: Reference to MainCoordinator
        """
        self.db_url = db_url.rstrip("/")
        self.db_secret = db_secret.strip()
        self.coordinator = coordinator
        self._stop_event = threading.Event()
        self._listener_thread: Optional[threading.Thread] = None
        self._telemetry_thread: Optional[threading.Thread] = None
        self._processed_command_ids = set()
        self._last_processed_timestamp = 0.0

    def _build_url(self, path: str) -> str:
        clean_path = path.lstrip("/")
        if self.db_secret:
            return f"{self.db_url}/{clean_path}?auth={self.db_secret}"
        return f"{self.db_url}/{clean_path}"

    def push_data(self, path: str, data: Dict[str, Any], method: str = "PUT") -> bool:
        """Sends data outbound to Firebase via standard HTTPS."""
        try:
            url = self._build_url(path)
            json_bytes = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(url, data=json_bytes, method=method)
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status in (200, 204)
        except Exception:
            return False

    def _telemetry_loop(self):
        """Periodically pushes live status and installed apps to Firebase."""
        print("[FOCUS Cloud] Telemetry publisher started (pushing every 3s).")
        last_apps_sync = 0

        while not self._stop_event.is_set():
            try:
                status = self.coordinator.get_status()
                status["last_seen"] = int(time.time())
                self.push_data("/focus/status.json", status)

                # Sync student access requests every loop
                requests = self.coordinator.get_access_requests()
                self.push_data("/focus/requests.json", requests)

                # Sync installed apps every 120 seconds
                if time.time() - last_apps_sync > 120:
                    try:
                        from app_scanner import get_installed_apps
                        installed = get_installed_apps()
                        self.push_data("/focus/installed_apps.json", {"apps": installed})
                        last_apps_sync = time.time()
                    except Exception:
                        pass

            except Exception as exc:
                print(f"[FOCUS Cloud] Telemetry push error: {exc}", file=sys.stderr)

            time.sleep(3.0)

    def _command_listener_loop(self):
        """
        Listens to real-time command events streamed by Google Firebase using SSE.
        Receives parent commands within 50-100 milliseconds via outbound connection.
        """
        print(f"[FOCUS Cloud] Connecting outbound to Firebase: {self.db_url}...")

        while not self._stop_event.is_set():
            stream_url = self._build_url("/focus/command.json")
            req = urllib.request.Request(stream_url)
            req.add_header("Accept", "text/event-stream")

            try:
                # Open persistent SSE stream
                with urllib.request.urlopen(req, timeout=60) as resp:
                    print("[FOCUS Cloud] Real-time cloud listener connected. Waiting for parent commands.")
                    event_type = ""
                    for line_bytes in resp:
                        if self._stop_event.is_set():
                            break

                        line = line_bytes.decode("utf-8").strip()
                        if not line:
                            continue

                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "null":
                                continue
                            try:
                                payload = json.loads(data_str)
                                self._handle_cloud_event(event_type, payload)
                            except Exception:
                                pass

            except Exception:
                # Reconnection delay if internet disconnects or 60s stream timeout
                time.sleep(2.0)


    def _handle_cloud_event(self, event_type: str, data: Any):
        """Processes command payloads pushed from the parent's phone."""
        if not isinstance(data, dict):
            return

        cmd_obj = data.get("data") if "data" in data and isinstance(data["data"], dict) else data

        action = cmd_obj.get("action")
        cmd_id = cmd_obj.get("id")
        timestamp = float(cmd_obj.get("timestamp", 0))

        # Normalize JS millisecond timestamp (Date.now()) to seconds
        if timestamp > 1e11:
            timestamp /= 1000.0

        if not action:
            return

        # Anti-replay & Deduplication
        if cmd_id:
            cmd_id_str = str(cmd_id)
            if cmd_id_str in self._processed_command_ids:
                return
            self._processed_command_ids.add(cmd_id_str)
            if len(self._processed_command_ids) > 1000:
                try:
                    self._processed_command_ids.pop()
                except KeyError:
                    pass
        else:
            # Fallback if no ID is sent by legacy client
            if timestamp <= self._last_processed_timestamp:
                return
            self._last_processed_timestamp = timestamp

        print(f"[FOCUS Cloud] Received parent command: '{action}' (ID: {cmd_id or 'none'})")

        # Execute action on local machine
        success = self.coordinator.handle_action(action, cmd_obj)

        # Immediately update status on Firebase so dashboard reflects it instantly
        try:
            status = self.coordinator.get_status()
            status["last_seen"] = int(time.time())
            self.push_data("/focus/status.json", status)
        except Exception:
            pass

        # Handle screenshot capture for remote parent
        if action == "screenshot":
            try:
                from web_server import capture_screen_bytes
                img_bytes, mime = capture_screen_bytes()
                if img_bytes:
                    b64 = base64.b64encode(img_bytes).decode("ascii")
                    self.push_data("/focus/screenshot.json", {
                        "image": f"data:{mime};base64,{b64}",
                        "cmd_id": cmd_id or "",
                        "timestamp": time.time()
                    })
                    print(f"[FOCUS Cloud] Screenshot captured and published ({len(img_bytes)} bytes, {mime}).")
                    success = True
            except Exception as e:
                print(f"[FOCUS Cloud] Screenshot capture failed: {e}", file=sys.stderr)

        # Handle rules sync if rules were updated remotely
        if action == "sync_rules" and "rules" in cmd_obj:
            self.coordinator.update_rules(cmd_obj["rules"])

        # Handle access request resolution from cloud
        if action == "resolve_request":
            req_id = cmd_obj.get("request_id") or cmd_obj.get("id")
            decision = cmd_obj.get("decision", "reject")
            self.coordinator.resolve_access_request(req_id, decision)

        # Push immediate confirmation
        self.push_data("/focus/command_ack.json", {
            "id": cmd_id or "",
            "action": action,
            "timestamp": timestamp,
            "success": success,
            "executed_at": time.time()
        })

    def _sync_initial_rules(self):
        """Syncs master rules between Firebase RTDB and local PC."""
        STARTUP_RESET_KEYS = {"keyboard_locked", "focus_mode", "focus_expires_at"}

        try:
            # Sync parent PIN hash securely to Firebase RTDB for web dashboard auth
            pin_hash = self.coordinator.config.get("pin_hash", "")
            if pin_hash:
                self.push_data("/focus/security.json", {"pin_hash": pin_hash})

            url = self._build_url("/focus/rules.json")
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data_str = resp.read().decode("utf-8")
                remote_data = json.loads(data_str) if data_str else None
                if remote_data and isinstance(remote_data, dict):
                    # Strip safety-critical keys — they are always reset locally on boot
                    for key in STARTUP_RESET_KEYS:
                        remote_data.pop(key, None)
                    print("[FOCUS Cloud] Downloaded master rules from Firebase RTDB (safety keys excluded).")
                    self.coordinator.update_rules(remote_data)
                else:
                    # Populate Firebase RTDB with default rules
                    local_rules = self.coordinator.config.get_all()
                    self.push_data("/focus/rules.json", local_rules)
                    print("[FOCUS Cloud] Initialized Firebase RTDB with default rules.")

            # Record any existing command in Firebase so it's not replayed on boot
            try:
                cmd_url = self._build_url("/focus/command.json")
                cmd_req = urllib.request.Request(cmd_url)
                with urllib.request.urlopen(cmd_req, timeout=5) as c_resp:
                    raw = c_resp.read().decode("utf-8")
                    if raw and raw != "null":
                        existing_cmd = json.loads(raw)
                        if isinstance(existing_cmd, dict):
                            e_id = existing_cmd.get("id")
                            if e_id:
                                self._processed_command_ids.add(str(e_id))
                            e_ts = float(existing_cmd.get("timestamp", 0))
                            if e_ts > 1e11:
                                e_ts /= 1000.0
                            self._last_processed_timestamp = max(self._last_processed_timestamp, e_ts)
            except Exception:
                pass

            # Always push the safe startup defaults back to Firebase
            # so the dashboard reflects the actual current state immediately
            self.push_data("/focus/rules/keyboard_locked.json", False)
            self.push_data("/focus/rules/focus_mode.json", False)
            self.push_data("/focus/rules/focus_expires_at.json", 0)

        except Exception as exc:
            print(f"[FOCUS Cloud] Rules sync error: {exc}", file=sys.stderr)


    def start(self):
        """Starts the outbound telemetry publisher and command listener threads."""
        if not self.db_url:
            print("[FOCUS Cloud] Firebase URL not configured. Running in Local LAN mode.")
            return

        self._sync_initial_rules()

        # Immediately push the true current state so the dashboard doesn't have
        # to wait up to 3s for the first telemetry tick to reflect reality.
        try:
            status = self.coordinator.get_status()
            status["last_seen"] = int(time.time())
            self.push_data("/focus/status.json", status)
        except Exception:
            pass

        self._stop_event.clear()
        self._listener_thread = threading.Thread(target=self._command_listener_loop, daemon=True)
        self._telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)

        self._listener_thread.start()
        self._telemetry_thread.start()


    def stop(self):
        self._stop_event.set()
