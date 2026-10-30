"""
Unit tests for DrawingService: Search, CAD Filter, Scraper, Downloader & Recovery.
Compatible with standard library unittest and pytest.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from drawing_vault.drawing_service import DrawingService
from drawing_vault.models import DrawingItem, DrawingRecord, DownloadResult, BatchDownloadSummary
from drawing_vault.exceptions import DrawingNotFoundError


class TestDrawingService(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_search_cad_filtering(self):
        """Verifies that Section 4.2.3 filter policy skips CAD items and keeps raster visual items."""
        service = DrawingService()
        service._session = MagicMock()

        # Search response with 1 CAD item and 1 Non-CAD JPG item
        mock_search_json = [
            {
                "drawingOid": "OID_CAD_001",
                "fabOid": "29113",
                "typeName": "CAD",
                "fileName": "model3d.prt",
            },
            {
                "drawingOid": "OID_NONCAD_002",
                "fabOid": "29113",
                "typeName": "Non-CAD",
                "fileName": "DWG99201.jpg",
            },
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = mock_search_json
        service._session.post.return_value = mock_resp

        records = service.search_drawings("QCAK09691")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].drawing_oid, "OID_NONCAD_002")
        self.assertEqual(records[0].type_name, "Non-CAD")

    def test_search_drawing_not_found(self):
        """Verifies that DrawingNotFoundError is raised if no records or only CAD records exist."""
        service = DrawingService()
        service._session = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = [{"drawingOid": "OID_1", "typeName": "CAD"}]
        service._session.post.return_value = mock_resp

        with self.assertRaises(DrawingNotFoundError):
            service.search_drawings("QC_NOT_FOUND")

    def test_scraper_regex_viewcontent(self):
        """Verifies Section 4.2.2 regex scraping for detailNonCAD.jsp."""
        service = DrawingService()
        service._session = MagicMock()

        html_content = """
        <html>
            <body>
                <div class="content">
                    <a href="http://fdm.internal.net:8008/Windchill/extcore/jsp/vault/drawing/viewContent/DWG99201.jpg?oid=12345">Download</a>
                </div>
            </body>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html_content
        service._session.get.return_value = mock_resp

        rec = DrawingRecord(qcode="QCAK09691", drawing_oid="12345")
        url = service.scrape_detail_page(rec)

        self.assertEqual(
            url,
            "http://fdm.internal.net:8008/Windchill/extcore/jsp/vault/drawing/viewContent/DWG99201.jpg?oid=12345",
        )

    def test_download_corrupt_payload_and_retry(self):
        """Verifies Section 7: CORRUPT_PAYLOAD (server returns HTML instead of binary stream) triggers recovery."""
        service = DrawingService()
        download_dir = str(self.tmp_path / "downloads")

        item = DrawingItem(qcode="QCAK09691", custom_name="Machine_2018021GC26")
        mock_rec = DrawingRecord(qcode="QCAK09691", drawing_oid="99201", type_name="Non-CAD")

        # 1st download attempt returns HTML login page
        corrupt_resp = MagicMock()
        corrupt_resp.status_code = 200
        corrupt_resp.headers = {"Content-Type": "text/html"}
        corrupt_resp.iter_content.return_value = [b"<!DOCTYPE html><html><body>Please Login</body></html>"]

        # 2nd attempt returns valid binary image
        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.headers = {
            "Content-Type": "image/jpeg",
            "Content-Disposition": 'attachment; filename="DWG99201.jpg"',
        }
        success_resp.iter_content.return_value = [b"\xFF\xD8\xFF\xE0MockJpegBytes"]

        with patch.object(service, "search_drawings", return_value=[mock_rec]):
            with patch.object(service, "scrape_detail_page", return_value="http://fdm.../viewContent/DWG99201.jpg"):
                with patch.object(service, "get_session") as mock_get_sess:
                    mock_sess = MagicMock()
                    mock_sess.get.side_effect = [corrupt_resp, success_resp]
                    mock_get_sess.return_value = mock_sess

                    result = service.process_item(item, download_dir=download_dir)

                    self.assertEqual(result.status, "Success")
                    self.assertIn("Machine_2018021GC26", result.file_name)
                    self.assertTrue(os.path.exists(result.local_path))

    def test_execute_batch(self):
        """Verifies batch execution returns BatchDownloadSummary with progress tracking."""
        service = DrawingService()
        download_dir = str(self.tmp_path / "batch_downloads")

        items = [
            DrawingItem(qcode="QCAK09691", custom_name="Unit_1"),
            DrawingItem(qcode="QCAD69945", custom_name="Unit_2"),
        ]

        mock_res1 = DownloadResult(qcode="QCAK09691", status="Success", file_name="Unit_1_DWG.jpg")
        mock_res2 = DownloadResult(qcode="QCAD69945", status="Failed: Drawing Not Found")

        with patch.object(service, "get_session"):
            with patch.object(service, "process_item", side_effect=[mock_res1, mock_res2]):
                progress_calls = []

                def on_progress(cur, total, res):
                    progress_calls.append((cur, total, res.qcode))

                summary = service.execute_batch(items, download_dir, progress_callback=on_progress)

                self.assertEqual(summary.total_requested, 2)
                self.assertEqual(summary.total_downloaded, 1)
                self.assertEqual(summary.total_failed, 1)
                self.assertEqual(len(progress_calls), 2)
                self.assertEqual(progress_calls[0], (1, 2, "QCAK09691"))
                self.assertEqual(progress_calls[1], (2, 2, "QCAD69945"))


if __name__ == "__main__":
    unittest.main()
