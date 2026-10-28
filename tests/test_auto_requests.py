"""
Tests for FOCUS Automated Request Policy Engine (Auto-Approve & Auto-Decline)
Verifies Phase 10 implementation:
1. Manual policy default
2. Auto-approve for websites, channels, and specific video IDs
3. Auto-decline policy
4. Focus Mode auto-decline override
5. Persistence across database and config layers
"""

import os
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_DIR = os.path.join(SCRIPT_DIR, "core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

from database import FocusDatabase
from config_manager import ConfigManager
from main import MainCoordinator


class TestAutoRequestPolicy(unittest.TestCase):
    def setUp(self):
        # Create an isolated temporary SQLite database for each test
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        self.db = FocusDatabase(db_path=self.temp_db_path)
        self.config = ConfigManager(database=self.db)
        self.coordinator = MainCoordinator(config_manager=self.config)

    def tearDown(self):
        try:
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
        except Exception:
            pass

    def test_default_policy_is_manual(self):
        """By default, requests should be queued as pending."""
        self.assertEqual(self.config.get("auto_request_policy"), "manual")
        self.assertFalse(self.config.get("auto_decline_during_focus"))

        res = self.coordinator.record_access_request({
            "type": "website",
            "target": "example.com",
            "title": "Example",
            "url": "https://example.com"
        })
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "pending")
        reqs = self.coordinator.get_access_requests()
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["status"], "pending")

    def test_auto_approve_website(self):
        """Auto-Approve policy should immediately whitelist website and approve request."""
        self.config.set("auto_request_policy", "approve")
        self.assertEqual(self.config.get("auto_request_policy"), "approve")

        res = self.coordinator.record_access_request({
            "type": "website",
            "target": "coursera.org",
            "title": "Coursera",
            "url": "https://coursera.org"
        })
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "approved")
        self.assertTrue(res.get("auto_resolved"))
        self.assertEqual(res.get("policy"), "auto_approve")

        # Verify website is in allowed_sites
        allowed_sites = self.config.get("allowed_sites")
        self.assertIn("coursera.org", allowed_sites)

        # Verify recorded in history as approved with resolved_by auto_approve
        reqs = self.coordinator.get_access_requests()
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["status"], "approved")
        self.assertEqual(reqs[0]["resolved_by"], "auto_approve")

    def test_auto_approve_youtube_video(self):
        """Auto-Approve for a video ID should whitelist only that specific video ID while channel stays restricted."""
        self.config.set("auto_request_policy", "approve")

        res = self.coordinator.record_access_request({
            "type": "video",
            "target": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "channel": "@RickAstleyYT"
        })
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "approved")
        self.assertTrue(res.get("auto_resolved"))

        # Verify specific video is in allowed_videos
        allowed_videos = self.config.get("allowed_videos")
        video_ids = [v["id"] for v in allowed_videos]
        self.assertIn("dQw4w9WgXcQ", video_ids)

        # Verify creator channel is NOT in allowed_channels (Option 2 strict single-video mode)
        allowed_channels = [c.lower() for c in self.config.get("allowed_channels")]
        self.assertNotIn("@rickastleyyt", allowed_channels)

    def test_auto_approve_channel(self):
        """Auto-Approve for a channel should add to allowed_channels."""
        self.config.set("auto_request_policy", "approve")

        res = self.coordinator.record_access_request({
            "type": "channel",
            "target": "@veritasium",
            "title": "Veritasium",
            "url": "https://www.youtube.com/@veritasium",
            "channel": "@veritasium"
        })
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "approved")
        allowed_channels = [c.lower() for c in self.config.get("allowed_channels")]
        self.assertIn("@veritasium", allowed_channels)

    def test_auto_decline_policy(self):
        """Auto-Decline policy should immediately mark request as rejected without modifying whitelists."""
        self.config.set("auto_request_policy", "decline")

        res = self.coordinator.record_access_request({
            "type": "website",
            "target": "distractinggames.com",
            "title": "Distracting Games",
            "url": "https://distractinggames.com"
        })
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "rejected")
        self.assertTrue(res.get("auto_resolved"))
        self.assertEqual(res.get("policy"), "auto_decline")

        # Verify site was NOT whitelisted
        allowed_sites = self.config.get("allowed_sites")
        self.assertNotIn("distractinggames.com", allowed_sites)

        # Verify recorded in history
        reqs = self.coordinator.get_access_requests()
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["status"], "rejected")
        self.assertEqual(reqs[0]["resolved_by"], "auto_decline")

    def test_focus_mode_auto_decline_override(self):
        """When Strict Focus Mode is active AND auto_decline_during_focus is True, requests must be auto-declined."""
        # Set global policy to approve
        self.config.set("auto_request_policy", "approve")
        self.config.set("auto_decline_during_focus", True)
        self.config.set("focus_mode", True)

        res = self.coordinator.record_access_request({
            "type": "website",
            "target": "somesite.org",
            "title": "Some Site",
            "url": "https://somesite.org"
        })
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "rejected")
        self.assertTrue(res.get("auto_resolved"))
        self.assertEqual(res.get("policy"), "auto_decline")

        # Now turn focus mode OFF; policy should resume to approve
        self.config.set("focus_mode", False)
        res2 = self.coordinator.record_access_request({
            "type": "website",
            "target": "learnpython.org",
            "title": "Learn Python",
            "url": "https://learnpython.org"
        })
        self.assertTrue(res2["success"])
        self.assertEqual(res2["status"], "approved")

    def test_handle_action_set_request_policy(self):
        """Parent dashboard action 'set_request_policy' should update config and status."""
        success = self.coordinator.handle_action("set_request_policy", {
            "policy": "approve",
            "auto_decline_during_focus": True
        })
        self.assertTrue(success)
        self.assertEqual(self.config.get("auto_request_policy"), "approve")
        self.assertTrue(self.config.get("auto_decline_during_focus"))

        status = self.coordinator.get_status()
        self.assertEqual(status["auto_request_policy"], "approve")
        self.assertTrue(status["auto_decline_during_focus"])


if __name__ == "__main__":
    unittest.main()
