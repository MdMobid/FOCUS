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

            # 2. Allowed Websites
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

            # 5. Allowed YouTube Specific Videos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS allowed_videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT UNIQUE COLLATE NOCASE NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    channel TEXT NOT NULL DEFAULT '',
                    added_at REAL NOT NULL
                );
            """)

            # 6. Activity Audit Logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT NOT NULL
                );
            """)

            # Column migrations for existing databases
            try:
                cursor.execute("ALTER TABLE allowed_videos ADD COLUMN channel TEXT NOT NULL DEFAULT '';")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE allowed_videos ADD COLUMN title TEXT NOT NULL DEFAULT '';")
            except Exception:
                pass

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
            "firebase_secret": "",
            "auto_request_policy": "manual",
            "auto_decline_during_focus": "0"
        }
        for k, v in default_settings.items():
            if self.get_setting(k) is None:
                self.set_setting(k, v)

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

    def get_allowed_videos(self) -> List[Dict[str, str]]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT video_id, title, channel FROM allowed_videos ORDER BY added_at DESC;")
            return [{"id": row["video_id"], "title": row["title"], "channel": row["channel"]} for row in cursor.fetchall()]

    def add_allowed_video(self, video_id: str, title: str = "", channel: str = "") -> bool:
        clean_id = video_id.strip()
        if not clean_id:
            return False
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO allowed_videos (video_id, title, channel, added_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(video_id) DO UPDATE SET title = excluded.title, channel = excluded.channel;",
                    (clean_id, title.strip(), channel.strip(), time.time())
                )
                conn.commit()
                return True
            except Exception:
                return False

    def remove_allowed_video(self, video_id: str) -> bool:
        clean_id = video_id.strip()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM allowed_videos WHERE video_id = ?;", (clean_id,))
            conn.commit()
            return cursor.rowcount > 0

    def set_allowed_videos(self, videos: List[Any]):
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM allowed_videos;")
            for item in videos:
                if isinstance(item, dict):
                    v_id = str(item.get("id", "")).strip()
                    title = str(item.get("title", "")).strip()
                    ch = str(item.get("channel", "")).strip()
                else:
                    v_id = str(item).strip()
                    title = ""
                    ch = ""
                if v_id:
                    cursor.execute(
                        "INSERT OR IGNORE INTO allowed_videos (video_id, title, channel, added_at) VALUES (?, ?, ?, ?);",
                        (v_id, title, ch, time.time())
                    )
            conn.commit()

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
            "auto_request_policy": self.get_setting("auto_request_policy", "manual") or "manual",
            "auto_decline_during_focus": self.get_setting("auto_decline_during_focus") == "1",
            "allowed_sites": self.get_allowed_sites(),
            "allowed_channels": self.get_allowed_channels(),
            "allowed_videos": self.get_allowed_videos(),
        }

    def log_event(self, event_type: str, details: str):
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO activity_logs (timestamp, event_type, details) VALUES (?, ?, ?);",
                           (time.time(), event_type, details))
            conn.commit()


# Singleton database instance
db = FocusDatabase()
