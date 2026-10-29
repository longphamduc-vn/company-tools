#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Application Window: SmartBatchExtractorApp.
Combines Folder Selection, Sample Canvas, Rule Manager (Keyword / Regex / Box),
Batch Processing Workers, and Review Focus Launchers.
"""

import os
import sys
import re
import csv
import json
import shutil
import platform
import asyncio
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

from ..config import (
    APP_TITLE,
    APP_VERSION,
    SUPPORTED_EXTENSIONS,
    DEFAULT_NAME_TEMPLATE,
    PREPROCESS_MODES,
    HAVE_LENS,
    HAVE_RAPIDOCR,
    init_theme_styles,
)
from ..utils import (
    natural_sort_key,
    sanitize_filename,
    compute_filename,
    get_unique_output_path,
)
from ..ocr_engine import preprocess_for_ocr, run_rapidocr, run_lens_full_text
from ..extraction import (
    extract_by_keyword,
    extract_by_pattern,
    extract_by_box,
    find_bounding_box_for_rule,
    auto_detect_bbox_for_image,
)
from .preprocess_dialog import PreprocessTestDialog
from .review_focus_dialog import ReviewFocusDialog

if HAVE_RAPIDOCR:
    from rapidocr_onnxruntime import RapidOCR
    import numpy as np

if HAVE_LENS:
    from chrome_lens_py import LensAPI


class SmartBatchExtractorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_TITLE} (v{APP_VERSION})")
        self.root.geometry("1300x850")
        self.root.minsize(1080, 720)

        self.style = ttk.Style()
        init_theme_styles(self.style)

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

        # Extraction Rules: list of dicts:
        # {"id": 1, "var": "{o1}", "name": "Mã phiếu", "type": "keyword", "keyword": "Mã phiếu", "pattern": "", "box": None}
        self.rules = []
        self.selected_rule_idx = -1

        # Table data: list of dicts: {orig_file, field, var_tag, rule_idx, img_idx, ocr_text, new_name, bbox}
        self.results_data = []

        # Configurations
        default_engine = (
            "Google Lens (Cloud AI - Highly Accurate)"
            if HAVE_LENS
            else "RapidOCR (Local Offline)"
        )
        self.ocr_engine_var = tk.StringVar(value=default_engine)
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
        self._update_status("Sẵn sàng. Chọn thư mục hoặc bấm '✨ Demo Nhãn Hàng' / '🔍 Demo GlassID' để bắt đầu.")

    def _build_ui(self):
        # Top Header Bar
        top_bar = ttk.Frame(self.root, padding="10 8")
        top_bar.pack(side=tk.TOP, fill=tk.X)

        title_lbl = ttk.Label(
            top_bar,
            text="Batch Character Extractor & Renamer",
            font=("Segoe UI", 12, "bold"),
            foreground="#0f172a",
        )
        title_lbl.pack(side=tk.LEFT, padx=(0, 15))

        btn_open = ttk.Button(top_bar, text="📁 Chọn Thư Mục...", command=self.on_choose_folder)
        btn_open.pack(side=tk.LEFT, padx=3)

        btn_demo = ttk.Button(top_bar, text="✨ Demo Nhãn Hàng", command=self.on_load_demo_images)
        btn_demo.pack(side=tk.LEFT, padx=3)

        btn_glass = ttk.Button(top_bar, text="🔍 Demo GlassID", command=self.on_load_glass_demo)
        btn_glass.pack(side=tk.LEFT, padx=3)

        btn_save_cfg = ttk.Button(top_bar, text="💾 Lưu Quy Tắc", command=self.on_save_config)
        btn_save_cfg.pack(side=tk.LEFT, padx=3)

        btn_load_cfg = ttk.Button(top_bar, text="📂 Nạp Quy Tắc", command=self.on_load_config)
        btn_load_cfg.pack(side=tk.LEFT, padx=3)

        self.folder_disp_lbl = ttk.Label(top_bar, text="Chưa chọn thư mục", foreground="#64748b")
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

        ttk.Label(sample_bar, text="Ảnh Mẫu:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self.sample_combo = ttk.Combobox(sample_bar, state="readonly", width=28)
        self.sample_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.sample_combo.bind("<<ComboboxSelected>>", self.on_sample_combo_selected)

        ttk.Button(sample_bar, text="◀", width=3, command=self.on_prev_sample).pack(side=tk.LEFT, padx=1)
        ttk.Button(sample_bar, text="▶", width=3, command=self.on_next_sample).pack(side=tk.LEFT, padx=1)

        btn_detect = ttk.Button(sample_bar, text="🔎 Nhận Diện Text", command=self.on_auto_detect_sample_text)
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

        # Extraction Rules List
        rule_box = ttk.LabelFrame(
            left_frame, text="Quy Tắc Trích Xuất (Chống lệch & Chống ảnh bị cắt xén)", padding=6
        )
        rule_box.pack(fill=tk.X, pady=(6, 0))

        cols = ("id", "var", "name", "method", "criteria")
        self.rule_tree = ttk.Treeview(rule_box, columns=cols, show="headings", height=4, selectmode="browse")
        self.rule_tree.heading("id", text="#")
        self.rule_tree.heading("var", text="Tag")
        self.rule_tree.heading("name", text="Tên Trường")
        self.rule_tree.heading("method", text="Cách Thức")
        self.rule_tree.heading("criteria", text="Từ Khóa / Regex / Tọa Độ")

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

        ttk.Label(edit_bar, text="Trường:").pack(side=tk.LEFT)
        self.ent_rule_name = ttk.Entry(edit_bar, width=10)
        self.ent_rule_name.pack(side=tk.LEFT, padx=2)

        ttk.Label(edit_bar, text="Loại:").pack(side=tk.LEFT)
        self.rule_type_combo = ttk.Combobox(
            edit_bar, values=["keyword", "regex", "box"], state="readonly", width=8
        )
        self.rule_type_combo.set("keyword")
        self.rule_type_combo.pack(side=tk.LEFT, padx=2)

        ttk.Label(edit_bar, text="Giá trị:").pack(side=tk.LEFT)
        self.ent_rule_val = ttk.Entry(edit_bar, width=14)
        self.ent_rule_val.pack(side=tk.LEFT, padx=2)

        ttk.Button(edit_bar, text="➕ Thêm", command=self.on_add_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(edit_bar, text="💾 Sửa", command=self.on_update_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(edit_bar, text="❌ Xóa", command=self.on_delete_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(edit_bar, text="🗑️ Xóa hết", command=self.on_clear_rules).pack(side=tk.LEFT, padx=2)

        # ====================================================================
        # RIGHT PANE: Settings, Batch Actions, Results Table
        # ====================================================================
        right_frame = ttk.Frame(paned, padding=5)
        paned.add(right_frame, weight=6)

        settings_box = ttk.LabelFrame(right_frame, text="Cấu Hình Quét Hàng Loạt & Đổi Tên", padding=8)
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
            text="🛡️ Chế độ Keyword & Regex chống lệch 100% khi ảnh bị crop!",
            foreground="#059669",
            font=("Segoe UI", 8, "italic"),
        ).pack(side=tk.LEFT)

        # Row 1b: Image Preprocessing Options
        r_prep = ttk.Frame(settings_box)
        r_prep.pack(fill=tk.X, pady=2)

        ttk.Label(r_prep, text="Tiền xử lý:").pack(side=tk.LEFT)
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

        ttk.Label(r2, text="Mẫu Tên File:").pack(side=tk.LEFT)
        ttk.Entry(r2, textvariable=self.template_var, width=22).pack(side=tk.LEFT, padx=4)

        ttk.Label(r2, text="Chèn:", foreground="#64748b").pack(side=tk.LEFT, padx=(5, 2))
        for var_tag in ["{o1}", "{o2}", "{o3}", "{name}", "{index:03d}"]:
            ttk.Button(
                r2, text=var_tag, width=len(var_tag) + 1, command=lambda v=var_tag: self._insert_template_tag(v)
            ).pack(side=tk.LEFT, padx=1)

        # Row 3: Output mode & folder
        r3 = ttk.Frame(settings_box)
        r3.pack(fill=tk.X, pady=2)

        ttk.Label(r3, text="Cách Xuất:").pack(side=tk.LEFT)
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

        ttk.Label(r3, text="Định dạng:").pack(side=tk.LEFT)
        ttk.Combobox(
            r3, textvariable=self.format_var, values=["Keep original", "png", "jpg"], state="readonly", width=12
        ).pack(side=tk.LEFT, padx=2)

        # Row 4: Output Folder
        r4 = ttk.Frame(settings_box)
        r4.pack(fill=tk.X, pady=2)
        ttk.Label(r4, text="Thư Mục Xuất:").pack(side=tk.LEFT)
        self.ent_out_folder = ttk.Entry(r4, textvariable=self.output_folder_var)
        self.ent_out_folder.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(r4, text="Chọn...", command=self.on_browse_output_folder).pack(side=tk.LEFT)

        # Actions Toolbar
        action_bar = ttk.Frame(right_frame)
        action_bar.pack(fill=tk.X, pady=(2, 6))

        self.btn_scan = ttk.Button(
            action_bar,
            text="🚀 Quét Ký Tự Hàng Loạt",
            style="Primary.TButton",
            command=self.on_start_extract_characters,
        )
        self.btn_scan.pack(side=tk.LEFT, padx=(0, 5))

        self.btn_review = ttk.Button(
            action_bar,
            text="🎯 Review Focus (Soát & Focus Vị Trí)",
            style="Focus.TButton",
            command=self.on_open_review_focus,
        )
        self.btn_review.pack(side=tk.LEFT, padx=3)

        self.btn_export = ttk.Button(
            action_bar,
            text="📁 Xuất & Đổi Tên Ảnh",
            style="Accent.TButton",
            command=self.on_start_export_images,
        )
        self.btn_export.pack(side=tk.LEFT, padx=3)

        self.btn_csv = ttk.Button(action_bar, text="📊 Xuất Báo Cáo CSV", command=self.on_export_csv)
        self.btn_csv.pack(side=tk.LEFT, padx=3)

        self.btn_cancel = ttk.Button(action_bar, text="⏹️ Dừng", command=self.on_stop_processing, state="disabled")
        self.btn_cancel.pack(side=tk.LEFT, padx=3)

        self.progress_bar = ttk.Progressbar(action_bar, mode="determinate")
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 5))
        self.progress_lbl = ttk.Label(action_bar, text="Sẵn sàng", foreground="#64748b", width=14, anchor="e")
        self.progress_lbl.pack(side=tk.RIGHT)

        # Results Table
        table_frame = ttk.LabelFrame(
            right_frame, text="Bảng Kết Quả & Xem Trước Tên Mới (Nhấp đúp dòng để mở Review Focus)", padding=6
        )
        table_frame.pack(fill=tk.BOTH, expand=True)

        res_cols = ("orig_file", "field", "var_tag", "ocr_text", "new_name", "roi")
        self.res_tree = ttk.Treeview(table_frame, columns=res_cols, show="headings", selectmode="browse")
        self.res_tree.heading("orig_file", text="Tệp Gốc")
        self.res_tree.heading("field", text="Trường")
        self.res_tree.heading("var_tag", text="Tag")
        self.res_tree.heading("ocr_text", text="Ký Tự Trích Xuất (Nhấp đúp để sửa)")
        self.res_tree.heading("new_name", text="Tên File Mới Dự Kiến")
        self.res_tree.heading("roi", text="Vị Trí (ROI)")

        self.res_tree.column("orig_file", width=130, anchor="w")
        self.res_tree.column("field", width=100, anchor="w")
        self.res_tree.column("var_tag", width=45, anchor="center")
        self.res_tree.column("ocr_text", width=200, anchor="w")
        self.res_tree.column("new_name", width=210, anchor="w")
        self.res_tree.column("roi", width=100, anchor="center")

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
        self.status_msg_lbl = ttk.Label(self.status_bar, text="Sẵn sàng", font=("Segoe UI", 8))
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
    # DEMO LOADERS
    # ========================================================================
    def on_load_demo_images(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        demo_dir = os.path.join(base_dir, "sample_images")
        if not os.path.isdir(demo_dir):
            messagebox.showinfo("Demo", "Không tìm thấy thư mục sample_images.")
            return

        self.folder_path = demo_dir
        self.folder_disp_lbl.config(text=demo_dir)

        files = sorted(
            [f for f in os.listdir(demo_dir) if f.lower().endswith(SUPPORTED_EXTENSIONS)],
            key=natural_sort_key,
        )
        if not files:
            messagebox.showinfo("Demo", "Không có tệp ảnh nào trong thư mục sample_images.")
            return

        self.image_files = files
        self.output_folder_var.set(os.path.join(demo_dir, "output"))
        self.sample_combo["values"] = self.image_files
        self.current_sample_idx = 0
        self.sample_combo.current(0)
        self.load_sample_image(self.image_files[0])

        self.rules = [
            {"id": 1, "var": "{o1}", "name": "Mã phiếu", "type": "keyword", "keyword": "Mã phiếu", "pattern": "", "box": None},
            {"id": 2, "var": "{o2}", "name": "Tên hàng", "type": "keyword", "keyword": "Tên hàng", "pattern": "", "box": None},
            {"id": 3, "var": "{o3}", "name": "Trạng thái", "type": "keyword", "keyword": "Trạng thái", "pattern": "", "box": None},
        ]
        self.selected_rule_idx = 0
        self.template_var.set("{o1}_{o2}")
        self._refresh_rule_tree()
        self.redraw_canvas()

        self._update_status("Đã nạp demo phiếu kho thành công!")
        messagebox.showinfo(
            "Demo Nhãn Hàng",
            f"Đã nạp {len(self.image_files)} ảnh demo (gồm cả ảnh bị cắt xén: label_cropped_demo.png)!\n"
            "Quy tắc từ khóa: Mã phiếu ({o1}), Tên hàng ({o2}), Trạng thái ({o3}).\n\n"
            "Bấm '🚀 Quét Ký Tự Hàng Loạt' rồi bấm '🎯 Review Focus' để xem tính năng Focus tự động vào vị trí ký tự!",
        )

    def on_load_glass_demo(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        demo_dir = os.path.join(base_dir, "sample_images")
        if not os.path.isdir(demo_dir):
            messagebox.showinfo("Demo", "Không tìm thấy thư mục sample_images.")
            return

        glass_files = sorted(
            [
                f for f in os.listdir(demo_dir)
                if ("glass" in f.lower() or "faint" in f.lower()) and f.lower().endswith(SUPPORTED_EXTENSIONS)
            ],
            key=natural_sort_key,
        )
        if not glass_files:
            glass_files = sorted(
                [f for f in os.listdir(demo_dir) if f.lower().endswith(SUPPORTED_EXTENSIONS)],
                key=natural_sort_key,
            )

        self.folder_path = demo_dir
        self.folder_disp_lbl.config(text=demo_dir)
        self.image_files = glass_files
        self.output_folder_var.set(os.path.join(demo_dir, "output"))
        self.sample_combo["values"] = self.image_files
        self.current_sample_idx = 0
        self.sample_combo.current(0)
        self.load_sample_image(self.image_files[0])

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

        self._update_status("Đã nạp demo mặt kính GlassID.")
        messagebox.showinfo(
            "Demo GlassID",
            f"Đã nạp {len(self.image_files)} ảnh mặt kính (gồm cả ảnh khắc laser mờ: faint_glass_demo.png)!\n"
            "Quy tắc: GlassID sử dụng Regex '(?i)GlassID\\s*([A-Za-z0-9]+)'.\n"
            "Bộ lọc: CLAHE + Upscale 2x.\n\n"
            "Bấm '🚀 Quét Ký Tự Hàng Loạt' rồi '🎯 Review Focus' để trải nghiệm tính năng Focus phóng to vị trí ký tự!",
        )

    # ========================================================================
    # FOLDER & SAMPLE IMAGE
    # ========================================================================
    def on_choose_folder(self):
        folder = filedialog.askdirectory(title="Chọn Thư Mục Ảnh")
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
            messagebox.showwarning("Không Có Ảnh", f"Không tìm thấy ảnh hợp lệ trong:\n{self.folder_path}")
            return

        self.output_folder_var.set(os.path.join(self.folder_path, "output"))
        self.sample_combo["values"] = self.image_files
        self.current_sample_idx = 0
        self.sample_combo.current(0)
        self.load_sample_image(self.image_files[0])
        self._update_status(f"Đã nạp {len(self.image_files)} ảnh từ {self.folder_path}")

    def load_sample_image(self, filename: str):
        img_path = os.path.join(self.folder_path, filename)
        if not os.path.isfile(img_path):
            return
        try:
            self.sample_image = Image.open(img_path).convert("RGB")
            self.redraw_canvas()
        except Exception as e:
            messagebox.showerror("Lỗi Mở Ảnh", f"Không thể tải ảnh:\n{e}")

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
    # 1-CLICK AUTO-DETECT
    # ========================================================================
    def on_auto_detect_sample_text(self):
        if not self.sample_image:
            messagebox.showinfo("Thông Báo", "Vui lòng chọn hoặc tải ảnh trước.")
            return

        self._update_status("Đang quét ảnh mẫu để nhận diện dòng chữ...")
        engine_name = self.ocr_engine_var.get()

        def worker():
            text_lines = []
            if "Google" in engine_name and HAVE_LENS:
                loop = asyncio.new_event_loop()
                try:
                    raw_text = loop.run_until_complete(run_lens_full_text(self.sample_image))
                    text_lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
                except Exception as e:
                    print("Auto detect error:", e)
                finally:
                    loop.close()
            elif HAVE_RAPIDOCR:
                raw_text, ocr_results = run_rapidocr(self.sample_image)
                if ocr_results:
                    text_lines = [line[1].strip() for line in ocr_results]

            self.root.after(0, self._show_detected_text_dialog, text_lines)

        threading.Thread(target=worker, daemon=True).start()

    def _show_detected_text_dialog(self, text_lines):
        self._update_status("Đã nhận diện xong text ảnh mẫu.")
        if not text_lines:
            messagebox.showinfo("Nhận Diện", "Không tìm thấy văn bản nào trong ảnh mẫu.")
            return

        win = tk.Toplevel(self.root)
        win.title("Nhấp Để Tạo Quy Tắc Nhanh")
        win.geometry("520x450")
        win.transient(self.root)

        ttk.Label(
            win,
            text="Các dòng chữ nhận diện được trong ảnh:\nNhấp vào dòng bất kỳ để tạo Quy Tắc Từ Khóa:",
            font=("Segoe UI", 10, "bold"),
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
            messagebox.showinfo("Đã Thêm Quy Tắc", f"Đã thêm quy tắc: '{kw}' (Tag: {{o{new_idx}}})")

        btn_box = ttk.Frame(win)
        btn_box.pack(fill=tk.X, padx=12, pady=10)
        ttk.Button(btn_box, text="➕ Thêm Thành Quy Tắc Keyword", style="Primary.TButton", command=add_selected_line).pack(side=tk.LEFT)
        ttk.Button(btn_box, text="Đóng", command=win.destroy).pack(side=tk.RIGHT)

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
                text="Vui lòng chọn thư mục hoặc nhấp 'Demo'",
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
            crit = (
                r["keyword"]
                if r["type"] == "keyword"
                else (r["pattern"] if r["type"] == "regex" else str(r.get("box", "")))
            )
            iid = self.rule_tree.insert(
                "", "end", values=(r["id"], r["var"], r["name"], r["type"].upper(), crit)
            )
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
        name = self.ent_rule_name.get().strip() or "Trường"
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
        if messagebox.askyesno("Xóa Quy Tắc", "Bạn có chắc chắn muốn xóa toàn bộ quy tắc?"):
            self.rules.clear()
            self.selected_rule_idx = -1
            self._refresh_rule_tree()
            self.redraw_canvas()

    def on_save_config(self):
        fpath = filedialog.asksaveasfilename(
            title="Lưu Quy Tắc Trích Xuất", defaultextension=".json", filetypes=[("JSON Files", "*.json")]
        )
        if fpath:
            cfg = {"rules": self.rules, "template": self.template_var.get()}
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Đã Lưu", f"Đã lưu quy tắc vào:\n{fpath}")

    def on_load_config(self):
        fpath = filedialog.askopenfilename(
            title="Nạp Quy Tắc Trích Xuất", filetypes=[("JSON Files", "*.json")]
        )
        if fpath:
            with open(fpath, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if "rules" in cfg:
                self.rules = cfg["rules"]
            if "template" in cfg:
                self.template_var.set(cfg["template"])
            self._refresh_rule_tree()
            self.redraw_canvas()
            messagebox.showinfo("Đã Nạp", "Đã nạp quy tắc thành công!")

    def on_browse_output_folder(self):
        folder = filedialog.askdirectory(title="Chọn Thư Mục Xuất")
        if folder:
            self.output_folder_var.set(os.path.abspath(folder))

    # ========================================================================
    # BATCH SCAN WORKERS
    # ========================================================================
    def on_start_extract_characters(self):
        if not self.image_files:
            messagebox.showwarning("Chưa Có Ảnh", "Vui lòng chọn thư mục ảnh hoặc nhấp 'Demo' trước.")
            return

        if not self.rules:
            messagebox.showwarning("Chưa Có Quy Tắc", "Vui lòng thêm ít nhất một quy tắc trích xuất.")
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
            self._update_status("Đang dừng tiến trình... Xin vui lòng đợi.")

    def _extract_worker(self):
        chosen_engine = self.ocr_engine_var.get()
        if "Google" in chosen_engine and HAVE_LENS:
            asyncio.run(self._async_google_worker())
        elif HAVE_RAPIDOCR:
            self._sync_rapidocr_worker()
        else:
            self.root.after(0, messagebox.showerror, "Lỗi Engine", "Không tìm thấy OCR engine khả dụng.")
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
                self.root.after(0, self._update_status, f"Đang quét Google Lens ({img_idx + 1}/{total_images}): {filename}...")

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
                    full_text = await run_lens_full_text(img, lens_api=lens)
                except Exception as e:
                    print(f"Google OCR error on {filename}: {e}", file=sys.stderr)
                    full_text = ""

                image_ocr_texts = []
                image_bboxes = []
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

                    # Compute or auto-detect bbox
                    b = auto_detect_bbox_for_image(
                        raw_img,
                        r,
                        extracted,
                        prep_mode=self.preprocess_mode_var.get(),
                        upscale=self.upscale_2x_var.get(),
                    )
                    image_bboxes.append(b)

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
                        "bbox": image_bboxes[r_idx],
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
            self.root.after(0, self._update_status, f"Đang quét RapidOCR ({img_idx + 1}/{total_images}): {filename}...")

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
                full_text, ocr_results = run_rapidocr(img, engine=engine)
            except Exception as e:
                print(f"RapidOCR error on {filename}: {e}", file=sys.stderr)
                full_text, ocr_results = "", []

            image_ocr_texts = []
            image_bboxes = []
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

                # Locate bounding box on original image
                b = find_bounding_box_for_rule(
                    ocr_results,
                    r,
                    extracted,
                    orig_size=raw_img.size,
                    proc_size=img.size,
                )
                image_bboxes.append(b)

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
                    "bbox": image_bboxes[r_idx],
                }
                self.results_data.append(row_data)
                self.root.after(0, self._insert_tree_row, row_data)

        self.root.after(0, self._on_scan_finished)

    def _insert_tree_row(self, row: dict):
        b = row.get("bbox")
        roi_str = f"[{b[0]},{b[1]},{b[2]},{b[3]}]" if b else "Toàn cảnh"
        self.res_tree.insert(
            "",
            "end",
            values=(
                row["orig_file"],
                row["field"],
                row["var_tag"],
                row["ocr_text"],
                row["new_name"],
                roi_str,
            ),
        )

    def _update_progress(self, pct: int, text: str):
        self.progress_bar["value"] = pct
        self.progress_lbl.config(text=text)

    def _on_scan_finished(self):
        self.is_processing = False
        self._toggle_ui_state(True)
        self.progress_bar["value"] = 100
        status_txt = "Đã dừng bởi người dùng." if self.stop_requested else "Hoàn tất quét hàng loạt!"
        self.progress_lbl.config(text="Xong" if not self.stop_requested else "Đã dừng")
        self._update_status(status_txt)
        messagebox.showinfo(
            "Quét Hoàn Tất",
            f"{status_txt}\nĐã xử lý {len(self.image_files)} tệp ảnh.\n\n"
            "💡 MẸO: Nhấp nút '🎯 Review Focus (Soát & Focus Vị Trí)' hoặc nhấp đúp vào dòng để kiểm tra, phóng to vị trí ký tự và chỉnh sửa nhanh!",
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
                "Chưa có dữ liệu trích xuất. Vui lòng bấm '🚀 Quét Ký Tự Hàng Loạt' trước khi soát lỗi.",
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
            messagebox.showinfo("Xuất CSV", "Không có dữ liệu. Vui lòng quét ký tự trước.")
            return

        fpath = filedialog.asksaveasfilename(
            title="Lưu Báo Cáo CSV", defaultextension=".csv", filetypes=[("CSV Files", "*.csv")]
        )
        if not fpath:
            return

        try:
            with open(fpath, "w", newline="", encoding="utf-8-sig") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Tệp Gốc", "Trường", "Tag", "Ký Tự Trích Xuất", "Tên Tệp Mới", "Tọa Độ ROI"])
                for row in self.results_data:
                    b = row.get("bbox")
                    roi_str = f"{b[0]},{b[1]},{b[2]},{b[3]}" if b else ""
                    writer.writerow([row["orig_file"], row["field"], row["var_tag"], row["ocr_text"], row["new_name"], roi_str])
            messagebox.showinfo("Xuất CSV Thành Công", f"Đã lưu tệp báo cáo vào:\n{fpath}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể ghi tệp CSV:\n{e}")

    def on_start_export_images(self):
        if not self.image_files or not self.results_data:
            messagebox.showwarning("Thông Báo", "Vui lòng quét ký tự trước khi xuất đổi tên.")
            return

        out_folder = self.output_folder_var.get().strip()
        if not out_folder:
            out_folder = os.path.join(self.folder_path, "output")
            self.output_folder_var.set(out_folder)

        try:
            os.makedirs(out_folder, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể tạo thư mục xuất:\n{e}")
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
            self.root.after(0, self._update_status, f"Đang xuất ({idx + 1}/{total}): {filename}...")

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
        self.progress_lbl.config(text="Đã xuất xong")
        status_txt = "Đã hủy xuất." if self.stop_requested else f"Hoàn tất xuất ảnh vào {out_folder}"
        self._update_status(status_txt)

        if not self.stop_requested:
            res = messagebox.askyesno(
                "Xuất Hoàn Tất",
                f"Đã xuất thành công các tệp ảnh đổi tên vào:\n{out_folder}\n\nBạn có muốn mở thư mục ngay bây giờ?",
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
