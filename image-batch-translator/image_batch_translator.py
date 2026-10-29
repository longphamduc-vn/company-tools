#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Batch Character Extractor & Renamer (Crop-Resilient)
==========================================================
Backward-compatible launcher forwarding to the modular `app` package.
"""

from app.config import (
    APP_TITLE,
    APP_VERSION,
    SUPPORTED_EXTENSIONS,
    DEFAULT_NAME_TEMPLATE,
    PREPROCESS_MODES,
    HAVE_LENS,
    HAVE_RAPIDOCR,
    HAVE_CV2,
)
from app.utils import (
    natural_sort_key,
    sanitize_filename,
    compute_filename,
    get_unique_output_path,
)
from app.ocr_engine import preprocess_for_ocr, run_rapidocr, run_lens_full_text
from app.extraction import (
    extract_by_keyword,
    extract_by_pattern,
    extract_by_box,
    find_bounding_box_for_rule,
    find_bounding_box_from_lens,
)
from app.excel_export import export_results_to_excel, HAVE_OPENPYXL
from app.session_manager import save_session, has_saved_session, load_session, clear_session
from app.ui.preprocess_dialog import PreprocessTestDialog
from app.ui.review_focus_dialog import ReviewFocusDialog
from app.ui.main_window import SmartBatchExtractorApp
from app.main import main

if __name__ == "__main__":
    main()
