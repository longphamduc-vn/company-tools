"""
Unit tests for Logger Setup, Diagnostic Error Tracking, and CLI Diag commands.
"""

import os
import sys
import tempfile
import unittest
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from drawing_vault.logger_setup import (
    setup_diagnostics_logging,
    ui_log_handler,
    read_latest_log_tail,
    LOG_FILE_PATH,
)
from drawing_vault.models import DrawingItem, DownloadResult
from drawing_vault.drawing_service import DrawingService
from drawing_vault.exceptions import DrawingNotFoundError


class TestDiagnosticsLogging(unittest.TestCase):
    """Verifies that network errors, exceptions, and diagnostics are logged and captured."""

    def test_setup_diagnostics_logging_file_and_queue(self):
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as tmp:
            test_log_path = tmp.name

        try:
            logger = setup_diagnostics_logging(verbose=True, log_file=test_log_path)
            received_messages = []

            def on_log(msg, level):
                received_messages.append((msg, level))

            ui_log_handler.set_callback(on_log)

            test_err = "TEST_DIAGNOSTIC_FAILURE_CODE_500"
            logger.error("Simulated download error: %s", test_err)

            # Check that message was delivered to QueueLogHandler for the UI
            self.assertTrue(any(test_err in msg for msg, _ in received_messages))

            # Check that file handler wrote the error to disk
            with open(test_log_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn(test_err, content)
            self.assertIn("[ERROR]", content)

        finally:
            if os.path.exists(test_log_path):
                os.remove(test_log_path)

    def test_process_item_populates_error_detail(self):
        """Verifies that when a drawing download fails, error_detail is populated."""
        service = DrawingService()

        # Mock search_drawings to raise DrawingNotFoundError
        def mock_search_fail(qcode):
            raise DrawingNotFoundError(
                qcode,
                message=f"HTTP 404: Drawing not found for {qcode} on Vault server",
            )

        service.search_drawings = mock_search_fail

        item = DrawingItem(qcode="QC_ERR_TEST_999", custom_name="TestMotor")
        result = service.process_item(item, download_dir="/tmp/test_vault_dl")

        self.assertIn("Failed", result.status)
        self.assertIn("HTTP 404", result.error_detail)
        self.assertEqual(result.qcode, "QC_ERR_TEST_999")


if __name__ == "__main__":
    unittest.main()
