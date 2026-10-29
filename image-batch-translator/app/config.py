#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Configuration, Constants, Theme Styles & Dependency Management.
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
    import numpy as np
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
    import numpy as np
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
# FONTS & THEME STYLING
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
    """Initializes modern, clean ttk styles with distinct accents."""
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Colors
    bg_color = "#f8fafc"
    card_bg = "#ffffff"
    text_color = "#0f172a"
    primary_color = "#0284c7"
    primary_hover = "#0369a1"
    accent_color = "#10b981"
    accent_hover = "#059669"
    danger_color = "#ef4444"
    border_color = "#cbd5e1"

    style.configure(".", background=bg_color, foreground=text_color, font=("Segoe UI", 9))
    style.configure("Card.TFrame", background=card_bg, relief="solid", borderwidth=1)
    style.configure("TLabelframe", background=card_bg, relief="solid", borderwidth=1)
    style.configure(
        "TLabelframe.Label",
        background=card_bg,
        foreground="#1e293b",
        font=("Segoe UI", 9, "bold"),
    )

    # Primary Button (Sky Blue)
    style.configure(
        "Primary.TButton",
        background=primary_color,
        foreground="#ffffff",
        font=("Segoe UI", 9, "bold"),
        padding=6,
        borderwidth=0,
    )
    style.map(
        "Primary.TButton",
        background=[("active", primary_hover), ("disabled", "#94a3b8")],
        foreground=[("disabled", "#cbd5e1")],
    )

    # Accent Button (Emerald Green)
    style.configure(
        "Accent.TButton",
        background=accent_color,
        foreground="#ffffff",
        font=("Segoe UI", 9, "bold"),
        padding=6,
        borderwidth=0,
    )
    style.map(
        "Accent.TButton",
        background=[("active", accent_hover), ("disabled", "#94a3b8")],
        foreground=[("disabled", "#cbd5e1")],
    )

    # Focus Button (Indigo / Violet)
    style.configure(
        "Focus.TButton",
        background="#6366f1",
        foreground="#ffffff",
        font=("Segoe UI", 9, "bold"),
        padding=6,
        borderwidth=0,
    )
    style.map(
        "Focus.TButton",
        background=[("active", "#4f46e5"), ("disabled", "#94a3b8")],
        foreground=[("disabled", "#cbd5e1")],
    )

    # Danger Button (Rose Red)
    style.configure(
        "Danger.TButton",
        background=danger_color,
        foreground="#ffffff",
        font=("Segoe UI", 9, "bold"),
        padding=6,
        borderwidth=0,
    )
    style.map(
        "Danger.TButton",
        background=[("active", "#dc2626"), ("disabled", "#94a3b8")],
        foreground=[("disabled", "#cbd5e1")],
    )

    # Treeview Styling
    style.configure(
        "Treeview",
        background="#ffffff",
        foreground="#1e293b",
        fieldbackground="#ffffff",
        rowheight=26,
        font=("Segoe UI", 9),
        borderwidth=1,
    )
    style.configure(
        "Treeview.Heading",
        background="#e2e8f0",
        foreground="#0f172a",
        font=("Segoe UI", 9, "bold"),
        padding=4,
    )
    style.map(
        "Treeview",
        background=[("selected", "#0284c7")],
        foreground=[("selected", "#ffffff")],
    )
