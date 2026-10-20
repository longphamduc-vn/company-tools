# -*- coding: utf-8 -*-
import unittest
import os
from scada_tracelog.core.validator import StructureValidator
from scada_tracelog.core.exceptions import Excel256ColumnLimitError

class TestStructureValidator(unittest.TestCase):
    def setUp(self):
        self.valid_sample = os.path.join("samples", "sample_valid.xlsx")
        self.truncated_sample = os.path.join("samples", "sample_256_truncated.xlsx")

    def test_valid_file_structure(self):
        meta_cols, total_cols = StructureValidator.validate(self.valid_sample)
        self.assertEqual(meta_cols, 2)
        self.assertEqual(total_cols, 29)
        self.assertEqual((total_cols - meta_cols) % 3, 0)

    def test_256_truncated_file_detection(self):
        with self.assertRaises(Excel256ColumnLimitError) as ctx:
            StructureValidator.validate(self.truncated_sample)
        
        err_msg = str(ctx.exception)
        self.assertIn("DATA LOSS WARNING", err_msg)
        self.assertIn("Excel 256-column limit", err_msg)
        self.assertIn("29TF01_ZR9999[Cutoff_Parameter_Test]", err_msg)

if __name__ == "__main__":
    unittest.main()
