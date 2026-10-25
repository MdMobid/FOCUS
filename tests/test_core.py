"""
Unit tests for FOCUS core subsystems.
Validates config manager, process enumeration, active window info, and token auth.
"""

import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "core"))

from config_manager import ConfigManager, hash_pin
from process_guard import get_running_processes, get_active_window_info
from web_server import generate_session_token


class TestFocusCore(unittest.TestCase):
    def test_pin_hashing_and_verification(self):
        cfg = ConfigManager()
        # Default PIN is 1234
        self.assertTrue(cfg.verify_pin("1234"))
        self.assertFalse(cfg.verify_pin("wrong_pin"))

    def test_process_enumeration(self):
        processes = get_running_processes()
        self.assertIsInstance(processes, list)
        self.assertGreater(len(processes), 0)
        # Verify tuple structure (pid, exe_name)
        pid, name = processes[0]
        self.assertIsInstance(pid, int)
        self.assertIsInstance(name, str)

    def test_active_window_detection(self):
        info = get_active_window_info()
        self.assertIn("app", info)
        self.assertIn("title", info)

    def test_session_token_generation(self):
        token1 = generate_session_token("1234")
        token2 = generate_session_token("1234")
        self.assertEqual(len(token1), 64)  # SHA-256 hex length
        self.assertNotEqual(token1, token2)  # High entropy unique sessions

    def test_firebase_bridge_url_building(self):
        from firebase_bridge import FirebaseCloudBridge
        bridge = FirebaseCloudBridge("https://test-db.firebaseio.com/", "test_secret_123", None)
        url = bridge._build_url("/focus/command.json")
        self.assertEqual(url, "https://test-db.firebaseio.com/focus/command.json?auth=test_secret_123")

    def test_database_crud(self):
        from database import FocusDatabase
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_db_path = tmp.name

        try:
            test_db = FocusDatabase(db_path=tmp_db_path)
            # Test Add Channel
            self.assertTrue(test_db.add_allowed_channel("@testchannel"))
            channels = test_db.get_allowed_channels()
            self.assertIn("@testchannel", channels)

            # Test Remove Channel
            self.assertTrue(test_db.remove_allowed_channel("@testchannel"))
            self.assertNotIn("@testchannel", test_db.get_allowed_channels())

            # Test Add Site
            self.assertTrue(test_db.add_allowed_site("testsite.org"))
            self.assertIn("testsite.org", test_db.get_allowed_sites())

            # Test Setting Key-Value
            test_db.set_setting("test_key", "hello_world")
            self.assertEqual(test_db.get_setting("test_key"), "hello_world")

            # Test Allowed Videos (Option 2)
            self.assertTrue(test_db.add_allowed_video("dQw4w9WgXcQ", "Never Gonna Give You Up", "@rickastley"))
            videos = test_db.get_allowed_videos()
            self.assertTrue(any(v["id"] == "dQw4w9WgXcQ" for v in videos))
            self.assertTrue(test_db.remove_allowed_video("dQw4w9WgXcQ"))
            self.assertFalse(any(v["id"] == "dQw4w9WgXcQ" for v in test_db.get_allowed_videos()))
        finally:
            if os.path.exists(tmp_db_path):
                os.remove(tmp_db_path)

    def test_youtube_video_id_extraction(self):
        from main import extract_youtube_video_id
        self.assertEqual(extract_youtube_video_id("https://www.youtube.com/watch?v=Rwf8eS3isWk"), "Rwf8eS3isWk")
        self.assertEqual(extract_youtube_video_id("https://youtu.be/Rwf8eS3isWk"), "Rwf8eS3isWk")
        self.assertEqual(extract_youtube_video_id("https://www.youtube.com/shorts/Rwf8eS3isWk"), "Rwf8eS3isWk")
        self.assertEqual(extract_youtube_video_id("Rwf8eS3isWk"), "Rwf8eS3isWk")


if __name__ == "__main__":
    unittest.main()
