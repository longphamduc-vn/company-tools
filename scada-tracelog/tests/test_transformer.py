# -*- coding: utf-8 -*-
import unittest
from scada_tracelog.core.transformer import DataTransformer

class TestDataTransformer(unittest.TestCase):
    def test_param_name_extraction(self):
        raw = "29TF01_ZR8450[OuterPeel_FILM_Peel_BLOW_TIME]"
        
        # Test description only
        desc = DataTransformer.extract_param_name(raw, mode="description")
        self.assertEqual(desc, "OuterPeel_FILM_Peel_BLOW_TIME")
        
        # Test original
        orig = DataTransformer.extract_param_name(raw, mode="original")
        self.assertEqual(orig, raw)
        
        # Test both
        both = DataTransformer.extract_param_name(raw, mode="both")
        self.assertEqual(both, "29TF01_ZR8450 - OuterPeel_FILM_Peel_BLOW_TIME")

    def test_no_brackets_fallback(self):
        raw = "SIMPLE_TAG_NAME"
        desc = DataTransformer.extract_param_name(raw, mode="description")
        self.assertEqual(desc, "SIMPLE_TAG_NAME")

if __name__ == "__main__":
    unittest.main()
