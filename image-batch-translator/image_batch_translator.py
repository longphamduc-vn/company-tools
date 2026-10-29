#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image Batch Translator & Smart Renamer
=======================================
A cross-platform desktop application written in Python (Tkinter GUI).
Translate text in batches of images sharing the same layout structure,
paint over old text with median background color, render translated text,
and export renamed image files according to customizable templates.

Dependencies:
    - Pillow (PIL)
    - pytesseract
    - deep-translator
    - tkinter (built into standard Python)
"""

import sys
import os
import re
import json
import time
import shutil
import platform
import threading
import statistics
import unicodedata
from string import Formatter

# ============================================================================
# 1. DEPENDENCY CHECK & GRACEFUL ERROR HANDLING
# ============================================================================
MISSING_PACKAGES = []

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageOps
except ImportError:
    MISSING_PACKAGES.append("pillow")

try:
    import pytesseract
except ImportError:
    MISSING_PACKAGES.append("pytesseract")

try:
    from deep_translator import GoogleTranslator
except ImportError:
    MISSING_PACKAGES.append("deep-translator")

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

if MISSING_PACKAGES:
    missing_str = " ".join(MISSING_PACKAGES)
    pip_cmd = f"pip install {missing_str}"
    error_msg = (
        f"Missing required Python libraries: {', '.join(MISSING_PACKAGES)}\n\n"
        f"Please install them by opening your terminal / command prompt and running:\n\n"
        f"    {pip_cmd}\n"
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

# Language mapping: Display Name -> {tesseract OCR code, deep-translator code}
LANGUAGES = {
    "English": {"ocr": "eng", "trans": "en"},
    "Vietnamese": {"ocr": "vie", "trans": "vi"},
    "Chinese (Simplified)": {"ocr": "chi_sim", "trans": "zh-CN"},
    "Chinese (Traditional)": {"ocr": "chi_tra", "trans": "zh-TW"},
    "Japanese": {"ocr": "jpn", "trans": "ja"},
    "Korean": {"ocr": "kor", "trans": "ko"},
    "Russian": {"ocr": "rus", "trans": "ru"},
    "French": {"ocr": "fra", "trans": "fr"},
    "German": {"ocr": "deu", "trans": "de"},
    "Spanish": {"ocr": "spa", "trans": "es"},
    "Thai": {"ocr": "tha", "trans": "th"},
}

PSM_OPTIONS = [
    "6 - Single uniform block of text (Default)",
    "3 - Fully automatic page segmentation",
    "4 - Single column of text of variable sizes",
    "7 - Treat image as a single text line",
    "11 - Sparse text: find as much text as possible",
    "12 - Sparse text with OSD",
    "1 - Automatic page segmentation with OSD",
]

DEFAULT_NAME_TEMPLATE = "{index:03d}_{t1}"


def auto_detect_tesseract() -> str:
    """Automatically detect Tesseract-OCR binary path across OSes."""
    # 1. Check if already in PATH
    which_path = shutil.which("tesseract")
    if which_path and os.path.exists(which_path):
        return which_path

    current_os = platform.system()
    candidates = []

    if current_os == "Windows":
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_app = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(prog_files, "Tesseract-OCR", "tesseract.exe"),
            os.path.join(prog_files_x86, "Tesseract-OCR", "tesseract.exe"),
            os.path.join(local_app, "Programs", "Tesseract-OCR", "tesseract.exe"),
            r"C:\Tesseract-OCR\tesseract.exe",
        ]
    elif current_os == "Darwin":  # macOS
        candidates = [
            "/opt/homebrew/bin/tesseract",
            "/usr/local/bin/tesseract",
            "/usr/bin/tesseract",
        ]
    else:  # Linux / Unix
        candidates = [
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
            "/opt/tesseract/bin/tesseract",
        ]

    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return ""


# Initialize Tesseract path if found
detected_tesseract = auto_detect_tesseract()
if detected_tesseract:
    pytesseract.pytesseract.tesseract_cmd = detected_tesseract


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
    """
    Sanitize filename while preserving Unicode/Vietnamese diacritics.
    Removes invalid characters: \\ / : * ? " < > | and newlines.
    """
    filename = unicodedata.normalize("NFC", str(filename))
    # Replace invalid chars with underscore
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", filename)
    # Collapse consecutive whitespace and underscores
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
        # Fallback if invalid template format
        raw_formatted = f"{index:03d}_{orig_stem}"

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
    """
    Computes the median RGB color of the pixels along the border of `box` = (x1, y1, x2, y2).
    """
    x1, y1, x2, y2 = box
    w, h = img.size
    x1 = max(0, min(x1, w - 1))
    x2 = max(x1 + 1, min(x2, w))
    y1 = max(0, min(y1, h - 1))
    y2 = max(y1 + 1, min(y2, h))

    border_pixels = []
    # Top and bottom edges
    for x in range(x1, x2):
        border_pixels.append(img.getpixel((x, y1)))
        border_pixels.append(img.getpixel((x, y2 - 1)))
    # Left and right edges
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
    """
    Renders text inside `box` = (x1, y1, x2, y2):
    - Automatically wraps text into multiple lines.
    - Decreases font size until text fits inside box width & height.
    - Centers text horizontally and vertically.
    - Text color is calculated based on background color brightness.
    """
    x1, y1, x2, y2 = box
    box_w = max(1, x2 - x1)
    box_h = max(1, y2 - y1)
    avail_w = max(1, box_w - 2 * padding)
    avail_h = max(1, box_h - 2 * padding)

    cleaned_text = text.strip()
    if not cleaned_text:
        return

    # Start font size based on box height (clamped)
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

        # Process each paragraph
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
                        # Check if single word exceeds avail_w
                        wb = draw.textbbox((0, 0), word, font=font)
                        if (wb[2] - wb[0]) > avail_w:
                            # Break word character by character
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
                        # Even first word exceeds width
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
        # Check if all lines fit within available width and total height
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
            break  # Fits perfectly

        font_size -= 2

    # Draw centered
    # Calculate background color of box to pick contrasting text color
    if bg_color is None:
        target_img = getattr(draw, "_image", None)
        if target_img:
            med_bg = get_box_median_color(target_img, box)
        else:
            med_bg = (255, 255, 255)
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
        self.root.title("Batch Image OCR, Translator & Renamer")
        self.root.geometry("1260x820")
        self.root.minsize(1050, 700)

        # Apply clean theme
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

        # Regions: list of dicts: {"rx1": float, "ry1": float, "rx2": float, "ry2": float}
        self.regions = []
        self.selected_region_idx = -1

        # Interactive drawing state
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.active_rect_id = None

        # Data & Caching
        self.translation_cache = {}  # {source_text: translated_text}
        # Table data: list of dicts: {filename, region_idx, ocr_text, translation, new_name}
        self.results_data = []

        # Configuration variables
        self.source_lang_var = tk.StringVar(value="English")
        self.target_lang_var = tk.StringVar(value="Vietnamese")
        self.psm_var = tk.StringVar(value=PSM_OPTIONS[0])
        self.template_var = tk.StringVar(value=DEFAULT_NAME_TEMPLATE)
        self.format_var = tk.StringVar(value="Keep original")
        self.output_folder_var = tk.StringVar(value="")
        self.font_path_var = tk.StringVar(value=find_default_font())
        self.tesseract_cmd_var = tk.StringVar(value=detected_tesseract)

        self.template_var.trace_add("write", self._on_template_or_format_changed)
        self.format_var.trace_add("write", self._on_template_or_format_changed)

        # Processing Threading & Cancellation
        self.is_processing = False
        self.stop_requested = False

        # Build UI
        self._build_ui()
        self._update_status("Ready. Please select an image folder to get started.")

    def _init_theme_styles(self):
        """Configure ttk colors and modern aesthetics."""
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
        """Constructs the comprehensive user interface."""
        # Top Header Bar
        top_bar = ttk.Frame(self.root, padding="10 8")
        top_bar.pack(side=tk.TOP, fill=tk.X)

        title_lbl = ttk.Label(top_bar, text="Batch Image Translator & Renamer", style="Title.TLabel")
        title_lbl.pack(side=tk.LEFT, padx=(0, 15))

        btn_open = ttk.Button(top_bar, text="📁 Choose Folder...", command=self.on_choose_folder)
        btn_open.pack(side=tk.LEFT, padx=3)

        btn_save_cfg = ttk.Button(top_bar, text="💾 Save Config", command=self.on_save_config)
        btn_save_cfg.pack(side=tk.LEFT, padx=3)

        btn_load_cfg = ttk.Button(top_bar, text="📂 Load Config", command=self.on_load_config)
        btn_load_cfg.pack(side=tk.LEFT, padx=3)

        btn_tess = ttk.Button(top_bar, text="⚙️ Tesseract Settings", command=self.on_tesseract_settings)
        btn_tess.pack(side=tk.LEFT, padx=3)

        self.folder_disp_lbl = ttk.Label(top_bar, text="No folder selected", foreground="#64748b")
        self.folder_disp_lbl.pack(side=tk.RIGHT, padx=5)

        # Main Split View (PanedWindow)
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 5))

        # ====================================================================
        # LEFT PANE: Canvas, Sample Image, Region Drawing & Region Editor
        # ====================================================================
        left_frame = ttk.Frame(paned, padding=5)
        paned.add(left_frame, weight=5)

        # Sample Image Selection Bar
        sample_bar = ttk.Frame(left_frame)
        sample_bar.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(sample_bar, text="Sample Image:", style="Header.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self.sample_combo = ttk.Combobox(sample_bar, state="readonly", width=32)
        self.sample_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.sample_combo.bind("<<ComboboxSelected>>", self.on_sample_combo_selected)

        btn_prev = ttk.Button(sample_bar, text="◀", width=3, command=self.on_prev_sample)
        btn_prev.pack(side=tk.LEFT, padx=2)
        btn_next = ttk.Button(sample_bar, text="▶", width=3, command=self.on_next_sample)
        btn_next.pack(side=tk.LEFT, padx=2)

        self.img_info_lbl = ttk.Label(sample_bar, text="", foreground="#64748b")
        self.img_info_lbl.pack(side=tk.RIGHT, padx=4)

        # Canvas Frame with scrollbars & responsive resize
        canvas_container = ttk.Frame(left_frame, borderwidth=1, relief="solid")
        canvas_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_container, bg="#1e293b", cursor="cross", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        # Region Management Controls (Below Canvas)
        reg_ctrl_frame = ttk.LabelFrame(left_frame, text="Defined Regions (Text Boxes)", padding=6)
        reg_ctrl_frame.pack(fill=tk.X, pady=(6, 0))

        # Treeview for regions
        cols = ("id", "pixels", "ratios")
        self.reg_tree = ttk.Treeview(reg_ctrl_frame, columns=cols, show="headings", height=4, selectmode="browse")
        self.reg_tree.heading("id", text="#")
        self.reg_tree.heading("pixels", text="Pixel Coords [X1, Y1, X2, Y2]")
        self.reg_tree.heading("ratios", text="Relative Ratios [RX1, RY1, RX2, RY2]")
        self.reg_tree.column("id", width=35, anchor="center")
        self.reg_tree.column("pixels", width=200, anchor="w")
        self.reg_tree.column("ratios", width=240, anchor="w")

        reg_scroll = ttk.Scrollbar(reg_ctrl_frame, orient="vertical", command=self.reg_tree.yview)
        self.reg_tree.configure(yscrollcommand=reg_scroll.set)
        self.reg_tree.pack(side=tk.TOP, fill=tk.X, expand=True)
        self.reg_tree.bind("<<TreeviewSelect>>", self.on_region_selected)

        # Region manual edit bar
        edit_bar = ttk.Frame(reg_ctrl_frame)
        edit_bar.pack(fill=tk.X, pady=(5, 0))

        ttk.Label(edit_bar, text="Manual Edit: X1:").pack(side=tk.LEFT)
        self.ent_x1 = ttk.Entry(edit_bar, width=5)
        self.ent_x1.pack(side=tk.LEFT, padx=2)

        ttk.Label(edit_bar, text="Y1:").pack(side=tk.LEFT)
        self.ent_y1 = ttk.Entry(edit_bar, width=5)
        self.ent_y1.pack(side=tk.LEFT, padx=2)

        ttk.Label(edit_bar, text="X2:").pack(side=tk.LEFT)
        self.ent_x2 = ttk.Entry(edit_bar, width=5)
        self.ent_x2.pack(side=tk.LEFT, padx=2)

        ttk.Label(edit_bar, text="Y2:").pack(side=tk.LEFT)
        self.ent_y2 = ttk.Entry(edit_bar, width=5)
        self.ent_y2.pack(side=tk.LEFT, padx=2)

        btn_update_reg = ttk.Button(edit_bar, text="Apply Coords", command=self.on_update_region_coords)
        btn_update_reg.pack(side=tk.LEFT, padx=4)

        btn_del_reg = ttk.Button(edit_bar, text="❌ Delete Region", command=self.on_delete_region)
        btn_del_reg.pack(side=tk.LEFT, padx=3)

        btn_clear_reg = ttk.Button(edit_bar, text="🗑️ Clear All", command=self.on_clear_regions)
        btn_clear_reg.pack(side=tk.LEFT, padx=3)

        # Tip note
        ttk.Label(
            reg_ctrl_frame,
            text="💡 Tip: Click and drag on the image above to define text regions. Click any region to select/edit.",
            foreground="#64748b",
            font=("Segoe UI", 8, "italic"),
        ).pack(side=tk.TOP, anchor="w", pady=(4, 0))

        # ====================================================================
        # RIGHT PANE: Settings, Actions, Progress & Results Treeview Table
        # ====================================================================
        right_frame = ttk.Frame(paned, padding=5)
        paned.add(right_frame, weight=6)

        # 1. Settings Box
        settings_box = ttk.LabelFrame(right_frame, text="Options & Configuration", padding=8)
        settings_box.pack(fill=tk.X, pady=(0, 6))

        # Row 1: Languages & PSM
        r1 = ttk.Frame(settings_box)
        r1.pack(fill=tk.X, pady=2)

        ttk.Label(r1, text="Source Lang:").pack(side=tk.LEFT)
        self.combo_src = ttk.Combobox(
            r1, textvariable=self.source_lang_var, values=list(LANGUAGES.keys()), state="readonly", width=15
        )
        self.combo_src.pack(side=tk.LEFT, padx=(3, 10))

        ttk.Label(r1, text="Target Lang:").pack(side=tk.LEFT)
        self.combo_tgt = ttk.Combobox(
            r1, textvariable=self.target_lang_var, values=list(LANGUAGES.keys()), state="readonly", width=15
        )
        self.combo_tgt.pack(side=tk.LEFT, padx=(3, 10))

        ttk.Label(r1, text="PSM:").pack(side=tk.LEFT)
        self.combo_psm = ttk.Combobox(r1, textvariable=self.psm_var, values=PSM_OPTIONS, state="readonly", width=25)
        self.combo_psm.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)

        # Row 2: Font selection & Output Format
        r2 = ttk.Frame(settings_box)
        r2.pack(fill=tk.X, pady=2)

        ttk.Label(r2, text="Render Font:").pack(side=tk.LEFT)
        self.font_lbl = ttk.Label(r2, text="Default Font", foreground="#2563eb", width=22, anchor="w")
        self.font_lbl.pack(side=tk.LEFT, padx=3)
        self._update_font_display_label()

        btn_font = ttk.Button(r2, text="Choose Font (TTF/OTF)...", command=self.on_choose_font)
        btn_font.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(r2, text="Output Format:").pack(side=tk.LEFT)
        combo_fmt = ttk.Combobox(
            r2, textvariable=self.format_var, values=["Keep original", "png", "jpg"], state="readonly", width=14
        )
        combo_fmt.pack(side=tk.LEFT, padx=3)

        # Row 3: Name Template & Helper buttons
        r3 = ttk.Frame(settings_box)
        r3.pack(fill=tk.X, pady=2)

        ttk.Label(r3, text="Name Template:").pack(side=tk.LEFT)
        ent_template = ttk.Entry(r3, textvariable=self.template_var, width=28)
        ent_template.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        # Template helper insertion pills
        ttk.Label(r3, text="Insert:", foreground="#64748b").pack(side=tk.LEFT, padx=(5, 2))
        for var_tag in ["{index:03d}", "{name}", "{t1}", "{t2}", "{o1}"]:
            btn_tag = ttk.Button(
                r3,
                text=var_tag,
                width=len(var_tag) + 1,
                command=lambda v=var_tag: self._insert_template_tag(v),
            )
            btn_tag.pack(side=tk.LEFT, padx=1)

        # Row 4: Output Folder
        r4 = ttk.Frame(settings_box)
        r4.pack(fill=tk.X, pady=2)

        ttk.Label(r4, text="Output Folder:").pack(side=tk.LEFT)
        self.ent_out_folder = ttk.Entry(r4, textvariable=self.output_folder_var)
        self.ent_out_folder.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        btn_out_browse = ttk.Button(r4, text="Browse...", command=self.on_browse_output_folder)
        btn_out_browse.pack(side=tk.LEFT)

        # 2. Action Controls & Progress Bar
        action_bar = ttk.Frame(right_frame)
        action_bar.pack(fill=tk.X, pady=(2, 6))

        self.btn_scan = ttk.Button(
            action_bar,
            text="🚀 Scan OCR + Translate",
            style="Primary.TButton",
            command=self.on_start_scan_and_translate,
        )
        self.btn_scan.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_preview = ttk.Button(action_bar, text="👁️ Preview Selected", command=self.on_preview_selected)
        self.btn_preview.pack(side=tk.LEFT, padx=4)

        self.btn_export = ttk.Button(
            action_bar,
            text="💾 Export New Images",
            style="Accent.TButton",
            command=self.on_start_export_images,
        )
        self.btn_export.pack(side=tk.LEFT, padx=4)

        self.btn_cancel = ttk.Button(action_bar, text="⏹️ Stop", command=self.on_stop_processing, state="disabled")
        self.btn_cancel.pack(side=tk.LEFT, padx=4)

        # Progress bar & label
        self.progress_bar = ttk.Progressbar(action_bar, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 5))

        self.progress_lbl = ttk.Label(action_bar, text="Idle", foreground="#64748b", width=14, anchor="e")
        self.progress_lbl.pack(side=tk.RIGHT)

        # 3. Results Table (Treeview)
        table_frame = ttk.LabelFrame(right_frame, text="Results & Translation Data (Double-click to edit)", padding=6)
        table_frame.pack(fill=tk.BOTH, expand=True)

        res_cols = ("orig_file", "region", "ocr_text", "translation", "new_name")
        self.res_tree = ttk.Treeview(table_frame, columns=res_cols, show="headings", selectmode="browse")

        self.res_tree.heading("orig_file", text="Original File")
        self.res_tree.heading("region", text="Region")
        self.res_tree.heading("ocr_text", text="OCR Text (Double-click to edit)")
        self.res_tree.heading("translation", text="Translation (Double-click to edit)")
        self.res_tree.heading("new_name", text="New Filename")

        self.res_tree.column("orig_file", width=140, anchor="w")
        self.res_tree.column("region", width=55, anchor="center")
        self.res_tree.column("ocr_text", width=180, anchor="w")
        self.res_tree.column("translation", width=190, anchor="w")
        self.res_tree.column("new_name", width=180, anchor="w")

        v_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.res_tree.yview)
        h_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.res_tree.xview)
        self.res_tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.res_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        # Inline Editing on double-click
        self.res_tree.bind("<Double-1>", self.on_tree_double_click)

        # Bottom Status Bar
        self.status_bar = ttk.Frame(self.root, padding="6 3")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_msg_lbl = ttk.Label(self.status_bar, text="Ready", font=("Segoe UI", 8))
        self.status_msg_lbl.pack(side=tk.LEFT)

        self.status_tess_lbl = ttk.Label(
            self.status_bar,
            text=f"Tesseract: {'Found' if detected_tesseract else 'Not Configured'}",
            foreground="#16a34a" if detected_tesseract else "#dc2626",
            font=("Segoe UI", 8, "bold"),
        )
        self.status_tess_lbl.pack(side=tk.RIGHT, padx=10)

    def _insert_template_tag(self, tag: str):
        curr = self.template_var.get()
        self.template_var.set(curr + tag)

    def _update_font_display_label(self):
        fpath = self.font_path_var.get()
        if fpath and os.path.exists(fpath):
            name = os.path.basename(fpath)
            self.font_lbl.config(text=name, foreground="#2563eb")
        else:
            self.font_lbl.config(text="System Default", foreground="#64748b")

    def _update_status(self, msg: str):
        self.status_msg_lbl.config(text=msg)

    # ========================================================================
    # FOLDER & SAMPLE IMAGE HANDLING
    # ========================================================================
    def on_choose_folder(self):
        folder = filedialog.askdirectory(title="Choose Image Folder")
        if not folder:
            return

        self.folder_path = os.path.abspath(folder)
        self.folder_disp_lbl.config(text=self.folder_path)

        # Find all supported images and sort in natural order
        files = []
        for entry in os.listdir(self.folder_path):
            full_p = os.path.join(self.folder_path, entry)
            if os.path.isfile(full_p) and entry.lower().endswith(SUPPORTED_EXTENSIONS):
                files.append(entry)

        files.sort(key=natural_sort_key)
        self.image_files = files

        if not self.image_files:
            messagebox.showwarning(
                "No Images Found",
                f"No supported images ({', '.join(SUPPORTED_EXTENSIONS)}) found in:\n{self.folder_path}",
            )
            return

        # Set default output folder
        default_out = os.path.join(self.folder_path, "output")
        self.output_folder_var.set(default_out)

        # Update Sample Combobox
        self.sample_combo["values"] = self.image_files
        self.current_sample_idx = 0
        self.sample_combo.current(0)

        # Load sample image
        self.load_sample_image(self.image_files[0])
        self._update_status(f"Loaded {len(self.image_files)} image(s) from {self.folder_path}")

    def load_sample_image(self, filename: str):
        img_path = os.path.join(self.folder_path, filename)
        if not os.path.isfile(img_path):
            return

        try:
            self.sample_image = Image.open(img_path).convert("RGB")
            orig_w, orig_h = self.sample_image.size
            self.img_info_lbl.config(
                text=f"{orig_w}x{orig_h} px | {self.current_sample_idx + 1}/{len(self.image_files)}"
            )
            self.redraw_canvas()
            self._refresh_region_tree()
        except Exception as e:
            messagebox.showerror("Error Opening Image", f"Failed to load image:\n{e}")

    def on_sample_combo_selected(self, event=None):
        idx = self.sample_combo.current()
        if idx >= 0 and idx < len(self.image_files):
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
    # CANVAS & REGION DRAWING LOGIC
    # ========================================================================
    def on_canvas_configure(self, event=None):
        if self.sample_image:
            self.redraw_canvas()

    def redraw_canvas(self):
        """Redraws the sample image scaled to fit canvas, along with all regions."""
        self.canvas.delete("all")
        if not self.sample_image:
            self.canvas.create_text(
                self.canvas.winfo_width() // 2,
                self.canvas.winfo_height() // 2,
                text="Please choose a folder to display the sample image",
                fill="#94a3b8",
                font=("Segoe UI", 12),
            )
            return

        canvas_w = max(10, self.canvas.winfo_width())
        canvas_h = max(10, self.canvas.winfo_height())
        orig_w, orig_h = self.sample_image.size

        # Compute scaling factor to fit within canvas
        scale = min(canvas_w / orig_w, canvas_h / orig_h)
        self.sample_scale = scale

        disp_w = max(1, int(orig_w * scale))
        disp_h = max(1, int(orig_h * scale))

        self.sample_offset_x = (canvas_w - disp_w) // 2
        self.sample_offset_y = (canvas_h - disp_h) // 2

        # Resize image for display
        resized = self.sample_image.resize((disp_w, disp_h), Image.Resampling.BILINEAR)
        self.sample_photo = ImageTk.PhotoImage(resized)

        self.canvas.create_image(
            self.sample_offset_x,
            self.sample_offset_y,
            anchor="nw",
            image=self.sample_photo,
        )

        # Draw all saved regions
        for idx, reg in enumerate(self.regions):
            self._draw_region_on_canvas(idx, reg)

    def _draw_region_on_canvas(self, idx: int, reg: dict):
        orig_w, orig_h = self.sample_image.size
        # Relative to screen coordinates
        cx1 = self.sample_offset_x + reg["rx1"] * orig_w * self.sample_scale
        cy1 = self.sample_offset_y + reg["ry1"] * orig_h * self.sample_scale
        cx2 = self.sample_offset_x + reg["rx2"] * orig_w * self.sample_scale
        cy2 = self.sample_offset_y + reg["ry2"] * orig_h * self.sample_scale

        is_selected = idx == self.selected_region_idx
        border_color = "#eab308" if is_selected else "#06b6d4"  # Gold if selected, cyan otherwise
        width = 3 if is_selected else 2

        # Draw rectangle
        self.canvas.create_rectangle(
            cx1, cy1, cx2, cy2, outline=border_color, width=width, tags=f"region_{idx}"
        )

        # Draw badge with region number
        badge_w = 20
        badge_h = 18
        bx1 = cx1
        by1 = max(self.sample_offset_y, cy1 - badge_h)
        bx2 = bx1 + badge_w
        by2 = by1 + badge_h

        self.canvas.create_rectangle(
            bx1, by1, bx2, by2, fill=border_color, outline="", tags=f"region_{idx}"
        )
        self.canvas.create_text(
            (bx1 + bx2) / 2,
            (by1 + by2) / 2,
            text=f"#{idx + 1}",
            fill="#0f172a",
            font=("Segoe UI", 9, "bold"),
            tags=f"region_{idx}",
        )

    def on_canvas_press(self, event):
        if not self.sample_image:
            return

        # Check if user clicked on an existing region
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

        # Start drawing a new region
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        if self.active_rect_id:
            self.canvas.delete(self.active_rect_id)
        self.active_rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#f59e0b", width=2, dash=(4, 4)
        )

    def on_canvas_drag(self, event):
        if self.active_rect_id:
            self.canvas.coords(self.active_rect_id, self.drag_start_x, self.drag_start_y, event.x, event.y)

    def on_canvas_release(self, event):
        if not self.active_rect_id or not self.sample_image:
            return

        self.canvas.delete(self.active_rect_id)
        self.active_rect_id = None

        # Check drag distance
        dx = abs(event.x - self.drag_start_x)
        dy = abs(event.y - self.drag_start_y)
        if dx < 6 or dy < 6:
            return  # Ignored accidental small click

        orig_w, orig_h = self.sample_image.size
        # Canvas to image coords
        sx1 = min(self.drag_start_x, event.x)
        sy1 = min(self.drag_start_y, event.y)
        sx2 = max(self.drag_start_x, event.x)
        sy2 = max(self.drag_start_y, event.y)

        # Clamp to image area
        ix1 = max(0.0, min(float(orig_w), (sx1 - self.sample_offset_x) / self.sample_scale))
        iy1 = max(0.0, min(float(orig_h), (sy1 - self.sample_offset_y) / self.sample_scale))
        ix2 = max(0.0, min(float(orig_w), (sx2 - self.sample_offset_x) / self.sample_scale))
        iy2 = max(0.0, min(float(orig_h), (sy2 - self.sample_offset_y) / self.sample_scale))

        if ix2 - ix1 < 4 or iy2 - iy1 < 4:
            return

        # Convert to relative ratios [0.0 - 1.0]
        rx1 = round(ix1 / orig_w, 4)
        ry1 = round(iy1 / orig_h, 4)
        rx2 = round(ix2 / orig_w, 4)
        ry2 = round(iy2 / orig_h, 4)

        new_reg = {"rx1": rx1, "ry1": ry1, "rx2": rx2, "ry2": ry2}
        self.regions.append(new_reg)
        self.selected_region_idx = len(self.regions) - 1

        self.redraw_canvas()
        self._refresh_region_tree()
        self._populate_manual_edit_entries(new_reg)

    def _select_region(self, idx: int):
        self.selected_region_idx = idx
        self.redraw_canvas()
        # Highlight in treeview
        if 0 <= idx < len(self.regions):
            items = self.reg_tree.get_children()
            if idx < len(items):
                self.reg_tree.selection_set(items[idx])
                self.reg_tree.see(items[idx])
            self._populate_manual_edit_entries(self.regions[idx])

    def _refresh_region_tree(self):
        """Updates the region treeview list."""
        for item in self.reg_tree.get_children():
            self.reg_tree.delete(item)

        orig_w = self.sample_image.size[0] if self.sample_image else 1
        orig_h = self.sample_image.size[1] if self.sample_image else 1

        for idx, reg in enumerate(self.regions):
            px1 = int(round(reg["rx1"] * orig_w))
            py1 = int(round(reg["ry1"] * orig_h))
            px2 = int(round(reg["rx2"] * orig_w))
            py2 = int(round(reg["ry2"] * orig_h))
            px_str = f"({px1}, {py1}) to ({px2}, {py2})"
            ratio_str = f"[{reg['rx1']:.3f}, {reg['ry1']:.3f}, {reg['rx2']:.3f}, {reg['ry2']:.3f}]"

            iid = self.reg_tree.insert("", "end", values=(f"#{idx+1}", px_str, ratio_str))
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
        x1 = int(round(reg["rx1"] * orig_w))
        y1 = int(round(reg["ry1"] * orig_h))
        x2 = int(round(reg["rx2"] * orig_w))
        y2 = int(round(reg["ry2"] * orig_h))

        for ent, val in [(self.ent_x1, x1), (self.ent_y1, y1), (self.ent_x2, x2), (self.ent_y2, y2)]:
            ent.delete(0, tk.END)
            ent.insert(0, str(val))

    def on_update_region_coords(self):
        """Applies manual pixel coordinates to the currently selected region."""
        if self.selected_region_idx < 0 or self.selected_region_idx >= len(self.regions):
            messagebox.showinfo("Select Region", "Please select a region to edit.")
            return
        if not self.sample_image:
            return

        try:
            x1 = int(self.ent_x1.get().strip())
            y1 = int(self.ent_y1.get().strip())
            x2 = int(self.ent_x2.get().strip())
            y2 = int(self.ent_y2.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter integer pixel numbers for X1, Y1, X2, Y2.")
            return

        orig_w, orig_h = self.sample_image.size
        nx1 = max(0, min(orig_w, min(x1, x2)))
        ny1 = max(0, min(orig_h, min(y1, y2)))
        nx2 = max(0, min(orig_w, max(x1, x2)))
        ny2 = max(0, min(orig_h, max(y1, y2)))

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

    # ========================================================================
    # CONFIGURATION SAVE & LOAD (JSON)
    # ========================================================================
    def on_save_config(self):
        fpath = filedialog.asksaveasfilename(
            title="Save Configuration",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
        )
        if not fpath:
            return

        cfg = {
            "regions": self.regions,
            "source_lang": self.source_lang_var.get(),
            "target_lang": self.target_lang_var.get(),
            "psm": self.psm_var.get(),
            "name_template": self.template_var.get(),
            "output_format": self.format_var.get(),
            "font_path": self.font_path_var.get(),
            "tesseract_cmd": self.tesseract_cmd_var.get(),
        }

        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Saved", f"Configuration successfully saved to:\n{fpath}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save configuration:\n{e}")

    def on_load_config(self):
        fpath = filedialog.askopenfilename(
            title="Load Configuration",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if not fpath:
            return

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            if "regions" in cfg and isinstance(cfg["regions"], list):
                self.regions = cfg["regions"]
                self.selected_region_idx = 0 if self.regions else -1

            if "source_lang" in cfg and cfg["source_lang"] in LANGUAGES:
                self.source_lang_var.set(cfg["source_lang"])

            if "target_lang" in cfg and cfg["target_lang"] in LANGUAGES:
                self.target_lang_var.set(cfg["target_lang"])

            if "psm" in cfg:
                self.psm_var.set(cfg["psm"])

            if "name_template" in cfg:
                self.template_var.set(cfg["name_template"])

            if "output_format" in cfg:
                self.format_var.set(cfg["output_format"])

            if "font_path" in cfg and os.path.exists(cfg["font_path"]):
                self.font_path_var.set(cfg["font_path"])
                self._update_font_display_label()

            if "tesseract_cmd" in cfg and cfg["tesseract_cmd"]:
                self.tesseract_cmd_var.set(cfg["tesseract_cmd"])
                pytesseract.pytesseract.tesseract_cmd = cfg["tesseract_cmd"]

            self.redraw_canvas()
            self._refresh_region_tree()
            messagebox.showinfo("Configuration Loaded", f"Successfully loaded configuration from:\n{fpath}")
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load configuration:\n{e}")

    def on_choose_font(self):
        fpath = filedialog.askopenfilename(
            title="Choose TTF/OTF Font",
            filetypes=[("Font Files", "*.ttf;*.otf;*.ttc"), ("All Files", "*.*")],
        )
        if fpath:
            self.font_path_var.set(fpath)
            self._update_font_display_label()

    def on_browse_output_folder(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_folder_var.set(os.path.abspath(folder))

    def on_tesseract_settings(self):
        """Dialog to configure and test the Tesseract-OCR binary path."""
        win = tk.Toplevel(self.root)
        win.title("Tesseract-OCR Settings")
        win.geometry("540x210")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        ttk.Label(
            win,
            text="Specify the path to the Tesseract executable:",
            style="Header.TLabel",
        ).pack(anchor="w", padx=15, pady=(15, 5))

        f_entry = ttk.Frame(win)
        f_entry.pack(fill=tk.X, padx=15, pady=5)

        tess_entry = ttk.Entry(f_entry, textvariable=self.tesseract_cmd_var)
        tess_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        def browse_tess():
            curr_os = platform.system()
            patterns = [("Executable", "*.exe" if curr_os == "Windows" else "*")]
            p = filedialog.askopenfilename(title="Select Tesseract Executable", filetypes=patterns)
            if p:
                self.tesseract_cmd_var.set(p)

        ttk.Button(f_entry, text="Browse...", command=browse_tess).pack(side=tk.RIGHT)

        test_result_lbl = ttk.Label(win, text="", font=("Segoe UI", 9))
        test_result_lbl.pack(anchor="w", padx=15, pady=5)

        def test_tess():
            cmd = self.tesseract_cmd_var.get().strip()
            pytesseract.pytesseract.tesseract_cmd = cmd
            try:
                ver = pytesseract.get_tesseract_version()
                test_result_lbl.config(
                    text=f"✅ Tesseract version {ver} is working properly!",
                    foreground="#16a34a",
                )
                self.status_tess_lbl.config(text="Tesseract: Working", foreground="#16a34a")
            except Exception as e:
                test_result_lbl.config(
                    text=f"❌ Failed: {str(e)[:70]}",
                    foreground="#dc2626",
                )
                self.status_tess_lbl.config(text="Tesseract: Error", foreground="#dc2626")

        btn_bar = ttk.Frame(win)
        btn_bar.pack(fill=tk.X, padx=15, pady=10)

        ttk.Button(btn_bar, text="Test Connection", command=test_tess).pack(side=tk.LEFT)
        ttk.Button(btn_bar, text="Save & Close", command=win.destroy).pack(side=tk.RIGHT)

    # ========================================================================
    # OCR & TRANSLATION ENGINE (BACKGROUND THREAD)
    # ========================================================================
    def on_start_scan_and_translate(self):
        if not self.image_files:
            messagebox.showwarning("No Images", "Please open an image folder first.")
            return

        if not self.regions:
            messagebox.showwarning(
                "No Regions",
                "Please draw at least one text region box on the sample image first.",
            )
            return

        # Check Tesseract path
        tess_cmd = self.tesseract_cmd_var.get().strip()
        if tess_cmd:
            pytesseract.pytesseract.tesseract_cmd = tess_cmd

        try:
            pytesseract.get_tesseract_version()
        except Exception:
            resp = messagebox.askyesno(
                "Tesseract Not Found",
                "Tesseract-OCR was not found or failed to execute.\n"
                "Would you like to configure the Tesseract path now?",
            )
            if resp:
                self.on_tesseract_settings()
            return

        self.is_processing = True
        self.stop_requested = False
        self._toggle_ui_state(False)

        # Clear existing table data
        for item in self.res_tree.get_children():
            self.res_tree.delete(item)
        self.results_data.clear()

        # Start thread
        thread = threading.Thread(target=self._scan_and_translate_worker, daemon=True)
        thread.start()

    def _toggle_ui_state(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.btn_scan.config(state=state)
        self.btn_export.config(state=state)
        self.btn_preview.config(state=state)
        self.btn_cancel.config(state="normal" if not enabled else "disabled")

    def on_stop_processing(self):
        if self.is_processing:
            self.stop_requested = True
            self._update_status("Stopping process... Please wait.")

    def _scan_and_translate_worker(self):
        total_images = len(self.image_files)
        src_lang_name = self.source_lang_var.get()
        tgt_lang_name = self.target_lang_var.get()

        ocr_lang = LANGUAGES[src_lang_name]["ocr"]
        trans_src = LANGUAGES[src_lang_name]["trans"]
        trans_tgt = LANGUAGES[tgt_lang_name]["trans"]

        # Parse PSM parameter
        psm_str = self.psm_var.get()
        psm_match = re.match(r"^(\d+)", psm_str)
        psm_val = psm_match.group(1) if psm_match else "6"
        tess_config = f"--psm {psm_val}"

        # Initialize GoogleTranslator instance
        translator = GoogleTranslator(source=trans_src, target=trans_tgt)

        for img_idx, filename in enumerate(self.image_files):
            if self.stop_requested:
                break

            pct = int(((img_idx + 1) / total_images) * 100)
            self.root.after(0, self._update_progress, pct, f"{img_idx + 1}/{total_images}")
            self.root.after(0, self._update_status, f"Scanning ({img_idx + 1}/{total_images}): {filename}...")

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

            # Process each region
            for r_idx, reg in enumerate(self.regions):
                if self.stop_requested:
                    break

                # Compute pixel coordinates
                x1 = int(round(reg["rx1"] * orig_w))
                y1 = int(round(reg["ry1"] * orig_h))
                x2 = int(round(reg["rx2"] * orig_w))
                y2 = int(round(reg["ry2"] * orig_h))

                # Clamp coords
                x1 = max(0, min(orig_w - 1, x1))
                y1 = max(0, min(orig_h - 1, y1))
                x2 = max(x1 + 1, min(orig_w, x2))
                y2 = max(y1 + 1, min(orig_h, y2))

                crop_img = img.crop((x1, y1, x2, y2))

                # OCR Preprocessing: Grayscale -> Autocontrast -> Upscale if short
                try:
                    gray = crop_img.convert("L")
                    enhanced = ImageOps.autocontrast(gray)
                    if crop_img.height < 60:
                        factor = max(2.0, 60.0 / max(1, crop_img.height))
                        nw = int(round(crop_img.width * factor))
                        nh = int(round(crop_img.height * factor))
                        enhanced = enhanced.resize((nw, nh), Image.Resampling.LANCZOS)

                    ocr_raw = pytesseract.image_to_string(enhanced, lang=ocr_lang, config=tess_config)
                    ocr_text = ocr_raw.strip()
                except Exception as e:
                    ocr_text = f"[OCR Error: {str(e)[:30]}]"

                image_ocr_texts.append(ocr_text)

                # Translation with caching & error handling
                if not ocr_text or ocr_text.startswith("[OCR Error"):
                    translated_text = ""
                elif ocr_text in self.translation_cache:
                    translated_text = self.translation_cache[ocr_text]
                else:
                    try:
                        translated_text = translator.translate(ocr_text)
                        if translated_text:
                            self.translation_cache[ocr_text] = translated_text
                        else:
                            translated_text = ocr_text
                    except Exception as e:
                        # Graceful fallback: retry once or save error text
                        time.sleep(0.4)
                        try:
                            translated_text = translator.translate(ocr_text)
                            self.translation_cache[ocr_text] = translated_text
                        except Exception as e2:
                            print(f"Translation error on '{ocr_text}': {e2}", file=sys.stderr)
                            translated_text = ocr_text  # Fallback to original text

                image_trans_texts.append(translated_text)

            # Compute new filename
            new_file_stem = compute_filename(
                self.template_var.get(),
                img_idx + 1,
                file_stem,
                image_ocr_texts,
                image_trans_texts,
            )
            orig_ext = os.path.splitext(filename)[1].lstrip(".")
            chosen_fmt = self.format_var.get().lower()
            if "png" in chosen_fmt:
                final_ext = "png"
            elif "jpg" in chosen_fmt:
                final_ext = "jpg"
            else:
                final_ext = orig_ext
            new_full_name = f"{new_file_stem}.{final_ext}"

            # Append to results data
            for r_idx in range(len(self.regions)):
                row_data = {
                    "orig_file": filename,
                    "region": f"#{r_idx + 1}",
                    "region_idx": r_idx,
                    "img_idx": img_idx,
                    "ocr_text": image_ocr_texts[r_idx],
                    "translation": image_trans_texts[r_idx],
                    "new_name": new_full_name,
                }
                self.results_data.append(row_data)
                self.root.after(0, self._insert_tree_row, row_data)

        # Worker finished
        self.root.after(0, self._on_scan_finished)

    def _insert_tree_row(self, row: dict):
        self.res_tree.insert(
            "",
            "end",
            values=(
                row["orig_file"],
                row["region"],
                row["ocr_text"],
                row["translation"],
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
        status_txt = "Stopped by user." if self.stop_requested else "Scan & Translation complete!"
        self.progress_lbl.config(text="Complete" if not self.stop_requested else "Stopped")
        self._update_status(status_txt)
        messagebox.showinfo("Scan Completed", f"{status_txt}\nProcessed {len(self.image_files)} image(s).")

    # ========================================================================
    # INLINE EDITING IN TREEVIEW TABLE
    # ========================================================================
    def on_tree_double_click(self, event):
        """Allows direct inline editing of OCR Text and Translation cells."""
        region = self.res_tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        column = self.res_tree.identify_column(event.x)
        item = self.res_tree.identify_row(event.y)
        if not item:
            return

        col_idx = int(column.replace("#", "")) - 1
        # Only allow editing OCR Text (col 2) and Translation (col 3)
        if col_idx not in (2, 3):
            return

        x, y, w, h = self.res_tree.bbox(item, column)
        current_values = list(self.res_tree.item(item, "values"))
        current_text = current_values[col_idx]

        # Create inline floating Entry
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

            # Update results_data and recalculate new filename
            item_idx = self.res_tree.index(item)
            if 0 <= item_idx < len(self.results_data):
                if col_idx == 2:
                    self.results_data[item_idx]["ocr_text"] = new_text
                elif col_idx == 3:
                    self.results_data[item_idx]["translation"] = new_text

                # Update translation cache if translation changed
                ocr_k = self.results_data[item_idx]["ocr_text"]
                if col_idx == 3 and ocr_k:
                    self.translation_cache[ocr_k] = new_text

                # Recompute filenames for this image
                target_filename = self.results_data[item_idx]["orig_file"]
                img_idx = self.results_data[item_idx]["img_idx"]
                self._recalculate_filenames_for_image(target_filename, img_idx)

        edit_entry.bind("<Return>", commit_edit)
        edit_entry.bind("<FocusOut>", commit_edit)
        edit_entry.bind("<Escape>", lambda e: edit_entry.destroy())

    def _recalculate_filenames_for_image(self, filename: str, img_idx: int):
        """Recalculates new name for all rows of a given image and updates the table."""
        orig_stem = os.path.splitext(filename)[0]
        # Gather all OCR and translations for this image
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
        if "png" in chosen_fmt:
            final_ext = "png"
        elif "jpg" in chosen_fmt:
            final_ext = "jpg"
        else:
            final_ext = orig_ext
        updated_name = f"{new_stem}.{final_ext}"

        tree_items = self.res_tree.get_children()
        for r_idx in row_indices:
            self.results_data[r_idx]["new_name"] = updated_name
            if r_idx < len(tree_items):
                vals = list(self.res_tree.item(tree_items[r_idx], "values"))
                vals[4] = updated_name
                self.res_tree.item(tree_items[r_idx], values=vals)

    def _on_template_or_format_changed(self, *args):
        """Live updates all rows in results table when template or format changes."""
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
    # PREVIEW WINDOW
    # ========================================================================
    def on_preview_selected(self):
        """Renders and previews the output image for the selected row."""
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

        # Open Preview Modal Window
        prev_win = tk.Toplevel(self.root)
        prev_win.title(f"Preview Output: {target_filename}")
        prev_win.geometry("900x700")

        lbl_hdr = ttk.Label(
            prev_win,
            text=f"Preview of rendered output image: {target_filename}",
            style="Header.TLabel",
        )
        lbl_hdr.pack(anchor="w", padx=10, pady=8)

        p_canvas = tk.Canvas(prev_win, bg="#0f172a", highlightthickness=0)
        p_canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Scale image to fit preview canvas
        def fit_preview(evt=None):
            cw = max(50, p_canvas.winfo_width())
            ch = max(50, p_canvas.winfo_height())
            iw, ih = rendered_img.size
            sc = min(cw / iw, ch / ih, 1.0)
            dw = max(1, int(iw * sc))
            dh = max(1, int(ih * sc))

            resized = rendered_img.resize((dw, dh), Image.Resampling.BILINEAR)
            prev_win._photo = ImageTk.PhotoImage(resized)
            p_canvas.delete("all")
            p_canvas.create_image(cw // 2, ch // 2, anchor="center", image=prev_win._photo)

        p_canvas.bind("<Configure>", fit_preview)
        fit_preview()

    def _render_output_image(self, filename: str) -> Image.Image:
        """
        Creates the output image:
        - Clones the original image.
        - Paints over old text regions with the median border color.
        - Draws the translated text with word wrapping and auto-font reduction.
        """
        img_path = os.path.join(self.folder_path, filename)
        if not os.path.isfile(img_path):
            return None

        try:
            out_img = Image.open(img_path).convert("RGB")
        except Exception:
            return None

        draw = ImageDraw.Draw(out_img)
        orig_w, orig_h = out_img.size

        # Find translated texts for this file from results_data (or fallback to empty)
        file_translations = {}
        for row in self.results_data:
            if row["orig_file"] == filename:
                file_translations[row["region_idx"]] = row["translation"]

        font_path = self.font_path_var.get()

        for idx, reg in enumerate(self.regions):
            x1 = int(round(reg["rx1"] * orig_w))
            y1 = int(round(reg["ry1"] * orig_h))
            x2 = int(round(reg["rx2"] * orig_w))
            y2 = int(round(reg["ry2"] * orig_h))

            # Clamp coordinates
            x1 = max(0, min(orig_w - 1, x1))
            y1 = max(0, min(orig_h - 1, y1))
            x2 = max(x1 + 1, min(orig_w, x2))
            y2 = max(y1 + 1, min(orig_h, y2))

            box = (x1, y1, x2, y2)

            # 1. Compute median color of border pixels
            median_color = get_box_median_color(out_img, box)

            # 2. Paint over the old text region
            draw.rectangle(box, fill=median_color)

            # 3. Draw translated text
            translated_text = file_translations.get(idx, f"Region #{idx+1}")
            fit_and_draw_text(
                draw,
                translated_text,
                box,
                font_path=font_path,
                padding=4,
                bg_color=median_color,
            )

        return out_img

    # ========================================================================
    # EXPORT NEW IMAGES (BACKGROUND THREAD)
    # ========================================================================
    def on_start_export_images(self):
        if not self.image_files:
            messagebox.showwarning("No Images", "Please open an image folder first.")
            return

        if not self.regions:
            messagebox.showwarning("No Regions", "Please define at least one text region first.")
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

        # Build map of new filenames from results_data if scanned
        filename_map = {}
        for row in self.results_data:
            filename_map[row["orig_file"]] = row["new_name"]

        chosen_format = self.format_var.get().lower()

        for idx, filename in enumerate(self.image_files):
            if self.stop_requested:
                break

            pct = int(((idx + 1) / total_images) * 100)
            self.root.after(0, self._update_progress, pct, f"{idx + 1}/{total_images}")
            self.root.after(0, self._update_status, f"Exporting ({idx + 1}/{total_images}): {filename}...")

            rendered_img = self._render_output_image(filename)
            if not rendered_img:
                continue

            # Determine output filename
            orig_stem = os.path.splitext(filename)[0]
            orig_ext = os.path.splitext(filename)[1].lstrip(".")

            if "png" in chosen_format:
                save_ext = "png"
            elif "jpg" in chosen_format:
                save_ext = "jpg"
            else:
                save_ext = orig_ext

            if filename in filename_map:
                base_stem = os.path.splitext(filename_map[filename])[0]
            else:
                base_stem = compute_filename(self.template_var.get(), idx + 1, orig_stem, [], [])

            # Generate collision-free path
            final_path = get_unique_output_path(out_folder, base_stem, save_ext, used_filenames)

            # Save image
            try:
                if save_ext in ("jpg", "jpeg"):
                    rendered_img.save(final_path, format="JPEG", quality=95)
                else:
                    rendered_img.save(final_path, format="PNG")
            except Exception as e:
                print(f"Error saving image to {final_path}: {e}", file=sys.stderr)

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
                f"Successfully exported images to:\n{out_folder}\n\nWould you like to open the output folder now?",
            )
            if res:
                self._open_in_file_manager(out_folder)

    def _open_in_file_manager(self, folder: str):
        """Cross-platform folder opening."""
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
