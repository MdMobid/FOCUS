"""
FOCUS: Change Master PIN Utility
Interactive utility to safely change the Parent Master PIN in SQLite focus.db and rules.json.
Uses pure Python standard library (hashlib, getpass).
"""

import getpass
import hashlib
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CORE_DIR = os.path.join(PROJECT_DIR, "core")
CONFIG_FILE = os.path.join(PROJECT_DIR, "config", "rules.json")

if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

# pyrefly: ignore[missing-import]
from config_manager import config, hash_pin


def main():
    print("=" * 50)
    print("        FOCUS: Change Parent Master PIN")
    print("=" * 50)

    # 1. Verify current PIN
    current_pin = getpass.getpass("Enter current Master PIN (default is 1234): ").strip()
    if not config.verify_pin(current_pin):
        print("\n[ERROR] Incorrect current Master PIN! Access denied.")
        sys.exit(1)

    # 2. Prompt for new PIN
    while True:
        new_pin = getpass.getpass("\nEnter new Master PIN: ").strip()
        if len(new_pin) < 4:
            print("[!] PIN should be at least 4 digits/characters. Try again.")
            continue

        confirm_pin = getpass.getpass("Confirm new Master PIN: ").strip()
        if new_pin != confirm_pin:
            print("[!] PINs do not match. Try again.")
            continue
        break

    # 3. Calculate new hash
    new_hash = hash_pin(new_pin)

    # 4. Update SQLite database
    config.set("pin_hash", new_hash)

    # 5. Update rules.json
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["pin_hash"] = new_hash
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            print(f"[!] Warning: Could not update rules.json: {exc}")

    print("\n" + "=" * 50)
    print("✅ SUCCESS: Master PIN has been updated successfully!")
    print("=" * 50)
    print(f"New PIN Hash: {new_hash}")
    print("Use your new PIN to log in to the Parent Dashboard and authorize uninstallation.\n")


if __name__ == "__main__":
    main()
