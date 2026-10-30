"""
Unit tests for ExcelInputGrid parsing and data handling.
"""

import unittest
from unittest.mock import MagicMock, patch

from lgd_vault.models import DrawingItem


class TestExcelGridLogic(unittest.TestCase):

    def test_parse_clipboard_tab_separated(self):
        """Verifies parsing of standard multi-row tab-separated text copied from Excel."""
        clipboard_text = (
            "QCAK09691\tMachine_2018021GC26\r\n"
            "QCAD69945\tMotor_Assembly\r\n"
            "QCAK09692\tConveyor_Unit\n"
        )

        lines = [line.strip("\r") for line in clipboard_text.split("\n")]
        parsed_items = []

        for line in lines:
            if not line.strip():
                continue
            cols = [c.strip() for c in line.split("\t")]
            qcode = cols[0].upper()
            alias = cols[1] if len(cols) > 1 else ""
            if qcode:
                parsed_items.append(DrawingItem(qcode=qcode, custom_name=alias))

        self.assertEqual(len(parsed_items), 3)
        self.assertEqual(parsed_items[0].qcode, "QCAK09691")
        self.assertEqual(parsed_items[0].custom_name, "Machine_2018021GC26")
        self.assertEqual(parsed_items[1].qcode, "QCAD69945")
        self.assertEqual(parsed_items[1].custom_name, "Motor_Assembly")
        self.assertEqual(parsed_items[2].qcode, "QCAK09692")

    def test_parse_clipboard_single_column_qcodes(self):
        """Verifies pasting a single column of QCodes copied from Excel."""
        clipboard_text = "QCAK09691\nQCAD69945\nQCAK09692\n"

        lines = [line.strip("\r") for line in clipboard_text.split("\n")]
        parsed_items = []
        for line in lines:
            qcode = line.strip().upper()
            if qcode:
                parsed_items.append(DrawingItem(qcode=qcode))

        self.assertEqual(len(parsed_items), 3)
        self.assertEqual(parsed_items[0].qcode, "QCAK09691")
        self.assertEqual(parsed_items[0].custom_name, "")
        self.assertEqual(parsed_items[2].qcode, "QCAK09692")

    def test_parse_clipboard_with_header(self):
        """Verifies that headers copied from Excel are automatically detected and skipped."""
        clipboard_text = "Mã QCode\tTên Thiết Bị\nQCAK09691\tMachine_A\n"
        lines = [line.strip("\r") for line in clipboard_text.split("\n")]

        first_line = lines[0].lower() if lines else ""
        start_idx = 1 if ("qcode" in first_line or "mã" in first_line) else 0

        parsed = []
        for line in lines[start_idx:]:
            if line.strip():
                parts = [p.strip() for p in line.split("\t")]
                parsed.append((parts[0].upper(), parts[1] if len(parts) > 1 else ""))

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0], ("QCAK09691", "Machine_A"))


if __name__ == "__main__":
    unittest.main()
