"""Unit tests for disk_analyzer.diagnostics."""

import os
import tempfile
import unittest
from unittest.mock import patch

from disk_analyzer.diagnostics import WindowsDiagnostics
from disk_analyzer.models import DriveInfo, DriveStatus, SafetyLevel, VssStorageInfo


class TestWindowsDiagnostics(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

        self.sys_drive = self.root
        self.win_dir = os.path.join(self.root, "Windows")
        self.user_prof = os.path.join(self.root, "Users", "tester")
        self.local_app = os.path.join(self.user_prof, "AppData", "Local")
        self.roaming_app = os.path.join(self.user_prof, "AppData", "Roaming")
        self.prog_data = os.path.join(self.root, "ProgramData")
        self.temp_dir = os.path.join(self.local_app, "Temp")

        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(os.path.join(self.win_dir, "Temp"), exist_ok=True)
        os.makedirs(os.path.join(self.local_app, "Google", "Chrome", "User Data", "Default", "Cache"), exist_ok=True)
        os.makedirs(os.path.join(self.user_prof, "Downloads"), exist_ok=True)

        with open(os.path.join(self.temp_dir, "junk1.tmp"), "wb") as f:
            f.write(b"x" * 4096)
        with open(os.path.join(self.local_app, "Google", "Chrome", "User Data", "Default", "Cache", "c_001"), "wb") as f:
            f.write(b"y" * 2048)
        with open(os.path.join(self.user_prof, "Downloads", "setup.exe"), "wb") as f:
            f.write(b"z" * 8192)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_audit_detects_items_and_computes_health_score(self) -> None:
        fake_drives = [
            DriveInfo(
                letter="C:",
                root_path="C:\\",
                label="OS",
                drive_type="Local Disk",
                filesystem="NTFS",
                total_bytes=100 * 1024 ** 3,
                used_bytes=94 * 1024 ** 3,
                free_bytes=6 * 1024 ** 3,
                used_percent=94.0,
                free_percent=6.0,
                status=DriveStatus.CRITICAL,
                recycle_bin_bytes=1024 ** 3,
                recycle_bin_items=12,
                is_system_drive=True,
                is_ready=True,
            )
        ]

        env = {
            "SystemDrive": self.sys_drive,
            "SystemRoot": self.win_dir,
            "windir": self.win_dir,
            "USERPROFILE": self.user_prof,
            "LOCALAPPDATA": self.local_app,
            "APPDATA": self.roaming_app,
            "ProgramData": self.prog_data,
            "TEMP": self.temp_dir,
            "TMP": self.temp_dir,
        }

        with (
            patch("disk_analyzer.diagnostics.get_logical_drives", return_value=fake_drives),
            patch("disk_analyzer.diagnostics.query_vss_shadow_storage", return_value=VssStorageInfo(available=False, requires_admin=True)),
        ):
            diag = WindowsDiagnostics(env_override=env)
            summary = diag.run_audit()

        self.assertLess(summary.health_score, 70)
        self.assertTrue(any("CRITICAL" in r for r in summary.recommendations))

        by_id = {i.item_id: i for i in summary.items}
        self.assertEqual(by_id["user_temp"].total_bytes, 4096)
        self.assertEqual(by_id["user_temp"].safety, SafetyLevel.SAFE)
        self.assertTrue(by_id["user_temp"].can_auto_clean)

        self.assertEqual(by_id["browser_caches"].total_bytes, 2048)
        self.assertEqual(by_id["downloads_folder"].total_bytes, 8192)
        self.assertFalse(by_id["downloads_folder"].can_auto_clean)

        self.assertEqual(by_id["recycle_bin"].total_bytes, 1024 ** 3)


if __name__ == "__main__":
    unittest.main()
