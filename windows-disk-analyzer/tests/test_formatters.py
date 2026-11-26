"""Unit tests for disk_analyzer.formatters."""

import unittest

from disk_analyzer.formatters import (
    format_bytes,
    format_duration,
    format_timestamp,
    make_percent_bar,
    truncate_middle,
)


class TestFormatters(unittest.TestCase):
    def test_format_bytes(self) -> None:
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(512), "512 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1024 ** 2 * 5), "5.00 MB")
        self.assertEqual(format_bytes(1024 ** 3 * 2.5), "2.50 GB")
        self.assertEqual(format_bytes(-2048), "-2.00 KB")

    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(0.25), "250 ms")
        self.assertEqual(format_duration(12.34), "12.3s")
        self.assertEqual(format_duration(125), "2m 5s")
        self.assertEqual(format_duration(3665), "1h 1m 5s")

    def test_format_timestamp(self) -> None:
        self.assertEqual(format_timestamp(None), "-")
        self.assertEqual(format_timestamp(0), "-")
        formatted = format_timestamp(1700000000)
        self.assertRegex(formatted, r"^\d{4}-\d{2}-\d{2}$")

    def test_make_percent_bar(self) -> None:
        bar = make_percent_bar(50.0, width=10)
        self.assertIn("50.0%", bar)
        self.assertIn("█████░░░░░", bar)

    def test_truncate_middle(self) -> None:
        short = "C:\\Temp\\file.txt"
        self.assertEqual(truncate_middle(short, 40), short)
        long_path = "C:\\Users\\administrator\\AppData\\Local\\Temp\\very_long_subfolder_name\\archive.zip"
        truncated = truncate_middle(long_path, 35)
        self.assertEqual(len(truncated), 35)
        self.assertIn("...", truncated)


if __name__ == "__main__":
    unittest.main()
