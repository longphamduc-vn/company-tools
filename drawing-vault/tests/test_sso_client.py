"""
Unit tests for SSOClient (WebSocket & Token Exchange).
Compatible with standard library unittest and pytest.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from drawing_vault.sso_client import SSOClient
from drawing_vault.exceptions import SSOConnectionRefusedError
from drawing_vault.session_manager import SessionManager


class TestSSOClient(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sso_connection_refused(self):
        session_file = str(self.tmp_path / "session.json")
        mgr = SessionManager(session_file=session_file)
        client = SSOClient(session_manager=mgr, ws_host="127.0.0.1", ws_port=28083)

        # Mock socket to raise ConnectionRefusedError
        with patch("socket.socket.connect", side_effect=ConnectionRefusedError("Connection refused")):
            with self.assertRaises(SSOConnectionRefusedError) as ctx:
                client.authenticate()

            self.assertEqual(ctx.exception.code, "WS_CONN_REFUSED")
            self.assertIn("28083", str(ctx.exception))

    def test_sso_full_flow_success(self):
        session_file = str(self.tmp_path / "session.json")
        mgr = SessionManager(session_file=session_file)
        client = SSOClient(session_manager=mgr)

        # Mock WebSocket response
        mock_ws_resp = "API?args=tsso://im.internal.net:8088/pdadmin/eai/eai.jsp?token=MOCK_TOKEN_XYZ"

        # Mock requests.Session for eai.jsp
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {
            "Set-Cookie": "PD-TH-SESSION-ID=tok123; Path=/, PD-ID=usr456; Path=/, JSESSIONID=jsess789; Path=/"
        }

        with patch.object(client, "_request_token_via_websocket", return_value=mock_ws_resp):
            with patch("requests.Session.get", return_value=mock_resp):
                cookies = client.authenticate()

                self.assertIn("PD-TH-SESSION-ID", cookies)
                self.assertIn("PD-ID", cookies)
                self.assertIn("JSESSIONID", cookies)
                self.assertTrue(mgr.is_session_valid())


if __name__ == "__main__":
    unittest.main()
