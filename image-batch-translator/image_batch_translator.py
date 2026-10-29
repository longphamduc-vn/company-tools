#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image Batch Character Extractor & Smart Renamer
================================================
A cross-platform desktop application written in Python (Tkinter GUI).
Specialized in extracting text/characters from fixed regions across batches of images
(using Google Lens OCR or offline RapidOCR - NO Tesseract required).
Provides batch file renaming based on extracted text, data table inspection,
CSV export, and optional image inpainting.

Dependencies:
    - Pillow (PIL)
    - chrome-lens-py (Google Lens Cloud AI OCR)
    - rapidocr-onnxruntime (Local Offline OCR Engine)
    - deep-translator (Optional Translation Engine)
    - tkinter (built into standard Python)
"""

import sys
import os
import re
import csv
import json
import time
import shutil
import platform
import asyncio
import threading
import statistics
import unicodedata
from string import Formatter

# ============================================================================
# 1. DEPENDENCY CHECK & GRACEFUL ERROR HANDLING
# ============================================================================
MISSING_PACKAGES = []

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
except ImportError:
    MISSING_PACKAGES.append("pillow")

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
    pass  # Optional offline fallback

try:
    from deep_translator import GoogleTranslator
except ImportError:
    pass  # Optional if translation is toggled

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    print(
        "CRITICAL ERROR: Tkinter is not installed on this system.\n"
        "On Debian/Ubuntu: sudo apt-get install python3-tk\n"
        "On Fedora: sudo dnf install python3-tkinter\n"
        "On macOS/Windows: Reinstall Python with Tkinter enabled.",
        file=sys.stderr,
    )
    sys.exit(1)

if not HAVE_LENS and not HAVE_RAPIDOCR:
    missing_str = " ".join(MISSING_PACKAGES)
    error_msg = (
        f"Missing required Python libraries: {', '.join(MISSING_PACKAGES)}\n\n"
        f"Please install them by opening your terminal and running:\n\n"
        f"    pip install pillow chrome-lens-py rapidocr-onnxruntime deep-translator\n"
    )
    print(error_msg, file=sys.stderr)
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Missing Dependencies", error_msg)
    root.destroy()
    sys.exit(1)


# ============================================================================
# 2. CONSTANTS & SYSTEM CONFIGURATION
# ============================================================================
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif")

LANGUAGES = {
    "Auto Detect": "auto",
    "Vietnamese": "vi",
    "English": "en",
    "Chinese (Simplified)": "zh-CN",
    "Chinese (Traditional)": "zh-TW",
    "Japanese": "ja",
    "Korean": "ko",
    "Russian": "ru",
    "French": "fr",
    "German": "de",
    "Spanish": "es",
    "Thai": "th",
}

DEFAULT_NAME_TEMPLATE = "{o1}_{o2}"


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
            "/System/Library/Fonts/PingFang.ttc",
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


# ============================================================================
# 3. HELPER FUNCTIONS & IMAGE PROCESSING
# ============================================================================
def natural_sort_key(s: str):
    """Sort strings containing numbers naturally (e.g. img2 before img10)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def sanitize_filename(filename: str, max_length: int = 120) -> str:
    """Sanitize filename while preserving Unicode/Vietnamese diacritics."""
    filename = unicodedata.normalize("NFC", str(filename))
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", filename)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(". ")
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned:
        cleaned = "untitled"
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(". ")
    return cleaned


class SafeFormatDict(dict):
    """Dictionary that returns the unformatted placeholder if key is missing."""
    def __missing__(self, key):
        return f"{{{key}}}"


def compute_filename(template: str, index: int, orig_stem: str, ocr_texts: list, trans_texts: list) -> str:
    """Computes sanitized new filename from template and variables."""
    format_vars = {
        "index": index,
        "name": sanitize_filename(orig_stem, max_length=50),
    }
    for i, o_text in enumerate(ocr_texts):
        format_vars[f"o{i+1}"] = sanitize_filename(o_text, max_length=40)
    for i, t_text in enumerate(trans_texts):
        format_vars[f"t{i+1}"] = sanitize_filename(t_text, max_length=40)

    try:
        raw_formatted = Formatter().vformat(template, (), SafeFormatDict(format_vars))
    except Exception:
        raw_formatted = f"{orig_stem}_renamed"

    return sanitize_filename(raw_formatted)


def get_unique_output_path(output_dir: str, base_name: str, ext: str, used_names: set) -> str:
    """Ensure filename is unique in the output directory by appending _2, _3 etc."""
    clean_ext = ext.lstrip(".").lower()
    candidate = f"{base_name}.{clean_ext}"
    full_path = os.path.join(output_dir, candidate)
    counter = 2
    while candidate.lower() in used_names or os.path.exists(full_path):
        candidate = f"{base_name}_{counter}.{clean_ext}"
        full_path = os.path.join(output_dir, candidate)
        counter += 1
    used_names.add(candidate.lower())
    return full_path


def get_box_median_color(img: Image.Image, box: tuple) -> tuple:
    """Computes median RGB color of border pixels around box = (x1, y1, x2, y2)."""
    x1, y1, x2, y2 = box
    w, h = img.size
    x1 = max(0, min(x1, w - 1))
    x2 = max(x1 + 1, min(x2, w))
    y1 = max(0, min(y1, h - 1))
    y2 = max(y1 + 1, min(y2, h))

    border_pixels = []
    for x in range(x1, x2):
        border_pixels.append(img.getpixel((x, y1)))
        border_pixels.append(img.getpixel((x, y2 - 1)))
    for y in range(y1, y2):
        border_pixels.append(img.getpixel((x1, y)))
        border_pixels.append(img.getpixel((x2 - 1, y)))

    if not border_pixels:
        return (255, 255, 255)

    sample = border_pixels[0]
    if isinstance(sample, int):
        med = int(statistics.median(border_pixels))
        return (med, med, med)
    elif len(sample) >= 3:
        r_vals = [p[0] for p in border_pixels]
        g_vals = [p[1] for p in border_pixels]
        b_vals = [p[2] for p in border_pixels]
        return (
            int(statistics.median(r_vals)),
            int(statistics.median(g_vals)),
            int(statistics.median(b_vals)),
        )
    return (255, 255, 255)


def get_contrast_text_color(bg_color: tuple) -> tuple:
    """Returns black or white text color depending on background brightness."""
    r, g, b = bg_color[:3]
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return (0, 0, 0) if luminance > 128 else (255, 255, 255)


