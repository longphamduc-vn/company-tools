"""Unit tests for disk_analyzer.exporter."""

import json
import os
import tempfile
import unittest

from disk_analyzer.exporter import export_csv, export_html, export_json, export_markdown
from disk_analyzer.models import (
    DiagnosticItem,
    DiagnosticSummary,
    DriveInfo,
    DriveStatus,
    FileEntry,
    FolderNode,
    SafetyLevel,
    ScanResult,
)


class TestExporter(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.diag = DiagnosticSummary(
            generated_at="2026-11-26 08:25:00",
            computer_name="PC-TEST-01",
            os_version="Windows 11",
            is_admin=False,
            health_score=75,
            reclaimable_safe_bytes=2 * 1024 ** 3,
            drives=[
                DriveInfo(
                    letter="C:",
                    root_path="C:\\",
                    label="System",
                    total_bytes=256 * 1024 ** 3,
                    used_bytes=220 * 1024 ** 3,
                    free_bytes=36 * 1024 ** 3,
                    used_percent=85.9,
                    free_percent=14.1,
                    status=DriveStatus.WARNING,
                )
            ],
            items=[
                DiagnosticItem(
                    item_id="user_temp",
                    name="User Temporary Files",
                    category="Temp & Caches",
                    description="Temp files",
                    paths=["C:\\Temp"],
                    exists=True,
                    total_bytes=2 * 1024 ** 3,
                    size_on_disk_bytes=2 * 1024 ** 3,
                    file_count=500,
                    safety=SafetyLevel.SAFE,
                    can_auto_clean=True,
                    recommended_action="Safe to delete",
                )
            ],
            recommendations=["Clean Temp to reclaim 2 GB."],
        )
        root_node = FolderNode(
            path="C:\\Users",
            name="Users",
            logical_bytes=50 * 1024 ** 3,
            disk_bytes=50 * 1024 ** 3,
            file_count=1200,
            children=[
                FolderNode(
                    path="C:\\Users\\tester",
                    name="tester",
                    logical_bytes=45 * 1024 ** 3,
                    disk_bytes=45 * 1024 ** 3,
                    file_count=1100,
                )
            ],
        )
        self.scan = ScanResult(
            target_path="C:\\Users",
            started_at="2026-11-26 08:25:05",
            duration_sec=1.25,
            total_logical_bytes=50 * 1024 ** 3,
            total_disk_bytes=50 * 1024 ** 3,
            total_files=1200,
            total_dirs=40,
            root_node=root_node,
            top_files=[
                FileEntry(
                    path="C:\\Users\\tester\\disk.vhdx",
                    name="disk.vhdx",
                    extension=".vhdx",
                    parent_dir="C:\\Users\\tester",
                    logical_bytes=20 * 1024 ** 3,
                    disk_bytes=12 * 1024 ** 3,
                    modified_ts=1700000000.0,
                )
            ],
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_export_all_formats(self) -> None:
        j_path = export_json(os.path.join(self.tmp.name, "report.json"), self.diag, self.scan)
        with open(j_path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
        self.assertEqual(parsed["diagnostic"]["computer_name"], "PC-TEST-01")
        self.assertEqual(parsed["scan"]["total_files"], 1200)

        m_path = export_markdown(os.path.join(self.tmp.name, "report.md"), self.diag, self.scan)
        with open(m_path, "r", encoding="utf-8") as f:
            md_txt = f.read()
        self.assertIn("PC-TEST-01", md_txt)
        self.assertIn("disk.vhdx", md_txt)

        c_path = export_csv(os.path.join(self.tmp.name, "report.csv"), self.diag, self.scan)
        with open(c_path, "r", encoding="utf-8-sig") as f:
            csv_txt = f.read()
        self.assertIn("User Temporary Files", csv_txt)
        self.assertIn("disk.vhdx", csv_txt)

        h_path = export_html(os.path.join(self.tmp.name, "report.html"), self.diag, self.scan)
        with open(h_path, "r", encoding="utf-8") as f:
            html_txt = f.read()
        self.assertIn("<html", html_txt)
        self.assertIn("PC-TEST-01", html_txt)
        self.assertIn("disk.vhdx", html_txt)


if __name__ == "__main__":
    unittest.main()
