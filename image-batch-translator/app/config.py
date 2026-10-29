#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Configuration, Constants, Theme Styles & Dependency Management.
Preserves the exact original English UI styles and themes of image_batch_translator.py.
"""

import os
import sys
import platform
import tkinter as tk
from tkinter import ttk

# ============================================================================
# DEPENDENCY CHECKS
# ============================================================================
MISSING_PACKAGES = []

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageOps, ImageFilter
except ImportError:
    MISSING_PACKAGES.append("pillow")

HAVE_CV2 = False
try:
    import cv2
    HAVE_CV2 = True
except ImportError:
    pass

HAVE_LENS = False
try:
    from chrome_lens_py import LensAPI
    HAVE_LENS = True
except ImportError:
    MISSING_PACKAGES.append("chrome-lens-py")

HAVE_RAPIDOCR = False
try:
    from rapidocr_onnxruntime import RapidOCR
    HAVE_RAPIDOCR = True
except ImportError:
    pass

try:
    from deep_translator import GoogleTranslator
except ImportError:
    pass


# ============================================================================
# CONSTANTS & DEFAULTS
# ============================================================================
APP_TITLE = "Smart Batch Character Extractor & Renamer"
APP_VERSION = "2.1.0"

SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif")
DEFAULT_NAME_TEMPLATE = "{o1}_{o2}"

PREPROCESS_MODES = [
    "None (Ảnh gốc)",
    "CLAHE (Độ tương phản cao - Chống lóa / Mặt kính)",
    "Enhance (Tự động cân bằng & Sắc nét)",
    "Invert (Đảo màu - Kính tối / Khắc laser sáng)",
    "Binarize (Otsu - Nhị phân đen trắng lọc nhiễu)",
    "Sharpen (Làm sắc nét chữ mờ)",
]


# ============================================================================
# FONTS & THEME STYLING (RESTORED 100% ORIGINAL DESIGN & PALETTE)
# ============================================================================
def find_default_font() -> str:
    """Find a system font that reliably renders Unicode & Vietnamese diacritics."""
    current_os = platform.system()
    candidates = []

    if current_os == "Windows":
        win_dir = os.environ.get("WINDIR", r"C:\Windows")
        candidates = [
            os.path.join(win_dir, "Fonts", "arial.ttf"),
            os.path.join(win_dir, "Fonts", "segoeui.ttf"),
            os.path.join(win_dir, "Fonts", "calibri.ttf"),
            os.path.join(win_dir, "Fonts", "tahoma.ttf"),
        ]
    elif current_os == "Darwin":  # macOS
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    else:  # Linux
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]

    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return ""


def init_theme_styles(style: ttk.Style):
    """
    Initializes the exact original clean, professional ttk styles
    from image_batch_translator.py.
    """
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(".", font=("Segoe UI", 9))
    style.configure("TLabel", font=("Segoe UI", 9))
    style.configure("TButton", font=("Segoe UI", 9), padding=5)
    style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), foreground="#1e293b")
    style.configure("Title.TLabel", font=("Segoe UI", 13, "bold"), foreground="#0f172a")

    # Original Primary Button (Blue #2563eb)
    style.configure(
        "Primary.TButton",
        font=("Segoe UI", 9, "bold"),
        background="#2563eb",
        foreground="#ffffff",
    )
    style.map("Primary.TButton", background=[("active", "#1d4ed8")])

    # Original Accent Button (Green #059669)
    style.configure(
        "Accent.TButton",
        font=("Segoe UI", 9, "bold"),
        background="#059669",
        foreground="#ffffff",
    )
    style.map("Accent.TButton", background=[("active", "#047857")])

    # Original Review Button (Amber #d97706)
    style.configure(
        "Review.TButton",
        font=("Segoe UI", 9, "bold"),
        background="#d97706",
        foreground="#ffffff",
    )
    style.map("Review.TButton", background=[("active", "#b45309")])