def fit_and_draw_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple,
    font_path: str = "",
    padding: int = 4,
    bg_color: tuple = None,
):
    """Renders text inside box with auto-wrapping and auto-scaling."""
    x1, y1, x2, y2 = box
    box_w = max(1, x2 - x1)
    box_h = max(1, y2 - y1)
    avail_w = max(1, box_w - 2 * padding)
    avail_h = max(1, box_h - 2 * padding)

    cleaned_text = text.strip()
    if not cleaned_text:
        return

    font_size = max(8, min(80, int(box_h * 0.75)))
    min_font_size = 8

    best_lines = []
    best_font = None
    best_line_h = 10
    best_total_h = 10

    def load_font(size):
        if font_path and os.path.isfile(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass
        fallback = find_default_font()
        if fallback and os.path.isfile(fallback):
            try:
                return ImageFont.truetype(fallback, size)
            except Exception:
                pass
        return ImageFont.load_default()

    while font_size >= min_font_size:
        font = load_font(font_size)
        line_height = int(font_size * 1.25)
        lines = []

        for paragraph in cleaned_text.splitlines():
            words = paragraph.split(" ")
            curr_line = ""
            for word in words:
                test_line = f"{curr_line} {word}".strip()
                bbox = draw.textbbox((0, 0), test_line, font=font)
                w = bbox[2] - bbox[0]
                if w <= avail_w:
                    curr_line = test_line
                else:
                    if curr_line:
                        lines.append(curr_line)
                        curr_line = word
                        wb = draw.textbbox((0, 0), word, font=font)
                        if (wb[2] - wb[0]) > avail_w:
                            chunk = ""
                            for char in word:
                                test_c = chunk + char
                                c_box = draw.textbbox((0, 0), test_c, font=font)
                                if (c_box[2] - c_box[0]) <= avail_w:
                                    chunk = test_c
                                else:
                                    if chunk:
                                        lines.append(chunk)
                                    chunk = char
                            curr_line = chunk
                    else:
                        chunk = ""
                        for char in word:
                            test_c = chunk + char
                            c_box = draw.textbbox((0, 0), test_c, font=font)
                            if (c_box[2] - c_box[0]) <= avail_w:
                                chunk = test_c
                            else:
                                if chunk:
                                    lines.append(chunk)
                                chunk = char
                        curr_line = chunk
            if curr_line:
                lines.append(curr_line)

        total_h = len(lines) * line_height
        all_lines_fit_w = True
        for l in lines:
            bb = draw.textbbox((0, 0), l, font=font)
            if (bb[2] - bb[0]) > avail_w:
                all_lines_fit_w = False
                break

        best_lines = lines
        best_font = font
        best_line_h = line_height
        best_total_h = total_h

        if all_lines_fit_w and total_h <= avail_h:
            break

        font_size -= 2

    if bg_color is None:
        target_img = getattr(draw, "_image", None)
        med_bg = get_box_median_color(target_img, box) if target_img else (255, 255, 255)
    else:
        med_bg = bg_color

    txt_color = get_contrast_text_color(med_bg)

    start_y = y1 + max(0, (box_h - best_total_h) // 2)
    for idx, line in enumerate(best_lines):
        bb = draw.textbbox((0, 0), line, font=best_font)
        lw = bb[2] - bb[0]
        line_x = x1 + max(0, (box_w - lw) // 2)
        line_y = start_y + idx * best_line_h
        draw.text((line_x, line_y), line, fill=txt_color, font=best_font)


# ============================================================================
# 4. MAIN APPLICATION CLASS
# ============================================================================
class BatchImageTranslatorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Image Batch Character Extractor & Smart Renamer")
        self.root.geometry("1280x830")
        self.root.minsize(1050, 700)

        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        self._init_theme_styles()

        # State Variables
        self.folder_path = ""
        self.image_files = []
        self.current_sample_idx = 0
        self.sample_image = None
        self.sample_photo = None
        self.sample_scale = 1.0
        self.sample_offset_x = 0
        self.sample_offset_y = 0

        self.regions = []
        self.selected_region_idx = -1

        self.drag_start_x = 0
        self.drag_start_y = 0
        self.active_rect_id = None

        self.translation_cache = {}
        self.results_data = []

        # Configurations
        self.ocr_engine_var = tk.StringVar(value="Google Lens (Cloud AI - High Accuracy)" if HAVE_LENS else "RapidOCR (Local Offline)")
        self.enable_translate_var = tk.BooleanVar(value=False)
        self.source_lang_var = tk.StringVar(value="Auto Detect")
        self.target_lang_var = tk.StringVar(value="Vietnamese")
        self.template_var = tk.StringVar(value=DEFAULT_NAME_TEMPLATE)
        self.export_mode_var = tk.StringVar(value="Copy & Rename Original (High Quality)")
        self.format_var = tk.StringVar(value="Keep original")
        self.output_folder_var = tk.StringVar(value="")
        self.font_path_var = tk.StringVar(value=find_default_font())

        # Reactive trace for live table updating
        self.template_var.trace_add("write", self._on_template_or_format_changed)
        self.format_var.trace_add("write", self._on_template_or_format_changed)

        self.is_processing = False
        self.stop_requested = False

        self._build_ui()
        self._update_status("Ready. Click 'Choose Folder' or 'Load Demo Images' to begin.")

    def _init_theme_styles(self):
        self.style.configure(".", font=("Segoe UI", 9))
        self.style.configure("TLabel", font=("Segoe UI", 9))
        self.style.configure("TButton", font=("Segoe UI", 9), padding=5)
        self.style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), foreground="#1e293b")
        self.style.configure("Title.TLabel", font=("Segoe UI", 13, "bold"), foreground="#0f172a")
        self.style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), background="#2563eb", foreground="#ffffff")
        self.style.map("Primary.TButton", background=[("active", "#1d4ed8")])
        self.style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"), background="#059669", foreground="#ffffff")
        self.style.map("Accent.TButton", background=[("active", "#047857")])

    def _build_ui(self):
        # Top Header Bar
        top_bar = ttk.Frame(self.root, padding="10 8")
        top_bar.pack(side=tk.TOP, fill=tk.X)

        title_lbl = ttk.Label(top_bar, text="Batch Character Extractor & Renamer", style="Title.TLabel")
        title_lbl.pack(side=tk.LEFT, padx=(0, 15))

        btn_open = ttk.Button(top_bar, text="📁 Choose Folder...", command=self.on_choose_folder)
        btn_open.pack(side=tk.LEFT, padx=3)

        btn_demo = ttk.Button(top_bar, text="✨ Load Demo Images", command=self.on_load_demo_images)
        btn_demo.pack(side=tk.LEFT, padx=3)

        btn_save_cfg = ttk.Button(top_bar, text="💾 Save Config", command=self.on_save_config)
        btn_save_cfg.pack(side=tk.LEFT, padx=3)

        btn_load_cfg = ttk.Button(top_bar, text="📂 Load Config", command=self.on_load_config)
        btn_load_cfg.pack(side=tk.LEFT, padx=3)

        self.folder_disp_lbl = ttk.Label(top_bar, text="No folder selected", foreground="#64748b")
        self.folder_disp_lbl.pack(side=tk.RIGHT, padx=5)

        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 5))

        # ====================================================================
        # LEFT PANE: Canvas, Regions, Coordinates
        # ====================================================================
        left_frame = ttk.Frame(paned, padding=5)
        paned.add(left_frame, weight=5)

        sample_bar = ttk.Frame(left_frame)
        sample_bar.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(sample_bar, text="Sample Image:", style="Header.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self.sample_combo = ttk.Combobox(sample_bar, state="readonly", width=32)
        self.sample_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.sample_combo.bind("<<ComboboxSelected>>", self.on_sample_combo_selected)

        ttk.Button(sample_bar, text="◀", width=3, command=self.on_prev_sample).pack(side=tk.LEFT, padx=2)
        ttk.Button(sample_bar, text="▶", width=3, command=self.on_next_sample).pack(side=tk.LEFT, padx=2)

        self.img_info_lbl = ttk.Label(sample_bar, text="", foreground="#64748b")
        self.img_info_lbl.pack(side=tk.RIGHT, padx=4)

        canvas_container = ttk.Frame(left_frame, borderwidth=1, relief="solid")
        canvas_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_container, bg="#1e293b", cursor="cross", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        reg_ctrl_frame = ttk.LabelFrame(left_frame, text="Extraction Regions (Drag mouse on image)", padding=6)
        reg_ctrl_frame.pack(fill=tk.X, pady=(6, 0))

        cols = ("id", "pixels", "ratios", "var")
        self.reg_tree = ttk.Treeview(reg_ctrl_frame, columns=cols, show="headings", height=4, selectmode="browse")
        self.reg_tree.heading("id", text="#")
        self.reg_tree.heading("pixels", text="Pixel Coords [X1, Y1, X2, Y2]")
        self.reg_tree.heading("ratios", text="Relative Ratios")
        self.reg_tree.heading("var", text="Template Var")
        self.reg_tree.column("id", width=35, anchor="center")
        self.reg_tree.column("pixels", width=190, anchor="w")
        self.reg_tree.column("ratios", width=160, anchor="w")
        self.reg_tree.column("var", width=90, anchor="center")

        reg_scroll = ttk.Scrollbar(reg_ctrl_frame, orient="vertical", command=self.reg_tree.yview)
        self.reg_tree.configure(yscrollcommand=reg_scroll.set)
        self.reg_tree.pack(side=tk.TOP, fill=tk.X, expand=True)
        self.reg_tree.bind("<<TreeviewSelect>>", self.on_region_selected)

        edit_bar = ttk.Frame(reg_ctrl_frame)
        edit_bar.pack(fill=tk.X, pady=(5, 0))

        ttk.Label(edit_bar, text="X1:").pack(side=tk.LEFT)
        self.ent_x1 = ttk.Entry(edit_bar, width=5)
        self.ent_x1.pack(side=tk.LEFT, padx=1)
        ttk.Label(edit_bar, text="Y1:").pack(side=tk.LEFT)
        self.ent_y1 = ttk.Entry(edit_bar, width=5)
        self.ent_y1.pack(side=tk.LEFT, padx=1)
        ttk.Label(edit_bar, text="X2:").pack(side=tk.LEFT)
        self.ent_x2 = ttk.Entry(edit_bar, width=5)
        self.ent_x2.pack(side=tk.LEFT, padx=1)
        ttk.Label(edit_bar, text="Y2:").pack(side=tk.LEFT)
        self.ent_y2 = ttk.Entry(edit_bar, width=5)
        self.ent_y2.pack(side=tk.LEFT, padx=1)

        ttk.Button(edit_bar, text="Apply Coords", command=self.on_update_region_coords).pack(side=tk.LEFT, padx=3)
        ttk.Button(edit_bar, text="❌ Delete", command=self.on_delete_region).pack(side=tk.LEFT, padx=2)
        ttk.Button(edit_bar, text="🗑️ Clear All", command=self.on_clear_regions).pack(side=tk.LEFT, padx=2)

        # ====================================================================
        # RIGHT PANE: Settings, Actions, Results
        # ====================================================================
        right_frame = ttk.Frame(paned, padding=5)
        paned.add(right_frame, weight=6)

        settings_box = ttk.LabelFrame(right_frame, text="Extraction & Renaming Configuration", padding=8)
        settings_box.pack(fill=tk.X, pady=(0, 6))

        # Row 1: OCR Engine & Translation Toggle
        r1 = ttk.Frame(settings_box)
        r1.pack(fill=tk.X, pady=2)

        ttk.Label(r1, text="OCR Engine:").pack(side=tk.LEFT)
        engine_options = []
        if HAVE_LENS:
            engine_options.append("Google Lens (Cloud AI - High Accuracy)")
        if HAVE_RAPIDOCR:
            engine_options.append("RapidOCR (Local Offline)")
        if not engine_options:
            engine_options.append("No OCR Engine Available")

        self.combo_engine = ttk.Combobox(
            r1, textvariable=self.ocr_engine_var, values=engine_options, state="readonly", width=34
        )
        self.combo_engine.pack(side=tk.LEFT, padx=(3, 15))

        self.chk_trans = ttk.Checkbutton(
            r1,
            text="Also Translate Text (Optional)",
            variable=self.enable_translate_var,
            command=self._on_toggle_translate,
        )
        self.chk_trans.pack(side=tk.LEFT, padx=5)

        # Row 1b: Language options (shown if translation enabled)
        self.trans_frame = ttk.Frame(settings_box)
        ttk.Label(self.trans_frame, text="Source:").pack(side=tk.LEFT)
        ttk.Combobox(self.trans_frame, textvariable=self.source_lang_var, values=list(LANGUAGES.keys()), state="readonly", width=14).pack(side=tk.LEFT, padx=3)
        ttk.Label(self.trans_frame, text="Target:").pack(side=tk.LEFT, padx=(10, 0))
        target_keys = [k for k in LANGUAGES.keys() if k != "Auto Detect"]
        ttk.Combobox(self.trans_frame, textvariable=self.target_lang_var, values=target_keys, state="readonly", width=14).pack(side=tk.LEFT, padx=3)

        # Row 2: Name Template & Quick Insert Pills
        r2 = ttk.Frame(settings_box)
        r2.pack(fill=tk.X, pady=4)

        ttk.Label(r2, text="Rename Template:").pack(side=tk.LEFT)
        ttk.Entry(r2, textvariable=self.template_var, width=24).pack(side=tk.LEFT, padx=4)

        ttk.Label(r2, text="Insert:", foreground="#64748b").pack(side=tk.LEFT, padx=(5, 2))
        for var_tag in ["{o1}", "{o2}", "{o3}", "{name}", "{index:03d}"]:
            ttk.Button(
                r2, text=var_tag, width=len(var_tag) + 1, command=lambda v=var_tag: self._insert_template_tag(v)
            ).pack(side=tk.LEFT, padx=1)

        # Row 3: Export Mode & Output Folder
        r3 = ttk.Frame(settings_box)
        r3.pack(fill=tk.X, pady=2)

        ttk.Label(r3, text="Export Mode:").pack(side=tk.LEFT)
        combo_exp_mode = ttk.Combobox(
            r3,
            textvariable=self.export_mode_var,
            values=[
                "Copy & Rename Original (High Quality)",
                "Inpaint & Stamp Text onto Image",
            ],
            state="readonly",
            width=32,
        )
        combo_exp_mode.pack(side=tk.LEFT, padx=(3, 10))

        ttk.Label(r3, text="Format:").pack(side=tk.LEFT)
        ttk.Combobox(
            r3, textvariable=self.format_var, values=["Keep original", "png", "jpg"], state="readonly", width=13
        ).pack(side=tk.LEFT, padx=2)

        # Row 4: Output Folder
        r4 = ttk.Frame(settings_box)
        r4.pack(fill=tk.X, pady=2)
        ttk.Label(r4, text="Output Folder:").pack(side=tk.LEFT)
        self.ent_out_folder = ttk.Entry(r4, textvariable=self.output_folder_var)
        self.ent_out_folder.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(r4, text="Browse...", command=self.on_browse_output_folder).pack(side=tk.LEFT)

        # Actions Toolbar
        action_bar = ttk.Frame(right_frame)
        action_bar.pack(fill=tk.X, pady=(2, 6))

        self.btn_scan = ttk.Button(
            action_bar,
            text="🔍 Extract Characters (OCR)",
            style="Primary.TButton",
            command=self.on_start_extract_characters,
        )
        self.btn_scan.pack(side=tk.LEFT, padx=(0, 5))

        self.btn_export = ttk.Button(
            action_bar,
            text="📁 Export & Rename Images",
            style="Accent.TButton",
            command=self.on_start_export_images,
        )
        self.btn_export.pack(side=tk.LEFT, padx=3)

        self.btn_csv = ttk.Button(action_bar, text="📊 Export CSV", command=self.on_export_csv)
        self.btn_csv.pack(side=tk.LEFT, padx=3)

        self.btn_preview = ttk.Button(action_bar, text="👁️ Preview", command=self.on_preview_selected)
        self.btn_preview.pack(side=tk.LEFT, padx=3)

        self.btn_cancel = ttk.Button(action_bar, text="⏹️ Stop", command=self.on_stop_processing, state="disabled")
        self.btn_cancel.pack(side=tk.LEFT, padx=3)

        self.progress_bar = ttk.Progressbar(action_bar, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 5))
        self.progress_lbl = ttk.Label(action_bar, text="Idle", foreground="#64748b", width=12, anchor="e")
        self.progress_lbl.pack(side=tk.RIGHT)

        # Results Table
        table_frame = ttk.LabelFrame(right_frame, text="Extracted Characters & Renaming Preview (Double-click to edit)", padding=6)
        table_frame.pack(fill=tk.BOTH, expand=True)

        res_cols = ("orig_file", "region", "var_tag", "ocr_text", "new_name")
        self.res_tree = ttk.Treeview(table_frame, columns=res_cols, show="headings", selectmode="browse")
        self.res_tree.heading("orig_file", text="Original File")
        self.res_tree.heading("region", text="Region")
        self.res_tree.heading("var_tag", text="Tag")
        self.res_tree.heading("ocr_text", text="Extracted Characters (Double-click to edit)")
        self.res_tree.heading("new_name", text="New Filename")

        self.res_tree.column("orig_file", width=140, anchor="w")
        self.res_tree.column("region", width=55, anchor="center")
        self.res_tree.column("var_tag", width=55, anchor="center")
        self.res_tree.column("ocr_text", width=240, anchor="w")
        self.res_tree.column("new_name", width=230, anchor="w")

        v_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.res_tree.yview)
        h_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.res_tree.xview)
        self.res_tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        self.res_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.res_tree.bind("<Double-1>", self.on_tree_double_click)

        # Status Bar
        self.status_bar = ttk.Frame(self.root, padding="6 3")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_msg_lbl = ttk.Label(self.status_bar, text="Ready", font=("Segoe UI", 8))
        self.status_msg_lbl.pack(side=tk.LEFT)
        self.status_engine_lbl = ttk.Label(
            self.status_bar,
            text="Engine: Google Lens / RapidOCR (Zero Tesseract)",
            foreground="#16a34a",
            font=("Segoe UI", 8, "bold"),
        )
        self.status_engine_lbl.pack(side=tk.RIGHT, padx=10)

    def _on_toggle_translate(self):
        if self.enable_translate_var.get():
            self.trans_frame.pack(fill=tk.X, pady=2)
        else:
            self.trans_frame.pack_forget()

    def _insert_template_tag(self, tag: str):
        curr = self.template_var.get()
        self.template_var.set(curr + tag)

    def _update_status(self, msg: str):
        self.status_msg_lbl.config(text=msg)

    # ========================================================================
    # DEMO / SAMPLE IMAGES
    # ========================================================================
    def on_load_demo_images(self):
        """Loads bundled sample images and configures regions automatically."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        demo_dir = os.path.join(base_dir, "sample_images")
        if not os.path.isdir(demo_dir):
            messagebox.showinfo("Demo Images", "Sample images directory not found.")
            return

        self.folder_path = demo_dir
        self.folder_disp_lbl.config(text=demo_dir)

        files = sorted([f for f in os.listdir(demo_dir) if f.lower().endswith(SUPPORTED_EXTENSIONS)], key=natural_sort_key)
        if not files:
            messagebox.showinfo("Demo Images", "No images in sample folder.")
            return

        self.image_files = files
        self.output_folder_var.set(os.path.join(demo_dir, "output"))
        self.sample_combo["values"] = self.image_files
        self.current_sample_idx = 0
        self.sample_combo.current(0)
        self.load_sample_image(self.image_files[0])

        # Predefine 3 standard regions for the demo images:
        # 1. Mã phiếu (190, 130, 480, 175) -> ratios (0.2375, 0.26, 0.6, 0.35)
        # 2. Tên hàng (190, 200, 680, 245)  -> ratios (0.2375, 0.40, 0.85, 0.49)
        # 3. Trạng thái (190, 340, 480, 385)-> ratios (0.2375, 0.68, 0.60, 0.77)
        self.regions = [
            {"rx1": 0.2375, "ry1": 0.26, "rx2": 0.6, "ry2": 0.35},
            {"rx1": 0.2375, "ry1": 0.40, "rx2": 0.85, "ry2": 0.49},
            {"rx1": 0.2375, "ry1": 0.68, "rx2": 0.60, "ry2": 0.77},
        ]
        self.selected_region_idx = 0
        self.template_var.set("{o1}_{o2}")
        self.redraw_canvas()
        self._refresh_region_tree()
        self._update_status(f"Loaded 3 demo images with 3 predefined regions. Click 'Extract Characters' to test!")
        messagebox.showinfo("Demo Loaded", "Successfully loaded 3 sample warehouse tickets with 3 predefined extraction regions!\nClick 'Extract Characters (OCR)' to run.")

    # ========================================================================
    # FOLDER & SAMPLE IMAGE
    # ========================================================================
    def on_choose_folder(self):
        folder = filedialog.askdirectory(title="Choose Image Folder")
        if not folder:
            return

        self.folder_path = os.path.abspath(folder)
        self.folder_disp_lbl.config(text=self.folder_path)

        files = []
        for entry in os.listdir(self.folder_path):
            full_p = os.path.join(self.folder_path, entry)
            if os.path.isfile(full_p) and entry.lower().endswith(SUPPORTED_EXTENSIONS):
                files.append(entry)

        files.sort(key=natural_sort_key)
        self.image_files = files

        if not self.image_files:
            messagebox.showwarning("No Images", f"No supported images found in:\n{self.folder_path}")
            return

        self.output_folder_var.set(os.path.join(self.folder_path, "output"))
        self.sample_combo["values"] = self.image_files
        self.current_sample_idx = 0
        self.sample_combo.current(0)
        self.load_sample_image(self.image_files[0])
        self._update_status(f"Loaded {len(self.image_files)} image(s) from {self.folder_path}")

    def load_sample_image(self, filename: str):
        img_path = os.path.join(self.folder_path, filename)
        if not os.path.isfile(img_path):
            return
        try:
            self.sample_image = Image.open(img_path).convert("RGB")
            orig_w, orig_h = self.sample_image.size
            self.img_info_lbl.config(text=f"{orig_w}x{orig_h} px | {self.current_sample_idx + 1}/{len(self.image_files)}")
            self.redraw_canvas()
            self._refresh_region_tree()
        except Exception as e:
            messagebox.showerror("Error Opening Image", f"Failed to load image:\n{e}")

    def on_sample_combo_selected(self, event=None):
        idx = self.sample_combo.current()
        if 0 <= idx < len(self.image_files):
            self.current_sample_idx = idx
            self.load_sample_image(self.image_files[idx])

    def on_prev_sample(self):
        if not self.image_files:
            return
        self.current_sample_idx = (self.current_sample_idx - 1) % len(self.image_files)
        self.sample_combo.current(self.current_sample_idx)
        self.load_sample_image(self.image_files[self.current_sample_idx])

    def on_next_sample(self):
        if not self.image_files:
            return
        self.current_sample_idx = (self.current_sample_idx + 1) % len(self.image_files)
        self.sample_combo.current(self.current_sample_idx)
        self.load_sample_image(self.image_files[self.current_sample_idx])

    # ========================================================================
    # CANVAS & REGION DRAWING
    # ========================================================================
    def on_canvas_configure(self, event=None):
        if self.sample_image:
            self.redraw_canvas()

    def redraw_canvas(self):
        self.canvas.delete("all")
        if not self.sample_image:
            self.canvas.create_text(
                self.canvas.winfo_width() // 2,
                self.canvas.winfo_height() // 2,
                text="Please choose a folder or click 'Load Demo Images'",
                fill="#94a3b8",
                font=("Segoe UI", 12),
            )
            return

        canvas_w = max(10, self.canvas.winfo_width())
        canvas_h = max(10, self.canvas.winfo_height())
        orig_w, orig_h = self.sample_image.size

        scale = min(canvas_w / orig_w, canvas_h / orig_h)
        self.sample_scale = scale
        disp_w = max(1, int(orig_w * scale))
        disp_h = max(1, int(orig_h * scale))

        self.sample_offset_x = (canvas_w - disp_w) // 2
        self.sample_offset_y = (canvas_h - disp_h) // 2

        resized = self.sample_image.resize((disp_w, disp_h), Image.Resampling.BILINEAR)
        self.sample_photo = ImageTk.PhotoImage(resized)

        self.canvas.create_image(self.sample_offset_x, self.sample_offset_y, anchor="nw", image=self.sample_photo)

        for idx, reg in enumerate(self.regions):
            self._draw_region_on_canvas(idx, reg)

    def _draw_region_on_canvas(self, idx: int, reg: dict):
        orig_w, orig_h = self.sample_image.size
        cx1 = self.sample_offset_x + reg["rx1"] * orig_w * self.sample_scale
        cy1 = self.sample_offset_y + reg["ry1"] * orig_h * self.sample_scale
        cx2 = self.sample_offset_x + reg["rx2"] * orig_w * self.sample_scale
        cy2 = self.sample_offset_y + reg["ry2"] * orig_h * self.sample_scale

        is_selected = idx == self.selected_region_idx
        border_color = "#eab308" if is_selected else "#06b6d4"
        width = 3 if is_selected else 2

        self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=border_color, width=width, tags=f"region_{idx}")

        badge_txt = f"# {idx+1} [{{o{idx+1}}}]"
        badge_w = 55
        badge_h = 18
        bx1, by1 = cx1, max(self.sample_offset_y, cy1 - badge_h)
        bx2, by2 = bx1 + badge_w, by1 + badge_h
        self.canvas.create_rectangle(bx1, by1, bx2, by2, fill=border_color, outline="", tags=f"region_{idx}")
        self.canvas.create_text((bx1 + bx2) / 2, (by1 + by2) / 2, text=badge_txt, fill="#0f172a", font=("Segoe UI", 8, "bold"), tags=f"region_{idx}")

    def on_canvas_press(self, event):
        if not self.sample_image:
            return

        orig_w, orig_h = self.sample_image.size
        clicked_reg_idx = -1
        for idx in reversed(range(len(self.regions))):
            reg = self.regions[idx]
            cx1 = self.sample_offset_x + reg["rx1"] * orig_w * self.sample_scale
            cy1 = self.sample_offset_y + reg["ry1"] * orig_h * self.sample_scale
            cx2 = self.sample_offset_x + reg["rx2"] * orig_w * self.sample_scale
            cy2 = self.sample_offset_y + reg["ry2"] * orig_h * self.sample_scale
            if cx1 <= event.x <= cx2 and cy1 <= event.y <= cy2:
                clicked_reg_idx = idx
                break

        if clicked_reg_idx != -1:
            self._select_region(clicked_reg_idx)
            return

        self.drag_start_x = event.x
        self.drag_start_y = event.y
        if self.active_rect_id:
            self.canvas.delete(self.active_rect_id)
        self.active_rect_id = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#f59e0b", width=2, dash=(4, 4))

    def on_canvas_drag(self, event):
        if self.active_rect_id:
            self.canvas.coords(self.active_rect_id, self.drag_start_x, self.drag_start_y, event.x, event.y)

    def on_canvas_release(self, event):
        if not self.active_rect_id or not self.sample_image:
            return

        self.canvas.delete(self.active_rect_id)
        self.active_rect_id = None

        dx = abs(event.x - self.drag_start_x)
        dy = abs(event.y - self.drag_start_y)
        if dx < 6 or dy < 6:
            return

        orig_w, orig_h = self.sample_image.size
        sx1, sy1 = min(self.drag_start_x, event.x), min(self.drag_start_y, event.y)
        sx2, sy2 = max(self.drag_start_x, event.x), max(self.drag_start_y, event.y)

        ix1 = max(0.0, min(float(orig_w), (sx1 - self.sample_offset_x) / self.sample_scale))
        iy1 = max(0.0, min(float(orig_h), (sy1 - self.sample_offset_y) / self.sample_scale))
        ix2 = max(0.0, min(float(orig_w), (sx2 - self.sample_offset_x) / self.sample_scale))
        iy2 = max(0.0, min(float(orig_h), (sy2 - self.sample_offset_y) / self.sample_scale))

        if ix2 - ix1 < 4 or iy2 - iy1 < 4:
            return

        rx1, ry1 = round(ix1 / orig_w, 4), round(iy1 / orig_h, 4)
        rx2, ry2 = round(ix2 / orig_w, 4), round(iy2 / orig_h, 4)

        new_reg = {"rx1": rx1, "ry1": ry1, "rx2": rx2, "ry2": ry2}
        self.regions.append(new_reg)
        self.selected_region_idx = len(self.regions) - 1
        self.redraw_canvas()
        self._refresh_region_tree()
        self._populate_manual_edit_entries(new_reg)

    def _select_region(self, idx: int):
        self.selected_region_idx = idx
        self.redraw_canvas()
        if 0 <= idx < len(self.regions):
            items = self.reg_tree.get_children()
            if idx < len(items):
                self.reg_tree.selection_set(items[idx])
                self.reg_tree.see(items[idx])
            self._populate_manual_edit_entries(self.regions[idx])

    def _refresh_region_tree(self):
        for item in self.reg_tree.get_children():
            self.reg_tree.delete(item)

        orig_w = self.sample_image.size[0] if self.sample_image else 1
        orig_h = self.sample_image.size[1] if self.sample_image else 1

        for idx, reg in enumerate(self.regions):
            px1, py1 = int(round(reg["rx1"] * orig_w)), int(round(reg["ry1"] * orig_h))
            px2, py2 = int(round(reg["rx2"] * orig_w)), int(round(reg["ry2"] * orig_h))
            px_str = f"({px1}, {py1}) - ({px2}, {py2})"
            ratio_str = f"[{reg['rx1']:.2f}, {reg['ry1']:.2f}, {reg['rx2']:.2f}, {reg['ry2']:.2f}]"
            var_str = f"{{o{idx+1}}}"

            iid = self.reg_tree.insert("", "end", values=(f"#{idx+1}", px_str, ratio_str, var_str))
            if idx == self.selected_region_idx:
                self.reg_tree.selection_set(iid)

    def on_region_selected(self, event=None):
        selected = self.reg_tree.selection()
        if not selected:
            return
        idx = self.reg_tree.index(selected[0])
        if 0 <= idx < len(self.regions):
            self.selected_region_idx = idx
            self.redraw_canvas()
            self._populate_manual_edit_entries(self.regions[idx])

    def _populate_manual_edit_entries(self, reg: dict):
        if not self.sample_image:
            return
        orig_w, orig_h = self.sample_image.size
        x1, y1 = int(round(reg["rx1"] * orig_w)), int(round(reg["ry1"] * orig_h))
        x2, y2 = int(round(reg["rx2"] * orig_w)), int(round(reg["ry2"] * orig_h))

        for ent, val in [(self.ent_x1, x1), (self.ent_y1, y1), (self.ent_x2, x2), (self.ent_y2, y2)]:
            ent.delete(0, tk.END)
            ent.insert(0, str(val))

    def on_update_region_coords(self):
        if self.selected_region_idx < 0 or self.selected_region_idx >= len(self.regions):
            messagebox.showinfo("Select Region", "Please select a region to edit.")
            return
        if not self.sample_image:
            return

        try:
            x1, y1 = int(self.ent_x1.get().strip()), int(self.ent_y1.get().strip())
            x2, y2 = int(self.ent_x2.get().strip()), int(self.ent_y2.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter integer pixel numbers for X1, Y1, X2, Y2.")
            return

        orig_w, orig_h = self.sample_image.size
        nx1, ny1 = max(0, min(orig_w, min(x1, x2))), max(0, min(orig_h, min(y1, y2)))
        nx2, ny2 = max(0, min(orig_w, max(x1, x2))), max(0, min(orig_h, max(y1, y2)))

        if nx2 - nx1 < 4 or ny2 - ny1 < 4:
            messagebox.showerror("Invalid Size", "Region must be at least 4x4 pixels.")
            return

        self.regions[self.selected_region_idx] = {
            "rx1": round(nx1 / orig_w, 4),
            "ry1": round(ny1 / orig_h, 4),
            "rx2": round(nx2 / orig_w, 4),
            "ry2": round(ny2 / orig_h, 4),
        }
        self.redraw_canvas()
        self._refresh_region_tree()

    def on_delete_region(self):
        if self.selected_region_idx < 0 or self.selected_region_idx >= len(self.regions):
            return
        del self.regions[self.selected_region_idx]
        self.selected_region_idx = min(self.selected_region_idx, len(self.regions) - 1)
        self.redraw_canvas()
        self._refresh_region_tree()

    def on_clear_regions(self):
        if not self.regions:
            return
        if messagebox.askyesno("Clear All Regions", "Are you sure you want to remove all defined regions?"):
            self.regions.clear()
            self.selected_region_idx = -1
            self.redraw_canvas()
            self._refresh_region_tree()

    def on_save_config(self):
        fpath = filedialog.asksaveasfilename(title="Save Configuration", defaultextension=".json", filetypes=[("JSON Files", "*.json")])
        if not fpath:
            return

        cfg = {
            "regions": self.regions,
            "ocr_engine": self.ocr_engine_var.get(),
            "enable_translate": self.enable_translate_var.get(),
            "source_lang": self.source_lang_var.get(),
            "target_lang": self.target_lang_var.get(),
            "name_template": self.template_var.get(),
            "export_mode": self.export_mode_var.get(),
            "output_format": self.format_var.get(),
        }

        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Saved", f"Configuration successfully saved to:\n{fpath}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save configuration:\n{e}")

    def on_load_config(self):
        fpath = filedialog.askopenfilename(title="Load Configuration", filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")])
        if not fpath:
            return

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            if "regions" in cfg and isinstance(cfg["regions"], list):
                self.regions = cfg["regions"]
                self.selected_region_idx = 0 if self.regions else -1

            if "ocr_engine" in cfg:
                self.ocr_engine_var.set(cfg["ocr_engine"])

            if "enable_translate" in cfg:
                self.enable_translate_var.set(cfg["enable_translate"])
                self._on_toggle_translate()

            if "source_lang" in cfg and cfg["source_lang"] in LANGUAGES:
                self.source_lang_var.set(cfg["source_lang"])

            if "target_lang" in cfg and cfg["target_lang"] in LANGUAGES:
                self.target_lang_var.set(cfg["target_lang"])

            if "name_template" in cfg:
                self.template_var.set(cfg["name_template"])

            if "export_mode" in cfg:
                self.export_mode_var.set(cfg["export_mode"])

            if "output_format" in cfg:
                self.format_var.set(cfg["output_format"])

            self.redraw_canvas()
            self._refresh_region_tree()
            messagebox.showinfo("Configuration Loaded", f"Successfully loaded configuration from:\n{fpath}")
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load configuration:\n{e}")

    def on_browse_output_folder(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_folder_var.set(os.path.abspath(folder))

    # ========================================================================
    # CHARACTER EXTRACTION (OCR)
    # ========================================================================
    def on_start_extract_characters(self):
        if not self.image_files:
            messagebox.showwarning("No Images", "Please open an image folder or click 'Load Demo Images' first.")
            return

        if not self.regions:
            messagebox.showwarning("No Regions", "Please draw at least one region on the image first.")
            return

        self.is_processing = True
        self.stop_requested = False
        self._toggle_ui_state(False)

        for item in self.res_tree.get_children():
            self.res_tree.delete(item)
        self.results_data.clear()

        thread = threading.Thread(target=self._extract_worker, daemon=True)
        thread.start()

    def _toggle_ui_state(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.btn_scan.config(state=state)
        self.btn_export.config(state=state)
        self.btn_csv.config(state=state)
        self.btn_preview.config(state=state)
        self.btn_cancel.config(state="normal" if not enabled else "disabled")

    def on_stop_processing(self):
        if self.is_processing:
            self.stop_requested = True
            self._update_status("Stopping process... Please wait.")

    def _extract_worker(self):
        chosen_engine = self.ocr_engine_var.get()
        if "Google" in chosen_engine and HAVE_LENS:
            asyncio.run(self._async_google_extract())
        elif HAVE_RAPIDOCR:
            self._sync_rapidocr_extract()
        elif HAVE_LENS:
            asyncio.run(self._async_google_extract())
        else:
            self.root.after(0, messagebox.showerror, "No Engine", "Neither Google Lens nor RapidOCR is available.")
            self.is_processing = False
            self._toggle_ui_state(True)

    async def _async_google_extract(self):
        total_images = len(self.image_files)
        do_translate = self.enable_translate_var.get()
        src_code = LANGUAGES.get(self.source_lang_var.get(), "auto")
        tgt_code = LANGUAGES.get(self.target_lang_var.get(), "vi")

        lens = LensAPI()
        try:
            for img_idx, filename in enumerate(self.image_files):
                if self.stop_requested:
                    break

                pct = int(((img_idx + 1) / total_images) * 100)
                self.root.after(0, self._update_progress, pct, f"{img_idx + 1}/{total_images}")
                self.root.after(0, self._update_status, f"Extracting characters ({img_idx + 1}/{total_images}): {filename}...")

                img_path = os.path.join(self.folder_path, filename)
                try:
                    img = Image.open(img_path).convert("RGB")
                except Exception as e:
                    print(f"Error opening image {filename}: {e}", file=sys.stderr)
                    continue

                orig_w, orig_h = img.size
                file_stem = os.path.splitext(filename)[0]

                image_ocr_texts = []
                image_trans_texts = []

                for r_idx, reg in enumerate(self.regions):
                    if self.stop_requested:
                        break

                    x1 = int(round(reg["rx1"] * orig_w))
                    y1 = int(round(reg["ry1"] * orig_h))
                    x2 = int(round(reg["rx2"] * orig_w))
                    y2 = int(round(reg["ry2"] * orig_h))
                    x1 = max(0, min(orig_w - 1, x1))
                    y1 = max(0, min(orig_h - 1, y1))
                    x2 = max(x1 + 1, min(orig_w, x2))
                    y2 = max(y1 + 1, min(orig_h, y2))

                    crop_img = img.crop((x1, y1, x2, y2))

                    try:
                        res = await lens.process_image(
                            crop_img,
                            source_translation_language=src_code if src_code != "auto" else None,
                            target_translation_language=tgt_code if do_translate else None,
                        )
                        ocr_text = res.get("ocr_text", "").strip()
                        trans_text = res.get("translated_text", "").strip() if do_translate else ocr_text
                    except Exception as e:
                        print(f"Extraction error: {e}", file=sys.stderr)
                        ocr_text = ""
                        trans_text = ""

                    image_ocr_texts.append(ocr_text)
                    image_trans_texts.append(trans_text)

                new_file_stem = compute_filename(
                    self.template_var.get(),
                    img_idx + 1,
                    file_stem,
                    image_ocr_texts,
                    image_trans_texts,
                )
                orig_ext = os.path.splitext(filename)[1].lstrip(".")
                chosen_fmt = self.format_var.get().lower()
                final_ext = "png" if "png" in chosen_fmt else ("jpg" if "jpg" in chosen_fmt else orig_ext)
                new_full_name = f"{new_file_stem}.{final_ext}"

                for r_idx in range(len(self.regions)):
                    row_data = {
                        "orig_file": filename,
                        "region": f"#{r_idx + 1}",
                        "var_tag": f"{{o{r_idx + 1}}}",
                        "region_idx": r_idx,
                        "img_idx": img_idx,
                        "ocr_text": image_ocr_texts[r_idx],
                        "translation": image_trans_texts[r_idx],
                        "new_name": new_full_name,
                    }
                    self.results_data.append(row_data)
                    self.root.after(0, self._insert_tree_row, row_data)

        finally:
            await lens.aclose()

        self.root.after(0, self._on_scan_finished)

    def _sync_rapidocr_extract(self):
        total_images = len(self.image_files)
        engine = RapidOCR()

        for img_idx, filename in enumerate(self.image_files):
            if self.stop_requested:
                break

            pct = int(((img_idx + 1) / total_images) * 100)
            self.root.after(0, self._update_progress, pct, f"{img_idx + 1}/{total_images}")
            self.root.after(0, self._update_status, f"RapidOCR extracting ({img_idx + 1}/{total_images}): {filename}...")

            img_path = os.path.join(self.folder_path, filename)
            try:
                img = Image.open(img_path).convert("RGB")
            except Exception as e:
                print(f"Error opening image {filename}: {e}", file=sys.stderr)
                continue

            orig_w, orig_h = img.size
            file_stem = os.path.splitext(filename)[0]

            image_ocr_texts = []

            for r_idx, reg in enumerate(self.regions):
                if self.stop_requested:
                    break

                x1 = int(round(reg["rx1"] * orig_w))
                y1 = int(round(reg["ry1"] * orig_h))
                x2 = int(round(reg["rx2"] * orig_w))
                y2 = int(round(reg["ry2"] * orig_h))
                x1 = max(0, min(orig_w - 1, x1))
                y1 = max(0, min(orig_h - 1, y1))
                x2 = max(x1 + 1, min(orig_w, x2))
                y2 = max(y1 + 1, min(orig_h, y2))

                crop_img = img.crop((x1, y1, x2, y2))
                try:
                    res, _ = engine(np.array(crop_img))
                    ocr_text = " ".join([line[1] for line in res]).strip() if res else ""
                except Exception as e:
                    ocr_text = ""

                image_ocr_texts.append(ocr_text)

            new_file_stem = compute_filename(
                self.template_var.get(),
                img_idx + 1,
                file_stem,
                image_ocr_texts,
                image_ocr_texts,
            )
            orig_ext = os.path.splitext(filename)[1].lstrip(".")
            chosen_fmt = self.format_var.get().lower()
            final_ext = "png" if "png" in chosen_fmt else ("jpg" if "jpg" in chosen_fmt else orig_ext)
            new_full_name = f"{new_file_stem}.{final_ext}"

            for r_idx in range(len(self.regions)):
                row_data = {
                    "orig_file": filename,
                    "region": f"#{r_idx + 1}",
                    "var_tag": f"{{o{r_idx + 1}}}",
                    "region_idx": r_idx,
                    "img_idx": img_idx,
                    "ocr_text": image_ocr_texts[r_idx],
                    "translation": image_ocr_texts[r_idx],
                    "new_name": new_full_name,
                }
                self.results_data.append(row_data)
                self.root.after(0, self._insert_tree_row, row_data)

        self.root.after(0, self._on_scan_finished)

    def _insert_tree_row(self, row: dict):
        self.res_tree.insert(
            "",
            "end",
            values=(
                row["orig_file"],
                row["region"],
                row["var_tag"],
                row["ocr_text"],
                row["new_name"],
            ),
        )

    def _update_progress(self, pct: int, text: str):
        self.progress_bar["value"] = pct
        self.progress_lbl.config(text=text)

    def _on_scan_finished(self):
        self.is_processing = False
        self._toggle_ui_state(True)
        self.progress_bar["value"] = 100
        status_txt = "Stopped by user." if self.stop_requested else "Character extraction complete!"
        self.progress_lbl.config(text="Complete" if not self.stop_requested else "Stopped")
        self._update_status(status_txt)
        messagebox.showinfo("Extraction Completed", f"{status_txt}\nProcessed {len(self.image_files)} image(s).")

    # ========================================================================
    # INLINE EDITING IN TREEVIEW TABLE
    # ========================================================================
    def on_tree_double_click(self, event):
        region = self.res_tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        column = self.res_tree.identify_column(event.x)
        item = self.res_tree.identify_row(event.y)
        if not item:
            return

        col_idx = int(column.replace("#", "")) - 1
        # Only allow editing Extracted Text (col 3)
        if col_idx != 3:
            return

        x, y, w, h = self.res_tree.bbox(item, column)
        current_values = list(self.res_tree.item(item, "values"))
        current_text = current_values[col_idx]

        edit_entry = ttk.Entry(self.res_tree)
        edit_entry.place(x=x, y=y, width=w, height=h)
        edit_entry.insert(0, current_text)
        edit_entry.select_range(0, tk.END)
        edit_entry.focus_set()

        def commit_edit(evt=None):
            new_text = edit_entry.get()
            edit_entry.destroy()

            current_values[col_idx] = new_text
            self.res_tree.item(item, values=current_values)

            item_idx = self.res_tree.index(item)
            if 0 <= item_idx < len(self.results_data):
                self.results_data[item_idx]["ocr_text"] = new_text
                self.results_data[item_idx]["translation"] = new_text

                target_filename = self.results_data[item_idx]["orig_file"]
                img_idx = self.results_data[item_idx]["img_idx"]
                self._recalculate_filenames_for_image(target_filename, img_idx)

        edit_entry.bind("<Return>", commit_edit)
        edit_entry.bind("<FocusOut>", commit_edit)
        edit_entry.bind("<Escape>", lambda e: edit_entry.destroy())

    def _recalculate_filenames_for_image(self, filename: str, img_idx: int):
        orig_stem = os.path.splitext(filename)[0]
        ocr_texts = []
        trans_texts = []
        row_indices = []

        for idx, row in enumerate(self.results_data):
            if row["orig_file"] == filename:
                ocr_texts.append(row["ocr_text"])
                trans_texts.append(row["translation"])
                row_indices.append(idx)

        new_stem = compute_filename(
            self.template_var.get(),
            img_idx + 1,
            orig_stem,
            ocr_texts,
            trans_texts,
        )

        orig_ext = os.path.splitext(filename)[1].lstrip(".")
        chosen_fmt = self.format_var.get().lower()
        final_ext = "png" if "png" in chosen_fmt else ("jpg" if "jpg" in chosen_fmt else orig_ext)
        updated_name = f"{new_stem}.{final_ext}"

        tree_items = self.res_tree.get_children()
        for r_idx in row_indices:
            self.results_data[r_idx]["new_name"] = updated_name
            if r_idx < len(tree_items):
                vals = list(self.res_tree.item(tree_items[r_idx], "values"))
                vals[4] = updated_name
                self.res_tree.item(tree_items[r_idx], values=vals)

    def _on_template_or_format_changed(self, *args):
        if not self.results_data:
            return
        images_seen = {}
        for row in self.results_data:
            fn = row["orig_file"]
            if fn not in images_seen:
                images_seen[fn] = row["img_idx"]
        for fn, img_idx in images_seen.items():
            self._recalculate_filenames_for_image(fn, img_idx)

    # ========================================================================
    # PREVIEW & EXPORT CSV
    # ========================================================================
    def on_export_csv(self):
        """Exports the extracted character table to a CSV file."""
        if not self.results_data:
            messagebox.showinfo("Export CSV", "No extracted data available to export. Please run extraction first.")
            return

        fpath = filedialog.asksaveasfilename(
            title="Save Extracted Characters CSV",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
        )
        if not fpath:
            return

        try:
            with open(fpath, "w", newline="", encoding="utf-8-sig") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Original File", "Region", "Tag", "Extracted Characters", "New Filename"])
                for row in self.results_data:
                    writer.writerow([row["orig_file"], row["region"], row["var_tag"], row["ocr_text"], row["new_name"]])
            messagebox.showinfo("CSV Exported", f"Successfully exported extracted data to:\n{fpath}")
        except Exception as e:
            messagebox.showerror("CSV Error", f"Failed to export CSV:\n{e}")

    def on_preview_selected(self):
        selected = self.res_tree.selection()
        if selected:
            item_idx = self.res_tree.index(selected[0])
            target_filename = self.results_data[item_idx]["orig_file"]
        elif self.image_files:
            target_filename = self.image_files[self.current_sample_idx]
        else:
            messagebox.showinfo("Preview", "Please open a folder and scan or select an image.")
            return

        rendered_img = self._render_output_image(target_filename)
        if not rendered_img:
            messagebox.showerror("Preview Error", f"Unable to generate preview for {target_filename}")
            return

        prev_win = tk.Toplevel(self.root)
        prev_win.title(f"Preview Output: {target_filename}")
        prev_win.geometry("900x700")

        lbl_hdr = ttk.Label(prev_win, text=f"Preview of output image: {target_filename}", style="Header.TLabel")
        lbl_hdr.pack(anchor="w", padx=10, pady=8)

        p_canvas = tk.Canvas(prev_win, bg="#0f172a", highlightthickness=0)
        p_canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        def fit_preview(evt=None):
            cw, ch = max(50, p_canvas.winfo_width()), max(50, p_canvas.winfo_height())
            iw, ih = rendered_img.size
            sc = min(cw / iw, ch / ih, 1.0)
            dw, dh = max(1, int(iw * sc)), max(1, int(ih * sc))

            resized = rendered_img.resize((dw, dh), Image.Resampling.BILINEAR)
            prev_win._photo = ImageTk.PhotoImage(resized)
            p_canvas.delete("all")
            p_canvas.create_image(cw // 2, ch // 2, anchor="center", image=prev_win._photo)

        p_canvas.bind("<Configure>", fit_preview)
        fit_preview()

    def _render_output_image(self, filename: str) -> Image.Image:
        img_path = os.path.join(self.folder_path, filename)
        if not os.path.isfile(img_path):
            return None

        try:
            out_img = Image.open(img_path).convert("RGB")
        except Exception:
            return None

        draw = ImageDraw.Draw(out_img)
        orig_w, orig_h = out_img.size

        file_texts = {}
        for row in self.results_data:
            if row["orig_file"] == filename:
                file_texts[row["region_idx"]] = row["ocr_text"]

        font_path = self.font_path_var.get()

        for idx, reg in enumerate(self.regions):
            x1 = int(round(reg["rx1"] * orig_w))
            y1 = int(round(reg["ry1"] * orig_h))
            x2 = int(round(reg["rx2"] * orig_w))
            y2 = int(round(reg["ry2"] * orig_h))
            x1, y1 = max(0, min(orig_w - 1, x1)), max(0, min(orig_h - 1, y1))
            x2, y2 = max(x1 + 1, min(orig_w, x2)), max(y1 + 1, min(orig_h, y2))

            box = (x1, y1, x2, y2)
            median_color = get_box_median_color(out_img, box)
            draw.rectangle(box, fill=median_color)

            txt = file_texts.get(idx, f"Region #{idx+1}")
            fit_and_draw_text(
                draw,
                txt,
                box,
                font_path=font_path,
                padding=4,
                bg_color=median_color,
            )

        return out_img

    # ========================================================================
    # EXPORT & RENAME IMAGES
    # ========================================================================
    def on_start_export_images(self):
        if not self.image_files:
            messagebox.showwarning("No Images", "Please open an image folder first.")
            return

        if not self.results_data:
            messagebox.showwarning("Not Extracted", "Please click 'Extract Characters' first so new filenames can be computed.")
            return

        out_folder = self.output_folder_var.get().strip()
        if not out_folder:
            out_folder = os.path.join(self.folder_path, "output")
            self.output_folder_var.set(out_folder)

        try:
            os.makedirs(out_folder, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Output Folder Error", f"Cannot create output directory:\n{e}")
            return

        self.is_processing = True
        self.stop_requested = False
        self._toggle_ui_state(False)

        thread = threading.Thread(target=self._export_images_worker, daemon=True)
        thread.start()

    def _export_images_worker(self):
        out_folder = self.output_folder_var.get().strip()
        total_images = len(self.image_files)
        used_filenames = set()

        filename_map = {}
        for row in self.results_data:
            filename_map[row["orig_file"]] = row["new_name"]

        chosen_mode = self.export_mode_var.get()
        chosen_format = self.format_var.get().lower()

        for idx, filename in enumerate(self.image_files):
            if self.stop_requested:
                break

            pct = int(((idx + 1) / total_images) * 100)
            self.root.after(0, self._update_progress, pct, f"{idx + 1}/{total_images}")
            self.root.after(0, self._update_status, f"Exporting ({idx + 1}/{total_images}): {filename}...")

            orig_path = os.path.join(self.folder_path, filename)
            orig_stem = os.path.splitext(filename)[0]
            orig_ext = os.path.splitext(filename)[1].lstrip(".")

            save_ext = "png" if "png" in chosen_format else ("jpg" if "jpg" in chosen_format else orig_ext)

            if filename in filename_map:
                base_stem = os.path.splitext(filename_map[filename])[0]
            else:
                base_stem = compute_filename(self.template_var.get(), idx + 1, orig_stem, [], [])

            final_path = get_unique_output_path(out_folder, base_stem, save_ext, used_filenames)

            try:
                if "Copy & Rename Original" in chosen_mode and save_ext.lower() == orig_ext.lower():
                    # Fast exact bit-for-bit file copy
                    shutil.copy2(orig_path, final_path)
                else:
                    # Inpaint or format conversion
                    if "Inpaint" in chosen_mode:
                        rendered_img = self._render_output_image(filename)
                    else:
                        rendered_img = Image.open(orig_path).convert("RGB")

                    if save_ext in ("jpg", "jpeg"):
                        rendered_img.save(final_path, format="JPEG", quality=95)
                    else:
                        rendered_img.save(final_path, format="PNG")
            except Exception as e:
                print(f"Error exporting image to {final_path}: {e}", file=sys.stderr)

        self.root.after(0, self._on_export_finished, out_folder)

    def _on_export_finished(self, out_folder: str):
        self.is_processing = False
        self._toggle_ui_state(True)
        self.progress_bar["value"] = 100
        self.progress_lbl.config(text="Exported")
        status_txt = "Export cancelled." if self.stop_requested else f"Export completed to {out_folder}"
        self._update_status(status_txt)

        if not self.stop_requested:
            res = messagebox.askyesno(
                "Export Complete",
                f"Successfully exported renamed images to:\n{out_folder}\n\nWould you like to open the output folder now?",
            )
            if res:
                self._open_in_file_manager(out_folder)

    def _open_in_file_manager(self, folder: str):
        current_os = platform.system()
        try:
            if current_os == "Windows":
                os.startfile(folder)
            elif current_os == "Darwin":
                import subprocess
                subprocess.Popen(["open", folder])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            print(f"Failed to open folder: {e}", file=sys.stderr)


# ============================================================================
# 5. APPLICATION ENTRY POINT
# ============================================================================
def main():
    root = tk.Tk()
    app = BatchImageTranslatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
