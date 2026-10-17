"""
FOCUS: Configuration & Rule Manager (SQLite Backed)
Wraps SQLite database for atomic reading/writing, whitelists, PIN hashing, and settings.
Zero external dependencies.
"""

import hashlib
import os
import sys
from typing import Any, Dict, List, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from database import db


def hash_pin(pin: str) -> str:
    """Returns SHA-256 hash of the parent PIN string."""
    return hashlib.sha256(pin.strip().encode("utf-8")).hexdigest()


class ConfigManager:
    def __init__(self, database=db):
        self.db = database
        self._sync_from_rules_json_if_present()

    def _sync_from_rules_json_if_present(self):
        """Automatically imports settings from rules.json into SQLite if present."""
        rules_path = os.path.join(os.path.dirname(SCRIPT_DIR), "config", "rules.json")
        if os.path.exists(rules_path):
            try:
                import json
                with open(rules_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    fb_url = data.get("firebase_url", "").strip()
                    fb_secret = data.get("firebase_secret", "").strip()
                    if fb_url:
                        self.db.set_setting("firebase_url", fb_url)
                    if fb_secret:
                        self.db.set_setting("firebase_secret", fb_secret)
                    if "pin_hash" in data and data["pin_hash"]:
                        self.db.set_setting("pin_hash", data["pin_hash"])
            except Exception:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        if key == "allowed_apps":
            return self.db.get_allowed_apps()
        elif key == "allowed_sites":
            return self.db.get_allowed_sites()
        elif key == "allowed_channels":
            return self.db.get_allowed_channels()
        elif key == "focus_mode":
            val = self.db.get_setting("focus_mode")
            return val == "1" if val is not None else default
        elif key == "keyboard_locked":
            val = self.db.get_setting("keyboard_locked")
            return val == "1" if val is not None else default
        elif key in ("focus_expires_at", "server_port", "max_tabs"):
            val = self.db.get_setting(key)
            if val is not None:
                try:
                    return float(val) if "." in val else int(val)
                except ValueError:
                    return default
            return default

        val = self.db.get_setting(key)
        if val is not None and val != "":
            return val

        # Fallback to rules.json if present
        rules_path = os.path.join(os.path.dirname(SCRIPT_DIR), "config", "rules.json")
        if os.path.exists(rules_path):
            try:
                import json
                with open(rules_path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    if key in file_data and file_data[key]:
                        return file_data[key]
            except Exception:
                pass

        return default

    def set(self, key: str, value: Any) -> None:
        if key == "allowed_apps" and isinstance(value, list):
            # Replace allowed apps
            current = set(self.db.get_allowed_apps())
            new_set = {str(x).strip().lower() for x in value}
            for x in current - new_set:
                self.db.remove_allowed_app(x)
            for x in new_set - current:
                self.db.add_allowed_app(x)
            return

        if key == "allowed_sites" and isinstance(value, list):
            current = set(self.db.get_allowed_sites())
            new_set = {str(x).strip().lower() for x in value}
            for x in current - new_set:
                self.db.remove_allowed_site(x)
            for x in new_set - current:
                self.db.add_allowed_site(x)
            return

        if key == "allowed_channels" and isinstance(value, list):
            current = set(self.db.get_allowed_channels())
            new_set = {str(x).strip().lower() for x in value}
            for x in current - new_set:
                self.db.remove_allowed_channel(x)
            for x in new_set - current:
                self.db.add_allowed_channel(x)
            return

        # Boolean conversion for DB storage
        if isinstance(value, bool):
            db_val = "1" if value else "0"
        else:
            db_val = str(value)

        self.db.set_setting(key, db_val)

    def verify_pin(self, candidate_pin: str) -> bool:
        candidate_hash = hash_pin(candidate_pin)
        stored_hash = self.get("pin_hash", "")
        return candidate_hash == stored_hash

    def change_pin(self, old_pin: str, new_pin: str) -> bool:
        if not self.verify_pin(old_pin):
            return False
        self.set("pin_hash", hash_pin(new_pin))
        return True

    def get_all(self) -> Dict[str, Any]:
        rules = self.db.get_all_rules()
        return rules


# Global singleton instance
config = ConfigManager()
