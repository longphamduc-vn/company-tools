"""
Unit tests for SessionManager and session.json persistence.
Compatible with standard library unittest and pytest.
"""

import os
import time
import tempfile
import unittest
from pathlib import Path

from lgd_vault.session_manager import SessionManager


class TestSessionManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_session_save_and_load(self):
        session_file = str(self.tmp_path / "test_session.json")
        mgr = SessionManager(session_file=session_file, ttl_seconds=3600)

        test_cookies = {
            "PD-TH-SESSION-ID": "test_session_token_123",
            "PD-ID": "pd_user_456",
            "JSESSIONID": "node0123456789.node0",
        }

        # Save
        mgr.save_session(test_cookies)
        self.assertTrue(os.path.exists(session_file))

        # Load
        loaded = mgr.load_session()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["PD-TH-SESSION-ID"], "test_session_token_123")
        self.assertEqual(loaded["PD-ID"], "pd_user_456")
        self.assertEqual(loaded["JSESSIONID"], "node0123456789.node0")
        self.assertTrue(mgr.is_session_valid())

    def test_session_ttl_expiration(self):
        session_file = str(self.tmp_path / "test_expired_session.json")
        # TTL of 1 second
        mgr = SessionManager(session_file=session_file, ttl_seconds=1)

        test_cookies = {"PD-TH-SESSION-ID": "token"}
        mgr.save_session(test_cookies)

        # Sleep slightly past TTL
        time.sleep(1.2)

        # Session should now be expired
        self.assertIsNone(mgr.load_session())
        self.assertFalse(mgr.is_session_valid())

    def test_session_clear(self):
        session_file = str(self.tmp_path / "test_clear.json")
        mgr = SessionManager(session_file=session_file)

        mgr.save_session({"PD-ID": "123"})
        self.assertTrue(os.path.exists(session_file))

        mgr.clear_session()
        self.assertFalse(os.path.exists(session_file))
        self.assertIsNone(mgr.load_session())


if __name__ == "__main__":
    unittest.main()
