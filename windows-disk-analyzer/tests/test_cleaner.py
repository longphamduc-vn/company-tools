"""Unit tests for disk_analyzer.cleaner."""

import os
import tempfile
import unittest

from disk_analyzer.cleaner import SafeCleaner, is_protected_path
from disk_analyzer.models import DiagnosticItem, SafetyLevel


class TestSafeCleaner(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cache_dir = os.path.join(self.tmp.name, "AppCache")
        os.makedirs(os.path.join(self.cache_dir, "nested"))
        self.file_a = os.path.join(self.cache_dir, "a.tmp")
        self.file_b = os.path.join(self.cache_dir, "nested", "b.tmp")
        with open(self.file_a, "wb") as f:
            f.write(b"1" * 1500)
        with open(self.file_b, "wb") as f:
            f.write(b"2" * 2500)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_protected_paths_are_blocked(self) -> None:
        for path in [
            "C:\\",
            "C:\\Windows",
            "C:\\Windows\\System32",
            "C:\\Windows\\WinSxS",
            "C:\\Program Files",
            "C:\\Users",
            "C:\\Users\\admin",
            "C:\\Users\\admin\\AppData",
        ]:
            self.assertTrue(is_protected_path(path), f"Should protect {path}")

        self.assertFalse(is_protected_path(self.cache_dir))

    def test_dry_run_preserves_files(self) -> None:
        item = DiagnosticItem(
            item_id="test_cache",
            name="Test Cache",
            category="Temp",
            description="Test",
            paths=[self.cache_dir],
            exists=True,
            total_bytes=4000,
            size_on_disk_bytes=4000,
            file_count=2,
            safety=SafetyLevel.SAFE,
            can_auto_clean=True,
            clean_mode="contents",
        )
        cleaner = SafeCleaner()
        summary = cleaner.clean_diagnostic_items([item], dry_run=True, use_recycle_bin=False)

        self.assertTrue(summary.dry_run)
        self.assertEqual(summary.total_freed_bytes, 4000)
        self.assertEqual(summary.total_deleted_files, 2)
        self.assertTrue(os.path.exists(self.file_a))
        self.assertTrue(os.path.exists(self.file_b))

    def test_execute_clean_deletes_contents_but_keeps_root_cache_dir(self) -> None:
        item = DiagnosticItem(
            item_id="test_cache",
            name="Test Cache",
            category="Temp",
            description="Test",
            paths=[self.cache_dir],
            exists=True,
            total_bytes=4000,
            size_on_disk_bytes=4000,
            file_count=2,
            safety=SafetyLevel.SAFE,
            can_auto_clean=True,
            clean_mode="contents",
        )
        cleaner = SafeCleaner()
        summary = cleaner.clean_diagnostic_items([item], dry_run=False, use_recycle_bin=False)

        self.assertFalse(summary.dry_run)
        self.assertEqual(summary.total_freed_bytes, 4000)
        self.assertEqual(summary.total_deleted_files, 2)
        self.assertFalse(os.path.exists(self.file_a))
        self.assertFalse(os.path.exists(self.file_b))
        self.assertTrue(os.path.isdir(self.cache_dir))

    def test_delete_selected_files_dry_run_and_execute(self) -> None:
        cleaner = SafeCleaner()
        dry = cleaner.delete_selected_files([self.file_a], dry_run=True, use_recycle_bin=False)
        self.assertEqual(dry.total_freed_bytes, 1500)
        self.assertTrue(os.path.exists(self.file_a))

        real = cleaner.delete_selected_files([self.file_a], dry_run=False, use_recycle_bin=False)
        self.assertEqual(real.total_freed_bytes, 1500)
        self.assertFalse(os.path.exists(self.file_a))
        self.assertTrue(os.path.exists(self.file_b))


if __name__ == "__main__":
    unittest.main()
