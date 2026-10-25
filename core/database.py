"""
FOCUS: SQLite Database Layer
Stores all rules, whitelists, settings, and activity logs in a persistent SQLite database.
Built using Python's standard library (sqlite3) - ZERO external dependencies.
"""

from contextlib import contextmanager
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "focus.db")


class FocusDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self):
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Key-Value Configuration Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

            # 2. Allowed Applications
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS allowed_apps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE COLLATE NOCASE NOT NULL,
                    added_at REAL NOT NULL
                );
            """)

            # 3. Allowed Websites
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS allowed_sites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT UNIQUE COLLATE NOCASE NOT NULL,
                    added_at REAL NOT NULL
                );
            """)

            # 4. Allowed YouTube Channels
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS allowed_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    handle TEXT UNIQUE COLLATE NOCASE NOT NULL,
                    added_at REAL NOT NULL
                );
            """)

            # 5. Activity Audit Logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT NOT NULL
                );
            """)
            conn.commit()

        # Seed initial defaults if newly created
        self._seed_defaults()

    def _seed_defaults(self):
        # Default Settings
        default_settings = {
            "pin_hash": "03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4",  # 1234
            "focus_mode": "0",
            "focus_expires_at": "0",
            "keyboard_locked": "0",
            "max_tabs": "1",
            "min_tabs": "1",
            "max_tabs_range": "15",
            "server_port": "8443",
            "firebase_url": "",
            "firebase_secret": ""
        }
        for k, v in default_settings.items():
            if self.get_setting(k) is None:
                self.set_setting(k, v)

        # Default Apps
        default_apps = [
            "chrome.exe", "msedge.exe", "notepad.exe", "calc.exe",
            "code.exe", "python.exe", "pythonw.exe", "focus.exe",
            "antigravity ide.exe", "antigravity.exe", "antigravity-ide.exe",
            "node.exe", "language_server_windows_x64.exe", "pyrefly.exe"
        ]
        for app in default_apps:
            self.add_allowed_app(app)

        # Default Sites
        default_sites = [
            "khanacademy.org", "wikipedia.org", "youtube.com", "github.com", "google.com"
        ]
        for site in default_sites:
            self.add_allowed_site(site)

        # Default Channels
        default_channels = [
            "@freecodecamp", "@khanacademy", "@veritasium", "@3blue1brown"
        ]
        for channel in default_channels:
            self.add_allowed_channel(channel)

    # --- Settings Operations ---
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: Any):
        str_val = str(value)
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """, (key, str_val))
            conn.commit()

    # --- Whitelist Operations ---
    def get_allowed_apps(self) -> List[str]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM allowed_apps ORDER BY name ASC;")
            return [row["name"] for row in cursor.fetchall()]

    def add_allowed_app(self, name: str) -> bool:
        clean = name.strip().lower()
        if not clean:
            return False
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT OR IGNORE INTO allowed_apps (name, added_at) VALUES (?, ?);", (clean, time.time()))
                conn.commit()
                return True
            except Exception:
                return False

    def remove_allowed_app(self, name: str) -> bool:
        clean = name.strip().lower()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM allowed_apps WHERE name = ?;", (clean,))
            conn.commit()
            return cursor.rowcount > 0

    def get_allowed_sites(self) -> List[str]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT domain FROM allowed_sites ORDER BY domain ASC;")
            return [row["domain"] for row in cursor.fetchall()]

    def add_allowed_site(self, domain: str) -> bool:
        clean = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
        if not clean:
            return False
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT OR IGNORE INTO allowed_sites (domain, added_at) VALUES (?, ?);", (clean, time.time()))
                conn.commit()
                return True
            except Exception:
                return False

    def remove_allowed_site(self, domain: str) -> bool:
        clean = domain.strip().lower()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM allowed_sites WHERE domain = ?;", (clean,))
            conn.commit()
            return cursor.rowcount > 0

    def get_allowed_channels(self) -> List[str]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT handle FROM allowed_channels ORDER BY handle ASC;")
            return [row["handle"] for row in cursor.fetchall()]

    def add_allowed_channel(self, handle: str) -> bool:
        clean = handle.strip().lower()
        if not clean:
            return False
        if not clean.startswith("@"):
            clean = "@" + clean
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT OR IGNORE INTO allowed_channels (handle, added_at) VALUES (?, ?);", (clean, time.time()))
                conn.commit()
                return True
            except Exception:
                return False

    def remove_allowed_channel(self, handle: str) -> bool:
        clean = handle.strip().lower()
        if not clean.startswith("@"):
            clean = "@" + clean
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM allowed_channels WHERE handle = ?;", (clean,))
            conn.commit()
            return cursor.rowcount > 0

    # --- Aggregated Rules Representation ---
    def get_all_rules(self) -> Dict[str, Any]:
        return {
            "focus_mode": self.get_setting("focus_mode") == "1",
            "focus_expires_at": float(self.get_setting("focus_expires_at", "0")),
            "keyboard_locked": self.get_setting("keyboard_locked") == "1",
            "max_tabs": int(self.get_setting("max_tabs", "1")),
            "min_tabs": int(self.get_setting("min_tabs", "1")),
            "max_tabs_range": int(self.get_setting("max_tabs_range", "15")),
            "server_port": int(self.get_setting("server_port", "8443")),
            "firebase_url": self.get_setting("firebase_url", ""),
            "allowed_apps": self.get_allowed_apps(),
            "allowed_sites": self.get_allowed_sites(),
            "allowed_channels": self.get_allowed_channels(),
        }

    def log_event(self, event_type: str, details: str):
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO activity_logs (timestamp, event_type, details) VALUES (?, ?, ?);",
                           (time.time(), event_type, details))
            conn.commit()


# Singleton database instance
db = FocusDatabase()
