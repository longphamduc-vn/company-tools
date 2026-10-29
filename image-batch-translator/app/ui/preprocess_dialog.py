#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Preprocess Test & Tuning Dialog.
Interactive preview and test scan dialog for image preprocessing algorithms
(CLAHE, Invert, Otsu binarization, Lanczos 2x upscale) with side-by-side comparison.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

from ..config import PREPROCESS_MODES, HAVE_CV2, HAVE_RAPIDOCR, HAVE_LENS
from ..ocr_engine import preprocess_for_ocr, run_rapidocr, run_lens_full_text
from ..extraction import extract_by_keyword, extract_by_pattern, extract_by_box


class PreprocessTestDialog:
    """Interactive preview and test scan dialog for image preprocessing algorithms."""

    def __init__(self, parent: tk.Tk, app):
        self.parent = parent
        self.app = app
        self.win = tk.Toplevel(parent)
        self.win.title("🧪 Image Preprocessing & OCR Test Tuning")
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

        ttk.Label(top, text="Select Image:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self.img_combo = ttk.Combobox(top, values=self.app.image_files, state="readonly", width=24)
        if self.app.image_files:
            self.img_combo.current(self.current_img_idx)
        self.img_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.img_combo.bind("<<ComboboxSelected>>", self._on_image_selected)

        ttk.Label(top, text="Filter Mode:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(5, 4))
        self.mode_combo = ttk.Combobox(
            top, textvariable=self.mode_var, values=PREPROCESS_MODES, state="readonly", width=34
        )
        self.mode_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self._update_preprocessed_preview())

        ttk.Checkbutton(
            top, text="Upscale 2x", variable=self.upscale_var, command=self._update_preprocessed_preview
        ).pack(side=tk.LEFT, padx=(0, 10))

        btn_run_test = ttk.Button(top, text="⚡ Run OCR Test", style="Primary.TButton", command=self._run_test_scan)
        btn_run_test.pack(side=tk.LEFT, padx=5)

        # Center: Side-by-side Image Previews
        preview_paned = ttk.PanedWindow(self.win, orient=tk.HORIZONTAL)
        preview_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Left: Original
        f_left = ttk.LabelFrame(preview_paned, text="Original Image", padding=5)
        preview_paned.add(f_left, weight=1)
        self.lbl_orig = ttk.Label(f_left, text="No Image", anchor="center", background="#0f172a")
        self.lbl_orig.pack(fill=tk.BOTH, expand=True)

        # Right: Preprocessed
        f_right = ttk.LabelFrame(preview_paned, text="Preprocessed Image", padding=5)
        preview_paned.add(f_right, weight=1)
        self.lbl_prep = ttk.Label(f_right, text="No Image", anchor="center", background="#0f172a")
        self.lbl_prep.pack(fill=tk.BOTH, expand=True)

        # Bottom: OCR Test Results & Actions
        res_frame = ttk.LabelFrame(self.win, text="OCR Test Scan & Extraction Output", padding=8)
        res_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

        self.txt_ocr_output = tk.Text(
            res_frame, height=5, font=("Consolas", 10), wrap="word", bg="#f8fafc", relief="solid", borderwidth=1
        )
        self.txt_ocr_output.pack(fill=tk.X, expand=True, side=tk.TOP, pady=(0, 6))

        bot_bar = ttk.Frame(self.win, padding="10 8")
        bot_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.lbl_status = ttk.Label(
            bot_bar, text="Select a filter mode and click '⚡ Run OCR Test' to inspect results.", font=("Segoe UI", 9, "italic")
        )
        self.lbl_status.pack(side=tk.LEFT)

        ttk.Button(bot_bar, text="Close", command=self.win.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(
            bot_bar, text="✅ Apply This Configuration", style="Accent.TButton", command=self._apply_and_close
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
            self.lbl_status.config(text=f"Error opening image: {e}")

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
            self.lbl_status.config(text=f"Preprocessing error: {e}")

    def _run_test_scan(self):
        if not self.prep_image:
            return
        self.lbl_status.config(text="Running OCR test... Please wait...")
        self.txt_ocr_output.delete("1.0", tk.END)
        self.txt_ocr_output.insert(tk.END, "⏳ Running OCR test on preprocessed image...\n")

        engine_name = self.app.ocr_engine_var.get()

        def worker():
            import time

            t0 = time.time()
            full_text = ""
            lines = []
            if "Google" in engine_name and HAVE_LENS:
                import asyncio
                loop = asyncio.new_event_loop()
                try:
                    full_text = loop.run_until_complete(run_lens_full_text(self.prep_image))
                    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
                except Exception as e:
                    full_text = f"Google OCR error: {e}"
                finally:
                    loop.close()
            elif HAVE_RAPIDOCR:
                full_text, ocr_results = run_rapidocr(self.prep_image)
                if ocr_results:
                    lines = [line[1].strip() for line in ocr_results]
            else:
                full_text = "No available OCR engine detected."

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
            f"⏱️ Scan completed in {elapsed}s | Filter: {self.mode_var.get()} | Upscale 2x: {self.upscale_var.get()}"
        )
        out.append("-" * 70)
        out.append("🎯 EXTRACTED DATA BY RULES:")
        if extracted_summary:
            out.extend(extracted_summary)
        else:
            out.append("  (No rules defined)")
        out.append("-" * 70)
        out.append("📄 FULL RECOGNIZED OCR TEXT:")
        out.append(full_text if full_text.strip() else "(No text detected)")
        self.txt_ocr_output.insert(tk.END, "\n".join(out))
        self.lbl_status.config(text=f"✅ Scan finished in {elapsed}s.")

    def _apply_and_close(self):
        self.app.preprocess_mode_var.set(self.mode_var.get())
        self.app.upscale_2x_var.set(self.upscale_var.get())
        self.win.destroy()
        messagebox.showinfo(
            "Configuration Applied",
            f"Applied preprocessing filter: {self.mode_var.get()}\nUpscale 2x: {self.upscale_var.get()}",
        )
