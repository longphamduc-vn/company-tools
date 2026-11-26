"""Unit tests for disk_analyzer.scanner."""

import os
import tempfile
import threading
import unittest

from disk_analyzer.scanner import DiskScanner, quick_dir_usage


class TestDiskScanner(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

        os.makedirs(os.path.join(self.root, "sub_a", "deep"))
        os.makedirs(os.path.join(self.root, "sub_b"))

        with open(os.path.join(self.root, "root.log"), "wb") as f:
            f.write(b"a" * 1000)
        with open(os.path.join(self.root, "sub_a", "big.iso"), "wb") as f:
            f.write(b"b" * 8000)
        with open(os.path.join(self.root, "sub_a", "deep", "mid.zip"), "wb") as f:
            f.write(b"c" * 3000)
        with open(os.path.join(self.root, "sub_b", "small.txt"), "wb") as f:
            f.write(b"d" * 500)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_recursive_scan_sizes_and_ordering(self) -> None:
        scanner = DiskScanner(top_n_files=10, min_top_file_bytes=0, max_tree_depth=4)
        res = scanner.scan(self.root)

        self.assertFalse(res.cancelled)
        self.assertEqual(res.total_files, 4)
        self.assertEqual(res.total_logical_bytes, 12500)
        self.assertEqual(res.total_disk_bytes, 12500)
        self.assertIsNotNone(res.root_node)

        # sub_a (11000) should come before sub_b (500)
        children = res.root_node.children
        self.assertEqual(children[0].name, "sub_a")
        self.assertEqual(children[0].logical_bytes, 11000)
        self.assertEqual(children[1].name, "sub_b")
        self.assertEqual(children[1].logical_bytes, 500)

        # Top files descending
        self.assertEqual([f.name for f in res.top_files], ["big.iso", "mid.zip", "root.log", "small.txt"])

        # Extension breakdown
        ext_map = {e.extension: e for e in res.extension_stats}
        self.assertEqual(ext_map[".iso"].logical_bytes, 8000)
        self.assertEqual(ext_map[".zip"].logical_bytes, 3000)

    def test_scan_cancellation(self) -> None:
        cancel = threading.Event()
        cancel.set()
        scanner = DiskScanner(min_top_file_bytes=0)
        res = scanner.scan(self.root, cancel_event=cancel)
        self.assertTrue(res.cancelled)
        self.assertEqual(res.total_files, 0)

    def test_quick_dir_usage(self) -> None:
        l_sz, d_sz, f_cnt, err = quick_dir_usage(self.root)
        self.assertEqual(err, "")
        self.assertEqual(f_cnt, 4)
        self.assertEqual(l_sz, 12500)
        self.assertEqual(d_sz, 12500)

    def test_symlink_not_double_counted(self) -> None:
        link_path = os.path.join(self.root, "link_to_sub_a")
        target = os.path.join(self.root, "sub_a")
        try:
            os.symlink(target, link_path, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation requires developer mode or admin privilege on this Windows host.")

        scanner = DiskScanner(min_top_file_bytes=0)
        res = scanner.scan(self.root)
        self.assertEqual(res.total_files, 4)
        self.assertEqual(res.total_logical_bytes, 12500)
        self.assertGreaterEqual(res.skipped_reparse_dirs, 1)


if __name__ == "__main__":
    unittest.main()
