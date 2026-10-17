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
        self._last_processed_timestamp = 0

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
        except Exception as exc:
            # Silent fallback if network temporarily drops
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
                            except Exception as json_err:
                                pass

            except Exception as stream_err:
                # Reconnection delay if internet disconnects
                time.sleep(3.0)

    def _handle_cloud_event(self, event_type: str, data: Any):
        """Processes command payloads pushed from the parent's phone."""
        if not isinstance(data, dict):
            return

        # Firebase 'put' event may nest payload in 'data'
        cmd_obj = data.get("data") if "data" in data and isinstance(data["data"], dict) else data

        action = cmd_obj.get("action")
        timestamp = float(cmd_obj.get("timestamp", 0))

        # Ignore stale or previously executed commands
        if not action or timestamp <= self._last_processed_timestamp:
            return

        self._last_processed_timestamp = timestamp
        print(f"[FOCUS Cloud] Received parent command from 1,000km: '{action}'")

        # Execute action on local machine
        success = self.coordinator.handle_action(action, cmd_obj)

        # Handle screenshot capture for remote parent
        if action == "screenshot":
            try:
                from web_server import capture_screen_bmp_bytes
                bmp = capture_screen_bmp_bytes()
                if bmp:
                    b64 = base64.b64encode(bmp).decode("ascii")
                    self.push_data("/focus/screenshot.json", {
                        "image": f"data:image/bmp;base64,{b64}",
                        "timestamp": time.time()
                    })
                    success = True
            except Exception as e:
                print(f"[FOCUS Cloud] Screenshot capture failed: {e}", file=sys.stderr)

        # Handle rules sync if rules were updated remotely
        if action == "sync_rules" and "rules" in cmd_obj:
            self.coordinator.update_rules(cmd_obj["rules"])

        # Push immediate confirmation
        self.push_data("/focus/command_ack.json", {
            "action": action,
            "timestamp": timestamp,
            "success": success,
            "executed_at": time.time()
        })

    def _sync_initial_rules(self):
        """Syncs master rules between Firebase RTDB and local PC."""
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
                    print("[FOCUS Cloud] Downloaded master rules from Firebase RTDB.")
                    self.coordinator.update_rules(remote_data)
                else:
                    # Populate Firebase RTDB with default rules
                    local_rules = self.coordinator.config.get_all()
                    self.push_data("/focus/rules.json", local_rules)
                    print("[FOCUS Cloud] Initialized Firebase RTDB with default rules.")
        except Exception as exc:
            print(f"[FOCUS Cloud] Rules sync error: {exc}", file=sys.stderr)

    def start(self):
        """Starts the outbound telemetry publisher and command listener threads."""
        if not self.db_url:
            print("[FOCUS Cloud] Firebase URL not configured. Running in Local LAN mode.")
            return

        self._sync_initial_rules()
        self._stop_event.clear()
        self._listener_thread = threading.Thread(target=self._command_listener_loop, daemon=True)
        self._telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)

        self._listener_thread.start()
        self._telemetry_thread.start()

    def stop(self):
        self._stop_event.set()
