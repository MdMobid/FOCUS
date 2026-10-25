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
from typing import Any, Dict, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Session storage for authenticated parent sessions
ACTIVE_SESSIONS = set()
SESSION_EXPIRY = {}


def generate_session_token(pin: str) -> str:
    raw = f"{pin}-{time.time()}-{os.urandom(8).hex()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _capture_gdiplus_jpeg() -> Optional[bytes]:
    """Captures screen as lightweight JPEG (15-40KB) via native Windows GDI+."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalSize.restype = ctypes.c_size_t
        kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

        ole32 = ctypes.windll.ole32
        gdiplus = ctypes.windll.gdiplus
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        class GdiplusStartupInput(ctypes.Structure):
            _fields_ = [('GdiplusVersion', wintypes.UINT),
                        ('DebugEventCallback', ctypes.c_void_p),
                        ('SuppressBackgroundThread', wintypes.BOOL),
                        ('SuppressExternalCodecs', wintypes.BOOL)]

        token = ctypes.c_ulong()
        startup_in = GdiplusStartupInput(1, None, False, False)
        if gdiplus.GdiplusStartup(ctypes.byref(token), ctypes.byref(startup_in), None) != 0:
            return None

        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        hdesk = user32.GetDesktopWindow()
        desk_dc = user32.GetWindowDC(hdesk)
        mem_dc = gdi32.CreateCompatibleDC(desk_dc)
        hbm = gdi32.CreateCompatibleBitmap(desk_dc, w, h)
        gdi32.SelectObject(mem_dc, hbm)
        gdi32.BitBlt(mem_dc, 0, 0, w, h, desk_dc, 0, 0, 0x00CC0020)

        gp_bitmap = ctypes.c_void_p()
        gdiplus.GdipCreateBitmapFromHBITMAP(hbm, 0, ctypes.byref(gp_bitmap))

        class GUID(ctypes.Structure):
            _fields_ = [('Data1', wintypes.DWORD),
                        ('Data2', wintypes.WORD),
                        ('Data3', wintypes.WORD),
                        ('Data4', ctypes.c_ubyte * 8)]

        # CLSID for GDI+ JPEG Encoder: {557cf401-1a04-11d3-9a73-0000f81ef32e}
        jpeg_clsid = GUID(0x557cf401, 0x1a04, 0x11d3, (ctypes.c_ubyte * 8)(0x9a, 0x73, 0x00, 0x00, 0xf8, 0x1e, 0xf3, 0x2e))

        p_stream = ctypes.c_void_p()
        ole32.CreateStreamOnHGlobal(None, True, ctypes.byref(p_stream))

        jpeg_bytes = None
        if gdiplus.GdipSaveImageToStream(gp_bitmap, p_stream, ctypes.byref(jpeg_clsid), None) == 0:
            hglobal = ctypes.c_void_p()
            ole32.GetHGlobalFromStream(p_stream, ctypes.byref(hglobal))
            size = kernel32.GlobalSize(hglobal)
            ptr = kernel32.GlobalLock(hglobal)
            if ptr:
                jpeg_bytes = ctypes.string_at(ptr, size)
                kernel32.GlobalUnlock(hglobal)

        gdiplus.GdipDisposeImage(gp_bitmap)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hdesk, desk_dc)
        gdiplus.GdiplusShutdown(token)
        return jpeg_bytes
    except Exception:
        return None


def _capture_gdi_bmp() -> Optional[bytes]:
    """Captures the primary monitor using native Win32 GDI APIs (pure ctypes) as raw BMP."""
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        hdesktop = user32.GetDesktopWindow()
        desktop_dc = user32.GetWindowDC(hdesktop)
        memory_dc = gdi32.CreateCompatibleDC(desktop_dc)

        bitmap = gdi32.CreateCompatibleBitmap(desktop_dc, w, h)
        gdi32.SelectObject(memory_dc, bitmap)
        gdi32.BitBlt(memory_dc, 0, 0, w, h, desktop_dc, 0, 0, 0x00CC0020)

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
        bmi.biWidth = w
        bmi.biHeight = h
        bmi.biPlanes = 1
        bmi.biBitCount = 24
        bmi.biCompression = 0

        row_size = ((w * 24 + 31) // 32) * 4
        image_size = row_size * h
        buffer = (ctypes.c_char * image_size)()

        gdi32.GetDIBits(memory_dc, bitmap, 0, h, ctypes.byref(buffer), ctypes.byref(bmi), 0)

        file_header_size = 14
        total_file_size = file_header_size + bmi.biSize + image_size
        bfType = b"BM"
        bfReserved = b"\x00\x00\x00\x00"
        bfOffBits = (file_header_size + bmi.biSize).to_bytes(4, byteorder="little")
        header = bfType + total_file_size.to_bytes(4, byteorder="little") + bfReserved + bfOffBits

        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hdesktop, desktop_dc)

        return header + bytes(bmi) + bytes(buffer)
    except Exception as exc:
        print(f"[FOCUS Screenshot] GDI capture failed: {exc}", file=sys.stderr)
        return None


def capture_screen_bytes() -> Tuple[Optional[bytes], str]:
    """Returns (image_bytes, mime_type). Prefers compressed JPEG (~20KB), falls back to BMP."""
    jpeg = _capture_gdiplus_jpeg()
    if jpeg:
        return jpeg, "image/jpeg"
    bmp = _capture_gdi_bmp()
    if bmp:
        return bmp, "image/bmp"
    return None, "image/jpeg"


def capture_screen_bmp_bytes() -> Optional[bytes]:
    """Backward compatibility helper."""
    return capture_screen_bytes()[0]


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
                rules["daemon_version"] = str(getattr(self.coordinator, "start_time", 0))
                rules["min_tabs"] = self.coordinator.config.get("min_tabs", 1)
                rules["max_tabs_range"] = self.coordinator.config.get("max_tabs_range", 15)
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



        # Screenshot capture endpoint
        if path == "/api/screenshot":
            if not self._is_authenticated():
                self._send_json(401, {"error": "Unauthorized"})
                return
            img_bytes, mime = capture_screen_bytes()
            if img_bytes:
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(img_bytes)))
                self.end_headers()
                self.wfile.write(img_bytes)
            else:
                self._send_json(500, {"error": "Failed to capture screen"})
            return

        # Access Requests list endpoint
        if path == "/api/requests":
            if not self._is_authenticated():
                self._send_json(401, {"error": "Unauthorized"})
                return
            requests = self.coordinator.get_access_requests() if self.coordinator else []
            self._send_json(200, {"requests": requests})
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
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b"{}"
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

        # Student Access Request endpoint (Unauthenticated - called from extension popup & blocked page)
        if path == "/api/request_access":
            if self.coordinator:
                res = self.coordinator.record_access_request(payload)
                self._send_json(200, res)
            else:
                self._send_json(500, {"error": "Coordinator unavailable"})
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

        # Resolve Access Request endpoint (Allow / Reject)
        if path == "/api/resolve_request":
            req_id = payload.get("id") or payload.get("request_id")
            decision = payload.get("decision", "reject")
            if self.coordinator:
                res = self.coordinator.resolve_access_request(req_id, decision)
                self._send_json(200, res)
            else:
                self._send_json(500, {"error": "Coordinator unavailable"})
            return

        # Delete Access Request endpoint
        if path == "/api/delete_request":
            req_id = payload.get("id") or payload.get("request_id")
            target = payload.get("target", "")
            if self.coordinator:
                res = self.coordinator.delete_access_request(req_id, target)
                self._send_json(200, res)
            else:
                self._send_json(500, {"error": "Coordinator unavailable"})
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
