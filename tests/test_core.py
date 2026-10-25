"""
Unit tests for FOCUS core subsystems.
Validates config manager, process enumeration, active window info, and token auth.
"""

import os
import sys
import tempfile
import uuid
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

    def test_tab_limiting_and_clamping(self):
        from main import MainCoordinator
        from database import FocusDatabase
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_db = tmp.name
        try:
            db_inst = FocusDatabase(db_path=tmp_db)
            cfg_inst = ConfigManager(database=db_inst)
            coord = MainCoordinator(config_manager=cfg_inst)

            # 1. Set tab range with min_tabs = 3, max_tabs_range = 15
            coord.handle_action("set_tab_range", {"min_tabs": 3, "max_tabs_range": 15, "max_tabs": 3})
            self.assertEqual(cfg_inst.get("min_tabs"), 3)
            self.assertEqual(cfg_inst.get("max_tabs_range"), 15)
            self.assertEqual(cfg_inst.get("max_tabs"), 3)

            # 2. Set tabs to 5 (should be 5, within [3, 15])
            coord.handle_action("set_tabs", {"max_tabs": 5})
            self.assertEqual(cfg_inst.get("max_tabs"), 5)

            # 3. Set tabs to 1 (should clamp to min_tabs = 3)
            coord.handle_action("set_tabs", {"max_tabs": 1})
            self.assertEqual(cfg_inst.get("max_tabs"), 3)

            # 4. Set tabs to 20 (should clamp to max_tabs_range = 15)
            coord.handle_action("set_tabs", {"max_tabs": 20})
            self.assertEqual(cfg_inst.get("max_tabs"), 15)

            # 5. Enable Focus Mode with specific max_tabs: 4 (within [3, 15])
            coord.handle_action("focus", {"enabled": True, "duration_mins": 30, "max_tabs": 4})
            self.assertTrue(cfg_inst.get("focus_mode"))
            self.assertEqual(cfg_inst.get("max_tabs"), 4)

            # 6. Enable Focus Mode with max_tabs: 1 (should clamp to min_tabs = 3)
            coord.handle_action("focus", {"enabled": True, "duration_mins": 30, "max_tabs": 1})
            self.assertEqual(cfg_inst.get("max_tabs"), 3)
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

    def test_delete_access_request(self):
        from main import MainCoordinator
        from database import FocusDatabase
        tmp_db = os.path.join(tempfile.gettempdir(), f"focus_test_del_{uuid.uuid4().hex[:8]}.db")
        try:
            db_inst = FocusDatabase(db_path=tmp_db)
            cfg_inst = ConfigManager(database=db_inst)
            coord = MainCoordinator(config_manager=cfg_inst)

            sample_requests = [
                {"id": "req_1", "title": "History Item 1", "status": "approved"},
                {"id": "req_2", "title": "History Item 2", "status": "rejected"},
                {"id": "req_3", "title": "Pending Item", "status": "pending"},
            ]
            cfg_inst.set("access_requests", sample_requests)

            # Delete req_1 via handle_action
            result = coord.handle_action("delete_request", {"request_id": "req_1"})
            self.assertTrue(result)

            remaining = cfg_inst.get("access_requests", [])
            self.assertEqual(len(remaining), 2)
            self.assertEqual([r["id"] for r in remaining], ["req_2", "req_3"])

            # Delete req_2 directly
            del_res = coord.delete_access_request("req_2")
            self.assertTrue(del_res.get("success"))

            remaining_after = cfg_inst.get("access_requests", [])
            self.assertEqual(len(remaining_after), 1)
            self.assertEqual(remaining_after[0]["id"], "req_3")
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

    def test_power_command_stale_and_loop_prevention(self):
        from main import MainCoordinator
        from database import FocusDatabase
        from firebase_bridge import FirebaseCloudBridge
        import time

        tmp_db = os.path.join(tempfile.gettempdir(), f"focus_test_loop_{uuid.uuid4().hex[:8]}.db")
        try:
            db_inst = FocusDatabase(db_path=tmp_db)
            cfg_inst = ConfigManager(database=db_inst)
            coord = MainCoordinator(config_manager=cfg_inst)
            coord.start_time = time.time()

            bridge = FirebaseCloudBridge(db_url="https://mock.firebaseio.com", db_secret="test", coordinator=coord)
            pushed_data = []
            bridge.push_data = lambda path, data, method="PUT": pushed_data.append((path, data))

            # 1. Stale command from before service boot (e.g. from previous day/session)
            stale_cmd = {
                "action": "shutdown",
                "id": "cmd_stale_123",
                "timestamp": coord.start_time - 3600  # 1 hour ago
            }
            bridge._handle_cloud_event("put", stale_cmd)
            # Must NOT be in processed command ids or executed
            self.assertNotIn("cmd_stale_123", bridge._processed_command_ids)
            # Must have sent a clear command to Firebase
            self.assertTrue(any("/focus/command.json" in p[0] and p[1].get("action") == "cleared" for p in pushed_data))

            # 2. Persisted command ID deduplication across bridge restarts
            cfg_inst.set("processed_cmd_ids", ["cmd_prev_executed"])
            new_bridge = FirebaseCloudBridge(db_url="https://mock.firebaseio.com", db_secret="test", coordinator=coord)
            self.assertIn("cmd_prev_executed", new_bridge._processed_command_ids)

            # Replaying cmd_prev_executed must be dropped immediately
            pushed_data.clear()
            new_bridge._handle_cloud_event("put", {
                "action": "restart",
                "id": "cmd_prev_executed",
                "timestamp": time.time()
            })
            # No action or push should be initiated
            self.assertEqual(len(pushed_data), 0)
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)


if __name__ == "__main__":
    unittest.main()


