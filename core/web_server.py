"""
FOCUS: Embedded Web API Server & Dashboard Host
Serves the mobile-friendly Parent Dashboard and handles authenticated REST API endpoints.
Built purely with Python's standard library (http.server.ThreadingHTTPServer).
"""

import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import mimetypes
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from app_scanner import get_installed_apps

# Session storage for authenticated parent sessions
ACTIVE_SESSIONS = set()
SESSION_EXPIRY = {}


def generate_session_token(pin: str) -> str:
    raw = f"{pin}-{time.time()}-{os.urandom(8).hex()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def capture_screen_bmp_bytes() -> Optional[bytes]:
    """
    Captures the primary monitor using native Win32 GDI APIs (pure ctypes).
    Returns raw BMP bytes without requiring PIL or any external library.
    """
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        # Get screen dimensions
        SM_CXSCREEN = 0
        SM_CYSCREEN = 1
        width = user32.GetSystemMetrics(SM_CXSCREEN)
        height = user32.GetSystemMetrics(SM_CYSCREEN)

        hdesktop = user32.GetDesktopWindow()
        desktop_dc = user32.GetWindowDC(hdesktop)
        memory_dc = gdi32.CreateCompatibleDC(desktop_dc)

        bitmap = gdi32.CreateCompatibleBitmap(desktop_dc, width, height)
        gdi32.SelectObject(memory_dc, bitmap)

        # BitBlt screen into memory DC
        SRCCOPY = 0x00CC0020
        gdi32.BitBlt(memory_dc, 0, 0, width, height, desktop_dc, 0, 0, SRCCOPY)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = width
        bmi.biHeight = height
        bmi.biPlanes = 1
        bmi.biBitCount = 24
        bmi.biCompression = 0  # BI_RGB

        row_size = ((width * 24 + 31) // 32) * 4
        image_size = row_size * height
        buffer = (ctypes.c_char * image_size)()

        gdi32.GetDIBits(memory_dc, bitmap, 0, height, ctypes.byref(buffer), ctypes.byref(bmi), 0)

        # Build BMP File Header
        file_header_size = 14
        total_file_size = file_header_size + bmi.biSize + image_size
        bfType = b"BM"
        bfReserved = b"\x00\x00\x00\x00"
        bfOffBits = (file_header_size + bmi.biSize).to_bytes(4, byteorder="little")
        header = bfType + total_file_size.to_bytes(4, byteorder="little") + bfReserved + bfOffBits
        info_header = bytes(bmi)

        # Clean up GDI objects
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hdesktop, desktop_dc)

        return header + info_header + bytes(buffer)
    except Exception as exc:
        print(f"[FOCUS Screenshot] GDI capture failed: {exc}", file=sys.stderr)
        return None


class FocusRequestHandler(BaseHTTPRequestHandler):
    coordinator = None  # Injected reference to MainCoordinator
    dashboard_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")

    def _send_json(self, status_code: int, data: Dict[str, Any]):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def _is_authenticated(self) -> bool:
        auth_header = self.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip()
        if not token:
            return False
        if token in ACTIVE_SESSIONS:
            if time.time() < SESSION_EXPIRY.get(token, 0):
                return True
            else:
                ACTIVE_SESSIONS.discard(token)
        return False

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Public Rules API for extension sync
        if path == "/api/rules":
            if self.coordinator:
                rules = self.coordinator.config.get_all()
                self._send_json(200, rules)
            else:
                self._send_json(500, {"error": "Coordinator unavailable"})
            return

        # Status endpoint (Live PC stats)
        if path == "/api/status":
            if not self._is_authenticated():
                self._send_json(401, {"error": "Unauthorized"})
                return
            status_data = self.coordinator.get_status() if self.coordinator else {}
            self._send_json(200, status_data)
            return

        # Installed Apps endpoint
        if path == "/api/installed_apps":
            if not self._is_authenticated():
                self._send_json(401, {"error": "Unauthorized"})
                return
            installed = get_installed_apps()
            self._send_json(200, {"apps": installed})
            return

        # Screenshot capture endpoint
        if path == "/api/screenshot":
            if not self._is_authenticated():
                self._send_json(401, {"error": "Unauthorized"})
                return
            bmp_bytes = capture_screen_bmp_bytes()
            if bmp_bytes:
                self.send_response(200)
                self.send_header("Content-Type", "image/bmp")
                self.send_header("Content-Length", str(len(bmp_bytes)))
                self.end_headers()
                self.wfile.write(bmp_bytes)
            else:
                self._send_json(500, {"error": "Failed to capture screen"})
            return

        # Serve static dashboard files
        if path == "/":
            path = "/index.html"
        safe_path = os.path.normpath(path.lstrip("/\\"))
        file_path = os.path.abspath(os.path.join(self.dashboard_dir, safe_path))

        # Security: Prevent directory traversal out of dashboard_dir
        if not file_path.startswith(os.path.abspath(self.dashboard_dir)):
            self.send_error(403, "Forbidden")
            return

        if os.path.isfile(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            mime_type = mime_type or "application/octet-stream"
            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except Exception as exc:
                self.send_error(500, f"Error reading file: {exc}")
        else:
            self.send_error(404, "File not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.wfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            payload = {}

        # Login endpoint
        if path == "/api/login":
            pin = payload.get("pin", "")
            if self.coordinator and self.coordinator.config.verify_pin(pin):
                token = generate_session_token(pin)
                ACTIVE_SESSIONS.add(token)
                SESSION_EXPIRY[token] = time.time() + (86400 * 7)  # 7-day session
                self._send_json(200, {"success": True, "token": token})
            else:
                self._send_json(403, {"success": False, "error": "Invalid PIN"})
            return

        # All other POST endpoints require authentication
        if not self._is_authenticated():
            self._send_json(401, {"error": "Unauthorized"})
            return

        # Action execution endpoint
        if path == "/api/action":
            action = payload.get("action")
            result = self.coordinator.handle_action(action, payload) if self.coordinator else False
            self._send_json(200, {"success": result, "action": action})
            return

        # Whitelist update endpoint
        if path == "/api/rules":
            if self.coordinator:
                self.coordinator.update_rules(payload)
                self._send_json(200, {"success": True, "rules": self.coordinator.config.get_all()})
            else:
                self._send_json(500, {"error": "Coordinator unavailable"})
            return

        # Change Master PIN endpoint
        if path == "/api/change_pin":
            old_pin = payload.get("old_pin", "")
            new_pin = payload.get("new_pin", "")
            if self.coordinator and self.coordinator.config.change_pin(old_pin, new_pin):
                self._send_json(200, {"success": True, "message": "PIN updated"})
            else:
                self._send_json(400, {"success": False, "error": "Incorrect current PIN"})
            return

        self.send_error(404, "Not Found")

    def log_message(self, format, *args):
        # Suppress noisy standard logging, log errors only
        if args and str(args[0]).startswith("5"):
            super().log_message(format, *args)


class EmbeddedWebServer:
    def __init__(self, port: int, coordinator):
        self.port = port
        self.coordinator = coordinator
        self.httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        FocusRequestHandler.coordinator = self.coordinator
        self.httpd = ThreadingHTTPServer(("0.0.0.0", self.port), FocusRequestHandler)
        print(f"[FOCUS WebServer] Parent Web Dashboard live on http://localhost:{self.port}")
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            print("[FOCUS WebServer] Web server stopped.")
