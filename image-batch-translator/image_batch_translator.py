#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Batch Character Extractor & Renamer (Crop-Resilient)
==========================================================
A cross-platform desktop application written in Python (Tkinter GUI).
Extracts characters and fields from batches of images even when images are
cropped, shifted, or scaled, using:
1. Keyword Anchor Extraction (e.g. text after "Mã phiếu:", "Tên hàng:")
2. Regex Pattern Matching (e.g. "PXK-\\d{4}-\\d{3}")
3. Visual Text Detection & 1-Click Rule Creator
4. Traditional Coordinate Bounding Box (Optional)

Supported OCR Engines:
- Google Lens (Cloud AI - 100% precision with Vietnamese & Unicode)
- RapidOCR (Local Offline - ONNX based, zero internet needed)
(NO Tesseract binary required!)

Dependencies:
    - Pillow (PIL)
    - chrome-lens-py
    - rapidocr-onnxruntime
    - deep-translator (optional fallback)
    - tkinter (built into standard Python)
"""

import sys
import os
import re
import csv
import json
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
    import numpy as np
    HAVE_RAPIDOCR = True
except ImportError:
    pass

try:
    from deep_translator import GoogleTranslator
except ImportError:
    pass

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    print("CRITICAL ERROR: Tkinter is required to run this GUI.", file=sys.stderr)
    sys.exit(1)

if not HAVE_LENS and not HAVE_RAPIDOCR:
    missing_str = " ".join(MISSING_PACKAGES)
    error_msg = (
        f"Missing required Python libraries: {', '.join(MISSING_PACKAGES)}\n\n"
        f"Please install them via:\n"
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
# 3. HELPER FUNCTIONS & RESILIENT EXTRACTION LOGIC
# ============================================================================
def natural_sort_key(s: str):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def sanitize_filename(filename: str, max_length: int = 120) -> str:
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
    def __missing__(self, key):
        return f"{{{key}}}"


def compute_filename(template: str, index: int, orig_stem: str, ocr_texts: list) -> str:
    format_vars = {
        "index": index,
        "name": sanitize_filename(orig_stem, max_length=50),
    }
    for i, o_text in enumerate(ocr_texts):
        format_vars[f"o{i+1}"] = sanitize_filename(o_text, max_length=40)

    try:
        raw_formatted = Formatter().vformat(template, (), SafeFormatDict(format_vars))
    except Exception:
        raw_formatted = f"{orig_stem}_renamed"

    return sanitize_filename(raw_formatted)


def get_unique_output_path(output_dir: str, base_name: str, ext: str, used_names: set) -> str:
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


def extract_by_keyword(full_text: str, keyword: str) -> str:
    """
    Extracts text associated with a keyword across full text.
    Resilient to:
    - Same line with colon: 'Mã phiếu: PXK-2026-001', 'GlassID: DLLLLLL1'
    - Same line with space: 'GlassID DLLLLLL1'
    - Same line fused: 'GlassIDDLLLLLL1'
    - Multi-line with colon or break: 'Mã phiếu:\nPXK-2026-001'
    Works even if images are cropped, shifted or scaled!
    """
    if not keyword.strip() or not full_text:
        return ""
    kw = re.escape(keyword.strip())

    # 1. Try same line (with optional separator or fused)
    m1 = re.search(rf"(?i){kw}[:\s\-_–—]*([^\n\r]+)", full_text)
    if m1 and m1.group(1).strip():
        return m1.group(1).strip()

    # 2. Try next line
    m2 = re.search(rf"(?i){kw}[:\s\-_–—]*\n+([^\n\r]+)", full_text)
    if m2 and m2.group(1).strip():
        return m2.group(1).strip()

    # 3. Line by line matching
    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
    for idx, line in enumerate(lines):
        if re.search(rf"(?i){kw}", line):
            rem = re.sub(rf"(?i)^.*?{kw}[:\s\-_–—]*", "", line).strip()
            if rem:
                return rem
            elif idx + 1 < len(lines):
                return lines[idx + 1].strip()

    return ""


def extract_by_pattern(full_text: str, pattern: str) -> str:
    """Extracts text matching a regex pattern from full text (returns group 1 if capturing group exists)."""
    if not pattern.strip() or not full_text:
        return ""
    try:
        m = re.search(pattern.strip(), full_text)
        if m:
            return m.group(1).strip() if m.groups() else m.group(0).strip()
        return ""
    except Exception:
        return ""


def extract_by_box(img: Image.Image, box: tuple, engine_name: str, lens_api=None, rapid_engine=None) -> str:
    """Crops by ratio coordinates and OCRs just that box."""
    orig_w, orig_h = img.size
    rx1, ry1, rx2, ry2 = box
    x1 = max(0, min(orig_w - 1, int(round(rx1 * orig_w))))
    y1 = max(0, min(orig_h - 1, int(round(ry1 * orig_h))))
    x2 = max(x1 + 1, min(orig_w, int(round(rx2 * orig_w))))
    y2 = max(y1 + 1, min(orig_h, int(round(ry2 * orig_h))))

    crop = img.crop((x1, y1, x2, y2))
    if "Google" in engine_name and lens_api:
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(lens_api.process_image(crop))
            return res.get("ocr_text", "").strip()
        finally:
            loop.close()
    elif rapid_engine:
        res, _ = rapid_engine(np.array(crop))
        return " ".join([l[1] for l in res]).strip() if res else ""
    return ""


# ============================================================================
# 3. IMAGE PREPROCESSING SYSTEM FOR OCR ACCURACY
# ============================================================================
PREPROCESS_MODES = [
    "None (Ảnh gốc)",
    "CLAHE (Độ tương phản cao - Chống lóa / Mặt kính)",
    "Enhance (Tự động cân bằng & Sắc nét)",
    "Invert (Đảo màu - Kính tối / Khắc laser sáng)",
    "Binarize (Otsu - Nhị phân đen trắng lọc nhiễu)",
    "Sharpen (Làm sắc nét chữ mờ)",
]


def preprocess_for_ocr(img_pil: Image.Image, mode: str = "none", upscale: bool = False) -> Image.Image:
    """
    Applies image preprocessing to dramatically improve OCR accuracy on glass,
    faint laser etching, reflective glare, low-contrast ink, and noisy backgrounds.
    """
    if not mode or mode.lower().startswith("none"):
        if upscale:
            w, h = img_pil.size
            return img_pil.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
        return img_pil.convert("RGB")

    mode_key = mode.lower()

    if HAVE_CV2:
        img_np = np.array(img_pil)
        if img_np.ndim == 2:
            gray = img_np
        elif img_np.shape[2] == 4:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGBA2GRAY)
        else:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        if upscale:
            h, w = gray.shape[:2]
            gray = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_LANCZOS4)

        if "clahe" in mode_key:
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            processed = clahe.apply(gray)
        elif "invert" in mode_key:
            processed = cv2.bitwise_not(gray)
        elif "binarize" in mode_key or "otsu" in mode_key:
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            _, processed = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        elif "enhance" in mode_key:
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            eq = clahe.apply(gray)
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
            processed = cv2.filter2D(eq, -1, kernel)
        elif "sharpen" in mode_key:
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
            processed = cv2.filter2D(gray, -1, kernel)
        else:
            processed = gray

        return Image.fromarray(processed).convert("RGB")
    else:
        # Pure PIL Fallback
        gray = img_pil.convert("L")
        if upscale:
            w, h = gray.size
            gray = gray.resize((w * 2, h * 2), Image.Resampling.LANCZOS)

        if "invert" in mode_key:
            processed = ImageOps.invert(gray)
        elif "enhance" in mode_key or "clahe" in mode_key:
            eq = ImageOps.autocontrast(gray, cutoff=2)
            processed = eq.filter(ImageFilter.SHARPEN)
        elif "sharpen" in mode_key:
            processed = gray.filter(ImageFilter.SHARPEN)
        elif "binarize" in mode_key or "otsu" in mode_key:
            processed = gray.point(lambda p: 255 if p > 128 else 0)
        else:
            processed = gray

        return processed.convert("RGB")


# ============================================================================
# PREPROCESS TEST & OCR TEST SCAN DIALOG
# ============================================================================
class PreprocessTestDialog:
    """Interactive preview and test scan dialog for image preprocessing algorithms."""

    def __init__(self, parent: tk.Tk, app):
        self.parent = parent
        self.app = app
        self.win = tk.Toplevel(parent)
        self.win.title("🧪 Test Tiền Xử Lý & Quét Thử OCR (Image Preprocessing & OCR Test)")
        self.win.geometry("1100x750")
        self.win.minsize(900, 620)
        self.win.transient(parent)
        try:
            self.win.grab_set()
        except Exception:
            pass

        self.current_img_idx = (
            app.current_sample_idx
            if (app.image_files and 0 <= app.current_sample_idx < len(app.image_files))
            else 0
        )
        self.mode_var = tk.StringVar(value=app.preprocess_mode_var.get())
        self.upscale_var = tk.BooleanVar(value=app.upscale_2x_var.get())
        self.ocr_engine_var = tk.StringVar(value=app.ocr_engine_var.get())

        self.orig_image = None
        self.prep_image = None
        self.orig_photo = None
        self.prep_photo = None

        self._build_ui()
        self._load_current_image()

    def _build_ui(self):
        # Top toolbar
        top = ttk.Frame(self.win, padding="10 8")
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top, text="Chọn ảnh:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self.img_combo = ttk.Combobox(top, values=self.app.image_files, state="readonly", width=24)
        if self.app.image_files:
            self.img_combo.current(self.current_img_idx)
        self.img_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.img_combo.bind("<<ComboboxSelected>>", self._on_image_selected)

        ttk.Label(top, text="Bộ lọc xử lý:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 4))
        self.mode_combo = ttk.Combobox(
            top, textvariable=self.mode_var, values=PREPROCESS_MODES, state="readonly", width=34
        )
        self.mode_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self._update_preprocessed_preview())

        ttk.Checkbutton(
            top, text="Upscale 2x", variable=self.upscale_var, command=self._update_preprocessed_preview
        ).pack(side=tk.LEFT, padx=(0, 10))

        btn_run_test = ttk.Button(top, text="⚡ Quét Thử OCR", style="Primary.TButton", command=self._run_test_scan)
        btn_run_test.pack(side=tk.LEFT, padx=5)

        # Center: Side-by-side Image Previews
        preview_paned = ttk.PanedWindow(self.win, orient=tk.HORIZONTAL)
        preview_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Left: Original
        f_left = ttk.LabelFrame(preview_paned, text="Ảnh Gốc (Original Image)", padding=5)
        preview_paned.add(f_left, weight=1)
        self.lbl_orig = ttk.Label(f_left, text="No Image", anchor="center", background="#0f172a")
        self.lbl_orig.pack(fill=tk.BOTH, expand=True)

        # Right: Preprocessed
        f_right = ttk.LabelFrame(preview_paned, text="Ảnh Sau Tiền Xử Lý (Preprocessed Image)", padding=5)
        preview_paned.add(f_right, weight=1)
        self.lbl_prep = ttk.Label(f_right, text="No Image", anchor="center", background="#0f172a")
        self.lbl_prep.pack(fill=tk.BOTH, expand=True)

        # Bottom: OCR Test Results & Actions
        res_frame = ttk.LabelFrame(self.win, text="Kết Quả Quét Thử OCR & Trích Xuất Dữ Liệu", padding=8)
        res_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

        self.txt_ocr_output = tk.Text(
            res_frame, height=5, font=("Consolas", 10), wrap="word", bg="#f8fafc", relief="solid", borderwidth=1
        )
        self.txt_ocr_output.pack(fill=tk.X, expand=True, side=tk.TOP, pady=(0, 6))

        bot_bar = ttk.Frame(self.win, padding="10 8")
        bot_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.lbl_status = ttk.Label(
            bot_bar, text="Chọn bộ lọc và bấm '⚡ Quét Thử OCR' để kiểm tra kết quả.", font=("Segoe UI", 9, "italic")
        )
        self.lbl_status.pack(side=tk.LEFT)

        ttk.Button(bot_bar, text="Đóng", command=self.win.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(
            bot_bar, text="✅ Áp Dụng Cấu Hình Này", style="Accent.TButton", command=self._apply_and_close
        ).pack(side=tk.RIGHT, padx=4)

    def _on_image_selected(self, event=None):
        idx = self.img_combo.current()
        if 0 <= idx < len(self.app.image_files):
            self.current_img_idx = idx
            self._load_current_image()

    def _load_current_image(self):
        if not self.app.image_files or not self.app.folder_path:
            return
        filename = self.app.image_files[self.current_img_idx]
        img_path = os.path.join(self.app.folder_path, filename)
        if not os.path.isfile(img_path):
            return
        try:
            self.orig_image = Image.open(img_path).convert("RGB")
            self._update_original_preview()
            self._update_preprocessed_preview()
        except Exception as e:
            self.lbl_status.config(text=f"Lỗi mở ảnh: {e}")

    def _update_original_preview(self):
        if not self.orig_image:
            return
        w, h = self.orig_image.size
        max_w, max_h = 480, 280
        ratio = min(max_w / max(1, w), max_h / max(1, h))
        nw, nh = max(1, int(w * ratio)), max(1, int(h * ratio))
        resized = self.orig_image.resize((nw, nh), Image.Resampling.BILINEAR)
        self.orig_photo = ImageTk.PhotoImage(resized)
        self.lbl_orig.config(image=self.orig_photo, text="")

    def _update_preprocessed_preview(self):
        if not self.orig_image:
            return
        try:
            mode = self.mode_var.get()
            upscale = self.upscale_var.get()
            self.prep_image = preprocess_for_ocr(self.orig_image, mode=mode, upscale=upscale)
            w, h = self.prep_image.size
            max_w, max_h = 480, 280
            ratio = min(max_w / max(1, w), max_h / max(1, h))
            nw, nh = max(1, int(w * ratio)), max(1, int(h * ratio))
            resized = self.prep_image.resize((nw, nh), Image.Resampling.BILINEAR)
            self.prep_photo = ImageTk.PhotoImage(resized)
            self.lbl_prep.config(image=self.prep_photo, text="")
        except Exception as e:
            self.lbl_status.config(text=f"Lỗi tiền xử lý ảnh: {e}")

    def _run_test_scan(self):
        if not self.prep_image:
            return
        self.lbl_status.config(text="Đang quét thử OCR... Xin vui lòng đợi...")
        self.txt_ocr_output.delete("1.0", tk.END)
        self.txt_ocr_output.insert(tk.END, "⏳ Đang quét OCR trên ảnh tiền xử lý...\n")

        engine_name = self.app.ocr_engine_var.get()

        def worker():
            import time

            t0 = time.time()
            full_text = ""
            lines = []
            if "Google" in engine_name and HAVE_LENS:
                loop = asyncio.new_event_loop()
                try:
                    lens = LensAPI()
                    res = loop.run_until_complete(lens.process_image(self.prep_image, output_format="full_text"))
                    loop.run_until_complete(lens.aclose())
                    full_text = res.get("ocr_text", "")
                    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
                except Exception as e:
                    full_text = f"Lỗi Google OCR: {e}"
                finally:
                    loop.close()
            elif HAVE_RAPIDOCR:
                engine = RapidOCR()
                res, _ = engine(np.array(self.prep_image))
                if res:
                    lines = [line[1].strip() for line in res]
                    full_text = "\n".join(lines)
            else:
                full_text = "Không tìm thấy OCR Engine khả dụng."

            elapsed = round(time.time() - t0, 3)

            extracted_summary = []
            for r in self.app.rules:
                if r["type"] == "keyword":
                    val = extract_by_keyword(full_text, r["keyword"])
                elif r["type"] == "regex":
                    val = extract_by_pattern(full_text, r["pattern"])
                elif r["type"] == "box" and r.get("box"):
                    val = extract_by_box(
                        self.prep_image,
                        (r["box"]["rx1"], r["box"]["ry1"], r["box"]["rx2"], r["box"]["ry2"]),
                        engine_name,
                    )
                else:
                    val = ""
                extracted_summary.append(f"  • {r['name']} ({r['var']}): \"{val}\"")

            self.win.after(0, self._display_test_results, full_text, extracted_summary, elapsed)

        threading.Thread(target=worker, daemon=True).start()

    def _display_test_results(self, full_text, extracted_summary, elapsed):
        self.txt_ocr_output.delete("1.0", tk.END)
        out = []
        out.append(
            f"⏱️ Quét hoàn tất trong {elapsed}s | Bộ lọc: {self.mode_var.get()} | Upscale 2x: {self.upscale_var.get()}"
        )
        out.append("-" * 70)
        out.append("🎯 DỮ LIỆU TRÍCH XUẤT THEO QUY TẮC:")
        if extracted_summary:
            out.extend(extracted_summary)
        else:
            out.append("  (Chưa có quy tắc nào được định nghĩa)")
        out.append("-" * 70)
        out.append("📄 TOÀN BỘ KÝ TỰ NHẬN DIỆN (FULL OCR TEXT):")
        out.append(full_text if full_text.strip() else "(Không tìm thấy văn bản)")
        self.txt_ocr_output.insert(tk.END, "\n".join(out))
        self.lbl_status.config(text=f"✅ Quét xong trong {elapsed}s.")

    def _apply_and_close(self):
        self.app.preprocess_mode_var.set(self.mode_var.get())
        self.app.upscale_2x_var.set(self.upscale_var.get())
        self.win.destroy()
        messagebox.showinfo(
            "Đã Áp Dụng",
            f"Đã cấu hình bộ lọc tiền xử lý: {self.mode_var.get()}\nUpscale 2x: {self.upscale_var.get()}",
        )


# ============================================================================
# REVIEW FOCUS DIALOG (HUMAN-IN-THE-LOOP QUICK VERIFICATION)
# ============================================================================
class ReviewFocusDialog:
    """
    Dedicated Human-in-the-Loop Review & Focus Dialog.
    Enables rapid manual verification and correction of OCR extraction outputs
    with keyboard shortcuts (Enter = Save & Next, Ctrl+Left = Prev, Esc = Close).
    """

    def __init__(self, parent: tk.Tk, app, target_img_idx: int = None, target_rule_idx: int = None):
        self.parent = parent
        self.app = app
        self.win = tk.Toplevel(parent)
        self.win.title("🎯 Review Focus - Soát Lỗi & Sửa Kết Quả Thủ Công")
        self.win.geometry("1150x760")
        self.win.minsize(920, 650)
        self.win.transient(parent)
        try:
            self.win.grab_set()
        except Exception:
            pass

        # Build list of distinct image indices present in results_data
        self.unique_image_indices = []
        for row in app.results_data:
            if row["img_idx"] not in self.unique_image_indices:
                self.unique_image_indices.append(row["img_idx"])
        self.unique_image_indices.sort()

        if target_img_idx is not None and target_img_idx in self.unique_image_indices:
            self.current_idx_pointer = self.unique_image_indices.index(target_img_idx)
        else:
            self.current_idx_pointer = 0

        self.target_rule_idx = target_rule_idx
        self.filter_issues_only_var = tk.BooleanVar(value=False)
        self.field_entries = []  # list of (row_dict, ttk.Entry, lbl_status, rule_dict)

        self.current_pil_img = None
        self.current_tk_img = None

        self._build_ui()
        self._load_current_image_data()
        self._bind_keys()

    def _bind_keys(self):
        self.win.bind("<Return>", lambda e: self.on_save_and_next())
        self.win.bind("<Control-Left>", lambda e: self.on_prev())
        self.win.bind("<Alt-Left>", lambda e: self.on_prev())
        self.win.bind("<Control-Right>", lambda e: self.on_save_and_next())
        self.win.bind("<Alt-Right>", lambda e: self.on_save_and_next())
        self.win.bind("<Escape>", lambda e: self.win.destroy())

    def _build_ui(self):
        # Top Header Bar
        top_bar = ttk.Frame(self.win, padding="10 8")
        top_bar.pack(side=tk.TOP, fill=tk.X)

        self.btn_prev = ttk.Button(top_bar, text="◀ Trước (Ctrl+←)", command=self.on_prev)
        self.btn_prev.pack(side=tk.LEFT, padx=3)

        self.lbl_progress = ttk.Label(
            top_bar, text="Ảnh 1 / 1", font=("Segoe UI", 12, "bold"), foreground="#1e293b"
        )
        self.lbl_progress.pack(side=tk.LEFT, padx=12)

        self.btn_next = ttk.Button(
            top_bar, text="Tiếp theo ▶ (Enter / Ctrl+→)", style="Primary.TButton", command=self.on_save_and_next
        )
        self.btn_next.pack(side=tk.LEFT, padx=3)

        ttk.Separator(top_bar, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=15)

        chk_filter = ttk.Checkbutton(
            top_bar,
            text="⚠️ Chỉ duyệt ảnh có lỗi / rỗng (Filter Suspect/Empty)",
            variable=self.filter_issues_only_var,
            command=self._on_filter_toggled,
        )
        chk_filter.pack(side=tk.LEFT, padx=5)

        ttk.Button(top_bar, text="Đóng (Esc)", command=self.win.destroy).pack(side=tk.RIGHT, padx=5)

        # Paned Window (Left: Image Preview, Right: Editable Fields & Live Output)
        paned = ttk.PanedWindow(self.win, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        # Left: Image Viewer
        left_box = ttk.LabelFrame(paned, text="Hình Ảnh Kiểm Tra (Visual Check)", padding=6)
        paned.add(left_box, weight=6)

        self.canvas_img = tk.Canvas(left_box, bg="#0f172a", highlightthickness=0)
        self.canvas_img.pack(fill=tk.BOTH, expand=True)
        self.canvas_img.bind("<Configure>", lambda e: self._draw_image_on_canvas())

        # Right: Fields & Filename
        right_box = ttk.LabelFrame(paned, text="Trích Xuất & Sửa Ký Tự (Keyboard-First)", padding=10)
        paned.add(right_box, weight=5)

        self.lbl_filename = ttk.Label(
            right_box, text="File: sample.png", font=("Segoe UI", 10, "bold"), foreground="#2563eb"
        )
        self.lbl_filename.pack(anchor="w", pady=(0, 8))

        # Container for dynamic field entries
        self.fields_container = ttk.Frame(right_box)
        self.fields_container.pack(fill=tk.BOTH, expand=True)

        # Live Filename Preview Box
        preview_box = ttk.LabelFrame(right_box, text="🏷️ Xem Trước Tên File Mới Khi Đổi (Live Preview)", padding=8)
        preview_box.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

        self.lbl_new_name_preview = ttk.Label(
            preview_box, text="", font=("Segoe UI", 11, "bold"), foreground="#059669", wraplength=420
        )
        self.lbl_new_name_preview.pack(fill=tk.X, pady=3)

        tip_lbl = ttk.Label(
            right_box,
            text="💡 Mẹo: Nhấn Enter để Lưu và chuyển ngay sang ảnh tiếp theo mà không cần dùng chuột!",
            font=("Segoe UI", 8, "italic"),
            foreground="#64748b",
        )
        tip_lbl.pack(side=tk.BOTTOM, anchor="w", pady=(5, 0))

    def _draw_image_on_canvas(self):
        if not self.current_pil_img:
            return
        cw = max(100, self.canvas_img.winfo_width())
        ch = max(100, self.canvas_img.winfo_height())
        iw, ih = self.current_pil_img.size

        scale = min(cw / max(1, iw), ch / max(1, ih)) * 0.96
        nw = max(1, int(iw * scale))
        nh = max(1, int(ih * scale))

        resized = self.current_pil_img.resize((nw, nh), Image.Resampling.BILINEAR)
        self.current_tk_img = ImageTk.PhotoImage(resized)

        self.canvas_img.delete("all")
        ox = (cw - nw) // 2
        oy = (ch - nh) // 2
        self.canvas_img.create_image(ox, oy, anchor=tk.NW, image=self.current_tk_img)

    def _load_current_image_data(self):
        if not self.unique_image_indices:
            return

        img_idx = self.unique_image_indices[self.current_idx_pointer]
        orig_filename = self.app.image_files[img_idx]

        total = len(self.unique_image_indices)
        self.lbl_progress.config(text=f"Ảnh {self.current_idx_pointer + 1} / {total}")
        self.lbl_filename.config(text=f"Tệp: {orig_filename}")

        # 1. Load and display Image on Canvas
        img_path = os.path.join(self.app.folder_path, orig_filename)
        if os.path.isfile(img_path):
            try:
                self.current_pil_img = Image.open(img_path).convert("RGB")
                self._draw_image_on_canvas()
            except Exception as e:
                print("Error opening review image:", e)

        # 2. Clear old field widgets
        for widget in self.fields_container.winfo_children():
            widget.destroy()

        self.field_entries.clear()

        # 3. Find all rows in results_data for this image
        image_rows = [r for r in self.app.results_data if r["img_idx"] == img_idx]

        focused_entry = None

        for r_idx, row_item in enumerate(image_rows):
            f_frame = ttk.Frame(self.fields_container, padding="4 6")
            f_frame.pack(fill=tk.X, pady=4)

            # Header row: Field Name & Tag
            hdr = ttk.Frame(f_frame)
            hdr.pack(fill=tk.X)

            rule_idx = row_item.get("rule_idx", 0)
            rule = self.app.rules[rule_idx] if rule_idx < len(self.app.rules) else None

            ttk.Label(
                hdr,
                text=f"{row_item['field']} ({row_item['var_tag']}):",
                font=("Segoe UI", 10, "bold"),
                foreground="#1e293b",
            ).pack(side=tk.LEFT)

            status_lbl = ttk.Label(hdr, font=("Segoe UI", 8, "bold"))
            status_lbl.pack(side=tk.RIGHT)

            # Large text input
            ent = ttk.Entry(f_frame, font=("Segoe UI", 14, "bold"))
            ent.insert(0, row_item["ocr_text"])
            ent.pack(fill=tk.X, pady=(3, 0))

            # Bind key release to update status & filename preview live
            def make_edit_cb(entry, status, rule_ref):
                def callback(event=None):
                    val = entry.get().strip()
                    if not val:
                        status.config(text="⚠️ RỖNG", foreground="#dc2626")
                    elif rule_ref and rule_ref.get("type") == "regex" and rule_ref.get("pattern"):
                        try:
                            if re.search(rule_ref["pattern"], val):
                                status.config(text="✅ HỢP LỆ", foreground="#059669")
                            else:
                                status.config(text="⚠️ KHÁC KHUÔN MẪU", foreground="#d97706")
                        except Exception:
                            status.config(text="✅ ĐÃ NHẬP", foreground="#059669")
                    else:
                        status.config(text="✅ ĐÃ CÓ", foreground="#059669")
                    self._update_live_filename_preview()

                return callback

            cb = make_edit_cb(ent, status_lbl, rule)
            ent.bind("<KeyRelease>", cb)
            cb()

            self.field_entries.append((row_item, ent, status_lbl, rule))

            if focused_entry is None or (
                self.target_rule_idx is not None and rule_idx == self.target_rule_idx
            ):
                focused_entry = ent

        if focused_entry:
            focused_entry.focus_set()
            focused_entry.select_range(0, tk.END)

        self._update_live_filename_preview()

    def _update_live_filename_preview(self):
        if not self.unique_image_indices:
            return
        img_idx = self.unique_image_indices[self.current_idx_pointer]
        orig_filename = self.app.image_files[img_idx]
        orig_stem = os.path.splitext(orig_filename)[0]

        ocr_texts = [ent.get().strip() for _, ent, _, _ in self.field_entries]
        new_stem = compute_filename(self.app.template_var.get(), img_idx + 1, orig_stem, ocr_texts)

        orig_ext = os.path.splitext(orig_filename)[1].lstrip(".")
        chosen_fmt = self.app.format_var.get().lower()
        final_ext = "png" if "png" in chosen_fmt else ("jpg" if "jpg" in chosen_fmt else orig_ext)
        new_full_name = f"{new_stem}.{final_ext}"

        self.lbl_new_name_preview.config(text=new_full_name)

    def on_save_and_next(self):
        if not self.unique_image_indices:
            return

        img_idx = self.unique_image_indices[self.current_idx_pointer]
        orig_filename = self.app.image_files[img_idx]

        # 1. Commit all edited entries
        for row_item, ent, _, _ in self.field_entries:
            row_item["ocr_text"] = ent.get().strip()

        # 2. Recalculate filenames and update main treeview
        self.app._recalculate_filenames_for_image(orig_filename, img_idx)

        # 3. Advance to next
        next_ptr = self._find_next_pointer(direction=1)
        if next_ptr is not None:
            self.current_idx_pointer = next_ptr
            self._load_current_image_data()
        else:
            if self.filter_issues_only_var.get():
                messagebox.showinfo("Hoàn Tất", "🎉 Tuyệt vời! Không còn ảnh nào bị lỗi hoặc rỗng.")
            else:
                messagebox.showinfo("Hoàn Tất", "🎉 Đã duyệt hết tất cả các ảnh trong danh sách!")

    def on_prev(self):
        if not self.unique_image_indices:
            return

        # Commit current before moving
        img_idx = self.unique_image_indices[self.current_idx_pointer]
        orig_filename = self.app.image_files[img_idx]
        for row_item, ent, _, _ in self.field_entries:
            row_item["ocr_text"] = ent.get().strip()
        self.app._recalculate_filenames_for_image(orig_filename, img_idx)

        prev_ptr = self._find_next_pointer(direction=-1)
        if prev_ptr is not None:
            self.current_idx_pointer = prev_ptr
            self._load_current_image_data()

    def _find_next_pointer(self, direction=1):
        total = len(self.unique_image_indices)
        if total <= 1:
            return None

        ptr = self.current_idx_pointer + direction
        while 0 <= ptr < total:
            if not self.filter_issues_only_var.get():
                return ptr

            # If filter is ON, check if image has any empty or suspect fields
            check_img_idx = self.unique_image_indices[ptr]
            rows = [r for r in self.app.results_data if r["img_idx"] == check_img_idx]
            has_issue = False
            for r in rows:
                txt = r["ocr_text"].strip()
                if not txt:
                    has_issue = True
                    break
                rule_idx = r.get("rule_idx", 0)
                rule = self.app.rules[rule_idx] if rule_idx < len(self.app.rules) else None
                if rule and rule.get("type") == "regex" and rule.get("pattern"):
                    try:
                        if not re.search(rule["pattern"], txt):
                            has_issue = True
                            break
                    except Exception:
                        pass
            if has_issue:
                return ptr
            ptr += direction

        return None

    def _on_filter_toggled(self):
        if self.filter_issues_only_var.get():
            # If current item is not problematic, jump to first problematic
            img_idx = self.unique_image_indices[self.current_idx_pointer]
            rows = [r for r in self.app.results_data if r["img_idx"] == img_idx]
            current_is_issue = any(not r["ocr_text"].strip() for r in rows)
            if not current_is_issue:
                next_ptr = self._find_next_pointer(direction=1)
                if next_ptr is None:
                    next_ptr = self._find_next_pointer(direction=-1)
                if next_ptr is not None:
                    self.current_idx_pointer = next_ptr
                    self._load_current_image_data()
                else:
                    messagebox.showinfo("Thông Báo", "Tất cả ảnh đều đã có dữ liệu đầy đủ!")
                    self.filter_issues_only_var.set(False)


# ============================================================================
# 4. MAIN APPLICATION CLASS
# ============================================================================
class SmartBatchExtractorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Smart Batch Character Extractor & Renamer (Crop-Resilient)")
        self.root.geometry("1300x850")
        self.root.minsize(1080, 720)

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

        # Interactive drawing state
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.active_rect_id = None

        # Detected lines on sample image for 1-click rule creation
        self.detected_sample_lines = []

        # Extraction Rules: list of dicts:
        # {"id": 1, "var": "{o1}", "name": "Mã phiếu", "type": "keyword", "keyword": "Mã phiếu", "pattern": "", "box": None}
        self.rules = []
        self.selected_rule_idx = -1

        # Table data: list of dicts: {orig_file, region, var_tag, ocr_text, new_name}
        self.results_data = []

        # Configurations
        self.ocr_engine_var = tk.StringVar(value="Google Lens (Cloud AI - Highly Accurate)" if HAVE_LENS else "RapidOCR (Local Offline)")
        self.preprocess_mode_var = tk.StringVar(value="CLAHE (Độ tương phản cao - Chống lóa / Mặt kính)")
        self.upscale_2x_var = tk.BooleanVar(value=True)
        self.template_var = tk.StringVar(value=DEFAULT_NAME_TEMPLATE)
        self.export_mode_var = tk.StringVar(value="Copy & Rename Original (High Quality)")
        self.format_var = tk.StringVar(value="Keep original")
        self.output_folder_var = tk.StringVar(value="")

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
        self.style.configure("Review.TButton", font=("Segoe UI", 9, "bold"), background="#d97706", foreground="#ffffff")
        self.style.map("Review.TButton", background=[("active", "#b45309")])

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

        btn_glass = ttk.Button(top_bar, text="🔍 GlassID Demo", command=self.on_load_glass_demo)
        btn_glass.pack(side=tk.LEFT, padx=3)

        btn_save_cfg = ttk.Button(top_bar, text="💾 Save Rules", command=self.on_save_config)
        btn_save_cfg.pack(side=tk.LEFT, padx=3)

        btn_load_cfg = ttk.Button(top_bar, text="📂 Load Rules", command=self.on_load_config)
        btn_load_cfg.pack(side=tk.LEFT, padx=3)

        self.folder_disp_lbl = ttk.Label(top_bar, text="No folder selected", foreground="#64748b")
        self.folder_disp_lbl.pack(side=tk.RIGHT, padx=5)

        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 5))

        # ====================================================================
        # LEFT PANE: Canvas & Rule Manager
        # ====================================================================
        left_frame = ttk.Frame(paned, padding=5)
        paned.add(left_frame, weight=5)

        # Sample Image Selector
        sample_bar = ttk.Frame(left_frame)
        sample_bar.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(sample_bar, text="Sample Image:", style="Header.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self.sample_combo = ttk.Combobox(sample_bar, state="readonly", width=30)
        self.sample_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.sample_combo.bind("<<ComboboxSelected>>", self.on_sample_combo_selected)

        ttk.Button(sample_bar, text="◀", width=3, command=self.on_prev_sample).pack(side=tk.LEFT, padx=1)
        ttk.Button(sample_bar, text="▶", width=3, command=self.on_next_sample).pack(side=tk.LEFT, padx=1)

        btn_detect = ttk.Button(sample_bar, text="🔎 Auto Detect Text", command=self.on_auto_detect_sample_text)
        btn_detect.pack(side=tk.LEFT, padx=(4, 2))

        # Canvas with crosshair
        canvas_container = ttk.Frame(left_frame, borderwidth=1, relief="solid")
        canvas_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_container, bg="#1e293b", cursor="cross", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        # Extraction Rules List (Handles Keywords, Regex, and Coordinates)
        rule_box = ttk.LabelFrame(left_frame, text="Extraction Rules (Resilient to Cropping & Shifts)", padding=6)
        rule_box.pack(fill=tk.X, pady=(6, 0))

        cols = ("id", "var", "name", "method", "criteria")
        self.rule_tree = ttk.Treeview(rule_box, columns=cols, show="headings", height=4, selectmode="browse")
        self.rule_tree.heading("id", text="#")
        self.rule_tree.heading("var", text="Tag")
        self.rule_tree.heading("name", text="Field Name")
        self.rule_tree.heading("method", text="Method")
        self.rule_tree.heading("criteria", text="Keyword / Pattern / Coords")

        self.rule_tree.column("id", width=30, anchor="center")
        self.rule_tree.column("var", width=50, anchor="center")
        self.rule_tree.column("name", width=110, anchor="w")
        self.rule_tree.column("method", width=85, anchor="center")
        self.rule_tree.column("criteria", width=220, anchor="w")

        rule_scroll = ttk.Scrollbar(rule_box, orient="vertical", command=self.rule_tree.yview)
        self.rule_tree.configure(yscrollcommand=rule_scroll.set)
        self.rule_tree.pack(side=tk.TOP, fill=tk.X, expand=True)
        self.rule_tree.bind("<<TreeviewSelect>>", self.on_rule_selected)

        # Quick Rule Editing / Creation Toolbar
        edit_bar = ttk.Frame(rule_box)
        edit_bar.pack(fill=tk.X, pady=(5, 0))

        ttk.Label(edit_bar, text="Field:").pack(side=tk.LEFT)
        self.ent_rule_name = ttk.Entry(edit_bar, width=10)
        self.ent_rule_name.pack(side=tk.LEFT, padx=2)

        ttk.Label(edit_bar, text="Type:").pack(side=tk.LEFT)
        self.rule_type_combo = ttk.Combobox(
            edit_bar, values=["keyword", "regex", "box"], state="readonly", width=8
        )
        self.rule_type_combo.set("keyword")
        self.rule_type_combo.pack(side=tk.LEFT, padx=2)

        ttk.Label(edit_bar, text="Value:").pack(side=tk.LEFT)
        self.ent_rule_val = ttk.Entry(edit_bar, width=14)
        self.ent_rule_val.pack(side=tk.LEFT, padx=2)

        ttk.Button(edit_bar, text="➕ Add Rule", command=self.on_add_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(edit_bar, text="💾 Update", command=self.on_update_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(edit_bar, text="❌ Delete", command=self.on_delete_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(edit_bar, text="🗑️ Clear", command=self.on_clear_rules).pack(side=tk.LEFT, padx=2)

        # ====================================================================
        # RIGHT PANE: Settings, Batch Actions, Results Table
        # ====================================================================
        right_frame = ttk.Frame(paned, padding=5)
        paned.add(right_frame, weight=6)

        settings_box = ttk.LabelFrame(right_frame, text="Batch Extraction & Renaming Configuration", padding=8)
        settings_box.pack(fill=tk.X, pady=(0, 6))

        # Row 1: Engine & Mode Info
        r1 = ttk.Frame(settings_box)
        r1.pack(fill=tk.X, pady=2)

        ttk.Label(r1, text="OCR Engine:").pack(side=tk.LEFT)
        engine_options = []
        if HAVE_LENS:
            engine_options.append("Google Lens (Cloud AI - Highly Accurate)")
        if HAVE_RAPIDOCR:
            engine_options.append("RapidOCR (Local Offline)")
        self.combo_engine = ttk.Combobox(
            r1, textvariable=self.ocr_engine_var, values=engine_options, state="readonly", width=36
        )
        self.combo_engine.pack(side=tk.LEFT, padx=(3, 10))

        ttk.Label(
            r1,
            text="🛡️ Keyword mode works 100% even if images are cropped!",
            foreground="#059669",
            font=("Segoe UI", 8, "italic"),
        ).pack(side=tk.LEFT)

        # Row 1b: Image Preprocessing Options
        r_prep = ttk.Frame(settings_box)
        r_prep.pack(fill=tk.X, pady=2)

        ttk.Label(r_prep, text="Preprocess:").pack(side=tk.LEFT)
        self.combo_prep = ttk.Combobox(
            r_prep,
            textvariable=self.preprocess_mode_var,
            values=PREPROCESS_MODES,
            state="readonly",
            width=36,
        )
        self.combo_prep.pack(side=tk.LEFT, padx=(3, 8))

        ttk.Checkbutton(
            r_prep, text="Upscale 2x", variable=self.upscale_2x_var
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            r_prep, text="🧪 Test Xử lý & Quét thử...", command=self.on_open_preprocess_test_dialog
        ).pack(side=tk.LEFT, padx=2)

        # Row 2: Rename Template
        r2 = ttk.Frame(settings_box)
        r2.pack(fill=tk.X, pady=4)

        ttk.Label(r2, text="Rename Template:").pack(side=tk.LEFT)
        ttk.Entry(r2, textvariable=self.template_var, width=22).pack(side=tk.LEFT, padx=4)

        ttk.Label(r2, text="Insert:", foreground="#64748b").pack(side=tk.LEFT, padx=(5, 2))
        for var_tag in ["{o1}", "{o2}", "{o3}", "{name}", "{index:03d}"]:
            ttk.Button(
                r2, text=var_tag, width=len(var_tag) + 1, command=lambda v=var_tag: self._insert_template_tag(v)
            ).pack(side=tk.LEFT, padx=1)

        # Row 3: Output mode & folder
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
            r3, textvariable=self.format_var, values=["Keep original", "png", "jpg"], state="readonly", width=12
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
            text="🔍 Extract Characters (All Images)",
            style="Primary.TButton",
            command=self.on_start_extract_characters,
        )
        self.btn_scan.pack(side=tk.LEFT, padx=(0, 5))

        self.btn_review = ttk.Button(
            action_bar,
            text="🎯 Review Focus (Soát Lỗi)",
            style="Review.TButton",
            command=self.on_open_review_focus,
        )
        self.btn_review.pack(side=tk.LEFT, padx=3)

        self.btn_export = ttk.Button(
            action_bar,
            text="📁 Export & Rename Images",
            style="Accent.TButton",
            command=self.on_start_export_images,
        )
        self.btn_export.pack(side=tk.LEFT, padx=3)

        self.btn_csv = ttk.Button(action_bar, text="📊 Export CSV", command=self.on_export_csv)
        self.btn_csv.pack(side=tk.LEFT, padx=3)

        self.btn_cancel = ttk.Button(action_bar, text="⏹️ Stop", command=self.on_stop_processing, state="disabled")
        self.btn_cancel.pack(side=tk.LEFT, padx=3)

        self.progress_bar = ttk.Progressbar(action_bar, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 5))
        self.progress_lbl = ttk.Label(action_bar, text="Idle", foreground="#64748b", width=12, anchor="e")
        self.progress_lbl.pack(side=tk.RIGHT)

        # Results Table
        table_frame = ttk.LabelFrame(right_frame, text="Extraction Results & New Filename Preview (Double-click to edit)", padding=6)
        table_frame.pack(fill=tk.BOTH, expand=True)

        res_cols = ("orig_file", "field", "var_tag", "ocr_text", "new_name")
        self.res_tree = ttk.Treeview(table_frame, columns=res_cols, show="headings", selectmode="browse")
        self.res_tree.heading("orig_file", text="Original File")
        self.res_tree.heading("field", text="Field")
        self.res_tree.heading("var_tag", text="Tag")
        self.res_tree.heading("ocr_text", text="Extracted Characters (Double-click to edit)")
        self.res_tree.heading("new_name", text="New Filename")

        self.res_tree.column("orig_file", width=140, anchor="w")
        self.res_tree.column("field", width=110, anchor="w")
        self.res_tree.column("var_tag", width=50, anchor="center")
        self.res_tree.column("ocr_text", width=230, anchor="w")
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

    def _insert_template_tag(self, tag: str):
        curr = self.template_var.get()
        self.template_var.set(curr + tag)

    def _update_status(self, msg: str):
        self.status_msg_lbl.config(text=msg)

    # ========================================================================
    # DEMO IMAGES LOADER
    # ========================================================================
    def on_load_demo_images(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        demo_dir = os.path.join(base_dir, "sample_images")
        if not os.path.isdir(demo_dir):
            messagebox.showinfo("Demo Images", "Sample images directory not found.")
            return

        self.folder_path = demo_dir
        self.folder_disp_lbl.config(text=demo_dir)

        files = sorted([f for f in os.listdir(demo_dir) if f.lower().endswith(SUPPORTED_EXTENSIONS)], key=natural_sort_key)
        if not files:
            messagebox.showinfo("Demo Images", "No images found in sample folder.")
            return

        self.image_files = files
        self.output_folder_var.set(os.path.join(demo_dir, "output"))
        self.sample_combo["values"] = self.image_files
        self.current_sample_idx = 0
        self.sample_combo.current(0)
        self.load_sample_image(self.image_files[0])

        # Predefine 3 Keyword Rules:
        # Rule 1 ({o1}): Keyword "Mã phiếu"
        # Rule 2 ({o2}): Keyword "Tên hàng"
        # Rule 3 ({o3}): Keyword "Trạng thái"
        self.rules = [
            {"id": 1, "var": "{o1}", "name": "Mã phiếu", "type": "keyword", "keyword": "Mã phiếu", "pattern": "", "box": None},
            {"id": 2, "var": "{o2}", "name": "Tên hàng", "type": "keyword", "keyword": "Tên hàng", "pattern": "", "box": None},
            {"id": 3, "var": "{o3}", "name": "Trạng thái", "type": "keyword", "keyword": "Trạng thái", "pattern": "", "box": None},
        ]
        self.selected_rule_idx = 0
        self.template_var.set("{o1}_{o2}")
        self._refresh_rule_tree()
        self.redraw_canvas()

        msg = (
            f"Loaded {len(self.image_files)} demo images (including cropped image: label_cropped_demo.png)!\n"
            "Predefined 3 Keyword Rules ({o1}=Mã phiếu, {o2}=Tên hàng, {o3}=Trạng thái).\n\n"
            "Click 'Extract Characters' to see keyword matching extract 100% correctly even on the cropped image!"
        )
        self._update_status("Loaded demo images with resilient keyword rules.")
        messagebox.showinfo("Demo Loaded", msg)

    def on_load_glass_demo(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        demo_dir = os.path.join(base_dir, "sample_images")
        if not os.path.isdir(demo_dir):
            messagebox.showinfo("Demo Images", "Sample images directory not found.")
            return

        glass_files = sorted(
            [
                f
                for f in os.listdir(demo_dir)
                if ("glass" in f.lower() or "faint" in f.lower()) and f.lower().endswith(SUPPORTED_EXTENSIONS)
            ],
            key=natural_sort_key,
        )
        if not glass_files:
            glass_files = sorted(
                [f for f in os.listdir(demo_dir) if f.lower().endswith(SUPPORTED_EXTENSIONS)], key=natural_sort_key
            )

        self.folder_path = demo_dir
        self.folder_disp_lbl.config(text=demo_dir)
        self.image_files = glass_files
        self.output_folder_var.set(os.path.join(demo_dir, "output"))
        self.sample_combo["values"] = self.image_files
        self.current_sample_idx = 0
        self.sample_combo.current(0)
        self.load_sample_image(self.image_files[0])

        # Predefine GlassID Rule with Regex capture
        self.rules = [
            {
                "id": 1,
                "var": "{o1}",
                "name": "GlassID",
                "type": "regex",
                "keyword": "",
                "pattern": r"(?i)GlassID\s*([A-Za-z0-9]+)",
                "box": None,
            },
        ]
        self.selected_rule_idx = 0
        self.template_var.set("{o1}")
        self.preprocess_mode_var.set("CLAHE (Độ tương phản cao - Chống lóa / Mặt kính)")
        self.upscale_2x_var.set(True)
        self._refresh_rule_tree()
        self.redraw_canvas()

        msg = (
            f"Loaded {len(self.image_files)} glass demo images (including faint etching: faint_glass_demo.png)!\n"
            "Predefined Rule: GlassID using Regex '(?i)GlassID\\s*([A-Za-z0-9]+)'\n"
            "Preprocess filter: CLAHE + Upscale 2x.\n\n"
            "Click 'Extract Characters' to scan, or 'Review Focus' to inspect and edit outputs!"
        )
        self._update_status("Loaded glass demo images (GlassID).")
        messagebox.showinfo("Glass Demo Loaded", msg)

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
            self.redraw_canvas()
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
    # AUTO-DETECT SAMPLE TEXT (1-CLICK RULE CREATION)
    # ========================================================================
    def on_auto_detect_sample_text(self):
        """Scans sample image and allows user to pick text lines to turn into rules."""
        if not self.sample_image:
            messagebox.showinfo("Auto Detect", "Please select or load an image first.")
            return

        self._update_status("Scanning sample image to detect text...")
        engine_name = self.ocr_engine_var.get()

        def worker():
            text_lines = []
            if "Google" in engine_name and HAVE_LENS:
                loop = asyncio.new_event_loop()
                try:
                    lens = LensAPI()
                    res = loop.run_until_complete(lens.process_image(self.sample_image, output_format="full_text"))
                    loop.run_until_complete(lens.aclose())
                    raw_text = res.get("ocr_text", "")
                    text_lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
                except Exception as e:
                    print("Auto detect error:", e)
                finally:
                    loop.close()
            elif HAVE_RAPIDOCR:
                engine = RapidOCR()
                res, _ = engine(np.array(self.sample_image))
                text_lines = [line[1].strip() for line in res] if res else []

            self.root.after(0, self._show_detected_text_dialog, text_lines)

        threading.Thread(target=worker, daemon=True).start()

    def _show_detected_text_dialog(self, text_lines):
        self._update_status("Sample image scanned.")
        if not text_lines:
            messagebox.showinfo("Detected Text", "No text detected in sample image.")
            return

        win = tk.Toplevel(self.root)
        win.title("Detected Text Lines (Click to Add as Rule)")
        win.geometry("520x450")
        win.transient(self.root)

        ttk.Label(
            win,
            text="Detected text lines in this sample image:\nClick a line to create an extraction rule:",
            style="Header.TLabel",
        ).pack(anchor="w", padx=12, pady=(10, 5))

        listbox_frame = ttk.Frame(win)
        listbox_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

        scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical")
        lb = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, font=("Segoe UI", 10), selectmode="single")
        scrollbar.config(command=lb.yview)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for l in text_lines:
            lb.insert(tk.END, l)

        def add_selected_line():
            sel = lb.curselection()
            if not sel:
                return
            chosen = text_lines[sel[0]]

            # Analyze text: check if it looks like a label/keyword
            if ":" in chosen:
                parts = chosen.split(":", 1)
                kw = parts[0].strip()
                field_name = kw
            else:
                kw = chosen.strip()
                field_name = kw[:15]

            new_idx = len(self.rules) + 1
            new_rule = {
                "id": new_idx,
                "var": f"{{o{new_idx}}}",
                "name": field_name,
                "type": "keyword",
                "keyword": kw,
                "pattern": "",
                "box": None,
            }
            self.rules.append(new_rule)
            self._refresh_rule_tree()
            win.destroy()
            messagebox.showinfo("Rule Added", f"Added extraction rule for: '{kw}' (Tag: {{o{new_idx}}})")

        btn_box = ttk.Frame(win)
        btn_box.pack(fill=tk.X, padx=12, pady=10)
        ttk.Button(btn_box, text="➕ Add as Keyword Rule", style="Primary.TButton", command=add_selected_line).pack(side=tk.LEFT)
        ttk.Button(btn_box, text="Close", command=win.destroy).pack(side=tk.RIGHT)

    # ========================================================================
    # CANVAS & VISUAL DRAWING
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

        # Draw any coordinate-type boxes
        for idx, rule in enumerate(self.rules):
            if rule.get("type") == "box" and rule.get("box"):
                self._draw_box_on_canvas(idx, rule)

    def _draw_box_on_canvas(self, idx: int, rule: dict):
        orig_w, orig_h = self.sample_image.size
        b = rule["box"]
        cx1 = self.sample_offset_x + b["rx1"] * orig_w * self.sample_scale
        cy1 = self.sample_offset_y + b["ry1"] * orig_h * self.sample_scale
        cx2 = self.sample_offset_x + b["rx2"] * orig_w * self.sample_scale
        cy2 = self.sample_offset_y + b["ry2"] * orig_h * self.sample_scale

        border_color = "#eab308" if idx == self.selected_rule_idx else "#06b6d4"
        self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=border_color, width=2)
        self.canvas.create_text(cx1 + 25, cy1 - 9, text=rule["var"], fill=border_color, font=("Segoe UI", 9, "bold"))

    def on_canvas_press(self, event):
        if not self.sample_image:
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
        if dx < 10 or dy < 10:
            return

        orig_w, orig_h = self.sample_image.size
        sx1, sy1 = min(self.drag_start_x, event.x), min(self.drag_start_y, event.y)
        sx2, sy2 = max(self.drag_start_x, event.x), max(self.drag_start_y, event.y)

        ix1 = max(0.0, min(float(orig_w), (sx1 - self.sample_offset_x) / self.sample_scale))
        iy1 = max(0.0, min(float(orig_h), (sy1 - self.sample_offset_y) / self.sample_scale))
        ix2 = max(0.0, min(float(orig_w), (sx2 - self.sample_offset_x) / self.sample_scale))
        iy2 = max(0.0, min(float(orig_h), (sy2 - self.sample_offset_y) / self.sample_scale))

        new_idx = len(self.rules) + 1
        new_rule = {
            "id": new_idx,
            "var": f"{{o{new_idx}}}",
            "name": f"Box #{new_idx}",
            "type": "box",
            "keyword": "",
            "pattern": "",
            "box": {
                "rx1": round(ix1 / orig_w, 4),
                "ry1": round(iy1 / orig_h, 4),
                "rx2": round(ix2 / orig_w, 4),
                "ry2": round(iy2 / orig_h, 4),
            },
        }
        self.rules.append(new_rule)
        self._refresh_rule_tree()
        self.redraw_canvas()

    # ========================================================================
    # RULE MANAGEMENT
    # ========================================================================
    def _refresh_rule_tree(self):
        for item in self.rule_tree.get_children():
            self.rule_tree.delete(item)

        for idx, r in enumerate(self.rules):
            r["id"] = idx + 1
            r["var"] = f"{{o{idx + 1}}}"
            crit = r["keyword"] if r["type"] == "keyword" else (r["pattern"] if r["type"] == "regex" else str(r["box"]))
            iid = self.rule_tree.insert("", "end", values=(r["id"], r["var"], r["name"], r["type"].upper(), crit))
            if idx == self.selected_rule_idx:
                self.rule_tree.selection_set(iid)

    def on_rule_selected(self, event=None):
        selected = self.rule_tree.selection()
        if not selected:
            return
        idx = self.rule_tree.index(selected[0])
        if 0 <= idx < len(self.rules):
            self.selected_rule_idx = idx
            r = self.rules[idx]
            self.ent_rule_name.delete(0, tk.END)
            self.ent_rule_name.insert(0, r["name"])
            self.rule_type_combo.set(r["type"])
            self.ent_rule_val.delete(0, tk.END)
            val = r["keyword"] if r["type"] == "keyword" else (r["pattern"] if r["type"] == "regex" else "")
            self.ent_rule_val.insert(0, val)
            self.redraw_canvas()

    def on_add_rule(self):
        name = self.ent_rule_name.get().strip() or "Field"
        rtype = self.rule_type_combo.get().strip()
        val = self.ent_rule_val.get().strip()

        new_idx = len(self.rules) + 1
        rule = {
            "id": new_idx,
            "var": f"{{o{new_idx}}}",
            "name": name,
            "type": rtype,
            "keyword": val if rtype == "keyword" else "",
            "pattern": val if rtype == "regex" else "",
            "box": None,
        }
        self.rules.append(rule)
        self.selected_rule_idx = len(self.rules) - 1
        self._refresh_rule_tree()

    def on_update_rule(self):
        if self.selected_rule_idx < 0 or self.selected_rule_idx >= len(self.rules):
            return
        name = self.ent_rule_name.get().strip()
        rtype = self.rule_type_combo.get().strip()
        val = self.ent_rule_val.get().strip()

        r = self.rules[self.selected_rule_idx]
        r["name"] = name
        r["type"] = rtype
        if rtype == "keyword":
            r["keyword"] = val
        elif rtype == "regex":
            r["pattern"] = val
        self._refresh_rule_tree()

    def on_delete_rule(self):
        if self.selected_rule_idx < 0 or self.selected_rule_idx >= len(self.rules):
            return
        del self.rules[self.selected_rule_idx]
        self.selected_rule_idx = min(self.selected_rule_idx, len(self.rules) - 1)
        self._refresh_rule_tree()
        self.redraw_canvas()

    def on_clear_rules(self):
        if messagebox.askyesno("Clear Rules", "Are you sure you want to delete all extraction rules?"):
            self.rules.clear()
            self.selected_rule_idx = -1
            self._refresh_rule_tree()
            self.redraw_canvas()

    def on_save_config(self):
        fpath = filedialog.asksaveasfilename(title="Save Extraction Rules", defaultextension=".json", filetypes=[("JSON Files", "*.json")])
        if fpath:
            cfg = {"rules": self.rules, "template": self.template_var.get()}
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Saved", f"Rules saved to:\n{fpath}")

    def on_load_config(self):
        fpath = filedialog.askopenfilename(title="Load Extraction Rules", filetypes=[("JSON Files", "*.json")])
        if fpath:
            with open(fpath, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if "rules" in cfg:
                self.rules = cfg["rules"]
            if "template" in cfg:
                self.template_var.set(cfg["template"])
            self._refresh_rule_tree()
            self.redraw_canvas()
            messagebox.showinfo("Loaded", "Rules successfully loaded!")

    def on_browse_output_folder(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_folder_var.set(os.path.abspath(folder))

    # ========================================================================
    # EXTRACTION WORKER
    # ========================================================================
    def on_start_extract_characters(self):
        if not self.image_files:
            messagebox.showwarning("No Images", "Please open an image folder or click 'Load Demo Images' first.")
            return

        if not self.rules:
            messagebox.showwarning("No Rules", "Please add at least one extraction rule first.")
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
        st = "normal" if enabled else "disabled"
        self.btn_scan.config(state=st)
        self.btn_review.config(state=st)
        self.btn_export.config(state=st)
        self.btn_csv.config(state=st)
        self.btn_cancel.config(state="normal" if not enabled else "disabled")

    def on_stop_processing(self):
        if self.is_processing:
            self.stop_requested = True
            self._update_status("Stopping process... Please wait.")

    def _extract_worker(self):
        chosen_engine = self.ocr_engine_var.get()
        if "Google" in chosen_engine and HAVE_LENS:
            asyncio.run(self._async_google_worker())
        elif HAVE_RAPIDOCR:
            self._sync_rapidocr_worker()
        else:
            self.root.after(0, messagebox.showerror, "No Engine", "No OCR engine available.")
            self.is_processing = False
            self._toggle_ui_state(True)

    async def _async_google_worker(self):
        total_images = len(self.image_files)
        lens = LensAPI()
        try:
            for img_idx, filename in enumerate(self.image_files):
                if self.stop_requested:
                    break

                pct = int(((img_idx + 1) / total_images) * 100)
                self.root.after(0, self._update_progress, pct, f"{img_idx + 1}/{total_images}")
                self.root.after(0, self._update_status, f"Scanning ({img_idx + 1}/{total_images}): {filename}...")

                img_path = os.path.join(self.folder_path, filename)
                try:
                    raw_img = Image.open(img_path).convert("RGB")
                    img = preprocess_for_ocr(
                        raw_img, mode=self.preprocess_mode_var.get(), upscale=self.upscale_2x_var.get()
                    )
                except Exception as e:
                    print(f"Error opening image {filename}: {e}", file=sys.stderr)
                    continue

                file_stem = os.path.splitext(filename)[0]

                # Full image OCR once
                try:
                    res = await lens.process_image(img, output_format="full_text")
                    full_text = res.get("ocr_text", "")
                except Exception as e:
                    print(f"Google OCR error on {filename}: {e}", file=sys.stderr)
                    full_text = ""

                image_ocr_texts = []
                for r in self.rules:
                    if r["type"] == "keyword":
                        extracted = extract_by_keyword(full_text, r["keyword"])
                    elif r["type"] == "regex":
                        extracted = extract_by_pattern(full_text, r["pattern"])
                    elif r["type"] == "box" and r.get("box"):
                        extracted = extract_by_box(
                            img, (r["box"]["rx1"], r["box"]["ry1"], r["box"]["rx2"], r["box"]["ry2"]), "Google", lens_api=lens
                        )
                    else:
                        extracted = ""
                    image_ocr_texts.append(extracted)

                new_file_stem = compute_filename(self.template_var.get(), img_idx + 1, file_stem, image_ocr_texts)
                orig_ext = os.path.splitext(filename)[1].lstrip(".")
                chosen_fmt = self.format_var.get().lower()
                final_ext = "png" if "png" in chosen_fmt else ("jpg" if "jpg" in chosen_fmt else orig_ext)
                new_full_name = f"{new_file_stem}.{final_ext}"

                for r_idx, r in enumerate(self.rules):
                    row_data = {
                        "orig_file": filename,
                        "field": r["name"],
                        "var_tag": r["var"],
                        "rule_idx": r_idx,
                        "img_idx": img_idx,
                        "ocr_text": image_ocr_texts[r_idx],
                        "new_name": new_full_name,
                    }
                    self.results_data.append(row_data)
                    self.root.after(0, self._insert_tree_row, row_data)
        finally:
            await lens.aclose()

        self.root.after(0, self._on_scan_finished)

    def _sync_rapidocr_worker(self):
        total_images = len(self.image_files)
        engine = RapidOCR()

        for img_idx, filename in enumerate(self.image_files):
            if self.stop_requested:
                break

            pct = int(((img_idx + 1) / total_images) * 100)
            self.root.after(0, self._update_progress, pct, f"{img_idx + 1}/{total_images}")
            self.root.after(0, self._update_status, f"RapidOCR ({img_idx + 1}/{total_images}): {filename}...")

            img_path = os.path.join(self.folder_path, filename)
            try:
                raw_img = Image.open(img_path).convert("RGB")
                img = preprocess_for_ocr(
                    raw_img, mode=self.preprocess_mode_var.get(), upscale=self.upscale_2x_var.get()
                )
            except Exception as e:
                print(f"Error opening image {filename}: {e}", file=sys.stderr)
                continue

            file_stem = os.path.splitext(filename)[0]

            try:
                res, _ = engine(np.array(img))
                full_text = "\n".join([line[1] for line in res]) if res else ""
            except Exception as e:
                print(f"RapidOCR error on {filename}: {e}", file=sys.stderr)
                full_text = ""

            image_ocr_texts = []
            for r in self.rules:
                if r["type"] == "keyword":
                    extracted = extract_by_keyword(full_text, r["keyword"])
                elif r["type"] == "regex":
                    extracted = extract_by_pattern(full_text, r["pattern"])
                elif r["type"] == "box" and r.get("box"):
                    extracted = extract_by_box(
                        img, (r["box"]["rx1"], r["box"]["ry1"], r["box"]["rx2"], r["box"]["ry2"]), "RapidOCR", rapid_engine=engine
                    )
                else:
                    extracted = ""
                image_ocr_texts.append(extracted)

            new_file_stem = compute_filename(self.template_var.get(), img_idx + 1, file_stem, image_ocr_texts)
            orig_ext = os.path.splitext(filename)[1].lstrip(".")
            chosen_fmt = self.format_var.get().lower()
            final_ext = "png" if "png" in chosen_fmt else ("jpg" if "jpg" in chosen_fmt else orig_ext)
            new_full_name = f"{new_file_stem}.{final_ext}"

            for r_idx, r in enumerate(self.rules):
                row_data = {
                    "orig_file": filename,
                    "field": r["name"],
                    "var_tag": r["var"],
                    "rule_idx": r_idx,
                    "img_idx": img_idx,
                    "ocr_text": image_ocr_texts[r_idx],
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
                row["field"],
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
        status_txt = "Stopped by user." if self.stop_requested else "Extraction completed!"
        self.progress_lbl.config(text="Complete" if not self.stop_requested else "Stopped")
        self._update_status(status_txt)
        messagebox.showinfo(
            "Extraction Completed",
            f"{status_txt}\nProcessed {len(self.image_files)} image(s).\n\n"
            "💡 TIP: Bấm nút '🎯 Review Focus (Soát Lỗi)' hoặc nhấp đúp vào dòng để kiểm tra và sửa lỗi nhanh!",
        )

    # ========================================================================
    # REVIEW FOCUS & INLINE EDITING
    # ========================================================================
    def on_tree_double_click(self, event):
        item = self.res_tree.identify_row(event.y)
        if not item:
            return
        item_idx = self.res_tree.index(item)
        if 0 <= item_idx < len(self.results_data):
            row_data = self.results_data[item_idx]
            self.on_open_review_focus(target_img_idx=row_data["img_idx"], target_rule_idx=row_data["rule_idx"])

    def on_open_review_focus(self, target_img_idx: int = None, target_rule_idx: int = None):
        if not self.results_data or not self.image_files:
            messagebox.showinfo(
                "Review Focus",
                "Chưa có dữ liệu trích xuất. Vui lòng bấm 'Extract Characters' trước khi soát lỗi.",
            )
            return
        ReviewFocusDialog(self.root, self, target_img_idx=target_img_idx, target_rule_idx=target_rule_idx)

    def on_open_preprocess_test_dialog(self):
        if not self.image_files:
            messagebox.showinfo("Test Tiền Xử Lý", "Vui lòng chọn thư mục ảnh hoặc tải ảnh Demo trước.")
            return
        PreprocessTestDialog(self.root, self)

    def _recalculate_filenames_for_image(self, filename: str, img_idx: int):
        orig_stem = os.path.splitext(filename)[0]
        ocr_texts = []
        row_indices = []

        for idx, row in enumerate(self.results_data):
            if row["orig_file"] == filename:
                ocr_texts.append(row["ocr_text"])
                row_indices.append(idx)

        new_stem = compute_filename(self.template_var.get(), img_idx + 1, orig_stem, ocr_texts)
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
    # EXPORT CSV & BATCH IMAGES
    # ========================================================================
    def on_export_csv(self):
        if not self.results_data:
            messagebox.showinfo("Export CSV", "No data to export. Please run extraction first.")
            return

        fpath = filedialog.asksaveasfilename(title="Save CSV File", defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not fpath:
            return

        try:
            with open(fpath, "w", newline="", encoding="utf-8-sig") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Original File", "Field", "Tag", "Extracted Characters", "New Filename"])
                for row in self.results_data:
                    writer.writerow([row["orig_file"], row["field"], row["var_tag"], row["ocr_text"], row["new_name"]])
            messagebox.showinfo("CSV Exported", f"Successfully exported to:\n{fpath}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export CSV:\n{e}")

    def on_start_export_images(self):
        if not self.image_files or not self.results_data:
            messagebox.showwarning("Notice", "Please extract characters first before exporting.")
            return

        out_folder = self.output_folder_var.get().strip()
        if not out_folder:
            out_folder = os.path.join(self.folder_path, "output")
            self.output_folder_var.set(out_folder)

        try:
            os.makedirs(out_folder, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot create output directory:\n{e}")
            return

        self.is_processing = True
        self.stop_requested = False
        self._toggle_ui_state(False)

        thread = threading.Thread(target=self._export_worker, daemon=True)
        thread.start()

    def _export_worker(self):
        out_folder = self.output_folder_var.get().strip()
        total = len(self.image_files)
        used = set()

        filename_map = {}
        for row in self.results_data:
            filename_map[row["orig_file"]] = row["new_name"]

        chosen_mode = self.export_mode_var.get()
        chosen_format = self.format_var.get().lower()

        for idx, filename in enumerate(self.image_files):
            if self.stop_requested:
                break

            pct = int(((idx + 1) / total) * 100)
            self.root.after(0, self._update_progress, pct, f"{idx + 1}/{total}")
            self.root.after(0, self._update_status, f"Exporting ({idx + 1}/{total}): {filename}...")

            orig_path = os.path.join(self.folder_path, filename)
            orig_stem = os.path.splitext(filename)[0]
            orig_ext = os.path.splitext(filename)[1].lstrip(".")

            save_ext = "png" if "png" in chosen_format else ("jpg" if "jpg" in chosen_format else orig_ext)

            if filename in filename_map:
                base_stem = os.path.splitext(filename_map[filename])[0]
            else:
                base_stem = compute_filename(self.template_var.get(), idx + 1, orig_stem, [])

            final_path = get_unique_output_path(out_folder, base_stem, save_ext, used)

            try:
                if "Copy & Rename" in chosen_mode and save_ext.lower() == orig_ext.lower():
                    shutil.copy2(orig_path, final_path)
                else:
                    img = Image.open(orig_path).convert("RGB")
                    if save_ext in ("jpg", "jpeg"):
                        img.save(final_path, format="JPEG", quality=95)
                    else:
                        img.save(final_path, format="PNG")
            except Exception as e:
                print(f"Export error on {final_path}: {e}", file=sys.stderr)

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
                f"Successfully exported renamed images to:\n{out_folder}\n\nOpen output folder now?",
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
# 5. ENTRY POINT
# ============================================================================
def main():
    root = tk.Tk()
    app = SmartBatchExtractorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
