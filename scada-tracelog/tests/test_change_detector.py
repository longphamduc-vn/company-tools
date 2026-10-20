# -*- coding: utf-8 -*-
import unittest
import pandas as pd
from scada_tracelog.core.change_detector import ChangeDetector

class TestChangeDetector(unittest.TestCase):
    def setUp(self):
        self.sample_data = pd.DataFrame({
            "RECIPE ID": [4, 4, 4, 4, 5, 5],
            "TIME": [
                "2026/06/12 01:00:00",
                "2026/06/12 02:00:00",
                "2026/06/12 03:00:00",
                "2026/06/12 04:00:00",
                "2026/06/12 01:00:00",
                "2026/06/12 02:00:00"
            ],
            "PARAMETER NAME": ["Speed", "Speed", "Speed", "Speed", "Speed", "Speed"],
            "VALUE": [100.0, 100.0, 105.0, 105.0, 200.0, 200.0],
            "LOWER LIMIT": [90.0, 90.0, 90.0, 90.0, 180.0, 180.0],
            "UPPER LIMIT": [110.0, 110.0, 110.0, 110.0, 220.0, 220.0]
        })

    def test_strict_changes_only(self):
        res = ChangeDetector.detect_changes(self.sample_data, include_baseline=False)
        # Chi co 1 su kien thay doi: Recipe 4 tai 03:00:00 (100 -> 105)
        self.assertEqual(len(res), 1)
        self.assertEqual(res.iloc[0]["RECIPE ID"], 4)
        self.assertEqual(res.iloc[0]["TIME"], "2026/06/12 03:00:00")
        self.assertEqual(res.iloc[0]["VALUE"], 105.0)

    def test_include_baseline(self):
        res = ChangeDetector.detect_changes(self.sample_data, include_baseline=True)
        # Gom 3 su kien: Recipe 4 tai 01:00:00 (khoi dau), 03:00:00 (bien dong), Recipe 5 tai 01:00:00 (khoi dau)
        self.assertEqual(len(res), 3)

if __name__ == "__main__":
    unittest.main()
