#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Review Focus Dialog (Human-in-the-Loop Quick Verification & ROI Focus).
100% English UI, keyboard-first navigation, instant zero-lag ROI focus.
"""

import os
import re
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

from ..config import HAVE_LENS, HAVE_RAPIDOCR
from ..utils import compute_filename
from ..ocr_engine import preprocess_for_ocr, run_rapidocr, run_lens_full_text
from ..extraction import extract_by_keyword, extract_by_pattern


class ReviewFocusDialog:
    """
    Dedicated Human-in-the-Loop Review & Focus Dialog.
    Enables rapid manual verification and correction of OCR extraction outputs
    with keyboard shortcuts (Enter = Save & Next, Ctrl+Left = Prev, Esc = Close)
    and instant ROI Focus into exact character coordinates with zero lag.
    """

    def __init__(self, parent: tk.Tk, app, target_img_idx: int = None, target_rule_idx: int = None):
        self.parent = parent
        self.app = app
        self.win = tk.Toplevel(parent)
        self.win.title("🎯 Review Focus - Inspection & Manual Correction")
        self.win.geometry("1180x760")
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

        self.active_rule_idx = target_rule_idx if target_rule_idx is not None else 0
        self.filter_issues_only_var = tk.BooleanVar(value=False)
        self.focus_mode_var = tk.BooleanVar(value=True)  # Auto-focus ROI enabled by default
        self.zoom_factor = 1.0

        # Debounce canvas resize to prevent GUI lag
        self._last_cw = 0
        self._last_ch = 0

        # Manual Focus Drag State & Canvas Mapping
        self._drag_start = None
        self._drag_rect_id = None
        self._canvas_mapping = {}

        self.field_entries = []  # list of (row_dict, ttk.Entry, lbl_status, rule_dict)
        self.current_pil_img = None
        self.current_tk_img = None

        self._build_ui()
        self._load_current_image_data()
        self._bind_keys()
        self.win.protocol("WM_DELETE_WINDOW", self.on_close)

    def _bind_keys(self):
        self.win.bind("<Return>", lambda e: self.on_save_and_next())
        self.win.bind("<Control-Left>", lambda e: self.on_prev())
        self.win.bind("<Alt-Left>", lambda e: self.on_prev())
        self.win.bind("<Control-Right>", lambda e: self.on_save_and_next())
        self.win.bind("<Alt-Right>", lambda e: self.on_save_and_next())
        self.win.bind("<Escape>", lambda e: self.on_close())

    def _build_ui(self):
        # Top Header Bar (100% English UI)
        top_bar = ttk.Frame(self.win, padding="10 8")
        top_bar.pack(side=tk.TOP, fill=tk.X)

        self.btn_prev = ttk.Button(top_bar, text="◀ Prev (Ctrl+←)", command=self.on_prev)
        self.btn_prev.pack(side=tk.LEFT, padx=3)

        self.lbl_progress = ttk.Label(
            top_bar, text="Image 1 / 1", font=("Segoe UI", 12, "bold"), foreground="#1e293b"
        )
        self.lbl_progress.pack(side=tk.LEFT, padx=12)

        self.btn_next = ttk.Button(
            top_bar, text="Next ▶ (Enter / Ctrl+→)", style="Primary.TButton", command=self.on_save_and_next
        )
        self.btn_next.pack(side=tk.LEFT, padx=3)

        ttk.Separator(top_bar, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=15)

        chk_filter = ttk.Checkbutton(
            top_bar,
            text="⚠️ Show errors & empty only (Filter Suspect/Empty)",
            variable=self.filter_issues_only_var,
            command=self._on_filter_toggled,
        )
        chk_filter.pack(side=tk.LEFT, padx=5)

        ttk.Button(top_bar, text="Close (Esc)", command=self.on_close).pack(side=tk.RIGHT, padx=5)

        # Paned Window (Left: Image Preview & Focus, Right: Editable Fields & Live Output)
        paned = ttk.PanedWindow(self.win, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        # Left: Image Viewer with Focus Controls
        left_box = ttk.LabelFrame(paned, text="Visual Inspection & Focus (Visual Check)", padding=6)
        paned.add(left_box, weight=6)

        # Focus Viewport Toolbar
        f_tool = ttk.Frame(left_box, padding="2 2")
        f_tool.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))

        chk_focus = ttk.Checkbutton(
            f_tool,
            text="🎯 Focus Position",
            variable=self.focus_mode_var,
            command=self._draw_image_on_canvas,
        )
        chk_focus.pack(side=tk.LEFT, padx=2)

        ttk.Button(f_tool, text="🖼️ Full Image", command=self._show_full_view).pack(side=tk.LEFT, padx=2)
        ttk.Separator(f_tool, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=4)

        ttk.Button(f_tool, text="⚡ Scan ROI", style="Accent.TButton", command=self.on_scan_selected_roi).pack(side=tk.LEFT, padx=2)
        ttk.Button(f_tool, text="🔄 Reset Box", command=self._on_reset_box).pack(side=tk.LEFT, padx=2)
        ttk.Separator(f_tool, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=4)

        ttk.Button(f_tool, text="🔍 +", width=3, command=self._zoom_in).pack(side=tk.LEFT, padx=1)
        ttk.Button(f_tool, text="🔍 -", width=3, command=self._zoom_out).pack(side=tk.LEFT, padx=1)
        ttk.Button(f_tool, text="1:1", width=3, command=self._zoom_reset).pack(side=tk.LEFT, padx=1)

        self.lbl_focus_info = ttk.Label(
            f_tool, text="", font=("Segoe UI", 9, "bold"), foreground="#0284c7"
        )
        self.lbl_focus_info.pack(side=tk.RIGHT, padx=4)

        # Canvas with crosshair cursor for intuitive drag-selection
        self.canvas_img = tk.Canvas(left_box, bg="#0f172a", highlightthickness=0, cursor="crosshair")
        self.canvas_img.pack(fill=tk.BOTH, expand=True)
        self.canvas_img.bind("<Configure>", self._on_canvas_configure)
        self.canvas_img.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas_img.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas_img.bind("<ButtonRelease-1>", self._on_canvas_release)

        # Right: Fields & Filename (100% English UI)
        right_box = ttk.LabelFrame(paned, text="Extracted Characters & Quick Edit (Keyboard-First)", padding=10)
        paned.add(right_box, weight=5)

        self.lbl_filename = ttk.Label(
            right_box, text="File: sample.png", font=("Segoe UI", 10, "bold"), foreground="#2563eb"
        )
        self.lbl_filename.pack(anchor="w", pady=(0, 8))

        # Container for dynamic field entries
        self.fields_container = ttk.Frame(right_box)
        self.fields_container.pack(fill=tk.BOTH, expand=True)

        # Live Filename Preview Box
        preview_box = ttk.LabelFrame(right_box, text="🏷️ New Filename Live Preview", padding=8)
        preview_box.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

        self.lbl_new_name_preview = ttk.Label(
            preview_box, text="", font=("Segoe UI", 11, "bold"), foreground="#059669", wraplength=420
        )
        self.lbl_new_name_preview.pack(fill=tk.X, pady=3)

        tip_lbl = ttk.Label(
            right_box,
            text="💡 Tip: Press Enter to Save and jump immediately to the next image!\nClick or Tab into an input field to auto-focus on text position.",
            font=("Segoe UI", 8, "italic"),
            foreground="#64748b",
            wraplength=420,
        )
        tip_lbl.pack(side=tk.BOTTOM, anchor="w", pady=(5, 0))

    def _show_full_view(self):
        self.focus_mode_var.set(False)
        self.zoom_factor = 1.0
        self._draw_image_on_canvas()

    def _zoom_in(self):
        self.zoom_factor = min(4.0, self.zoom_factor * 1.25)
        self._draw_image_on_canvas()

    def _zoom_out(self):
        self.zoom_factor = max(0.5, self.zoom_factor / 1.25)
        self._draw_image_on_canvas()

    def _zoom_reset(self):
        self.zoom_factor = 1.0
        self._draw_image_on_canvas()

    def _on_canvas_configure(self, event):
        cw = event.width
        ch = event.height
        if abs(cw - self._last_cw) > 5 or abs(ch - self._last_ch) > 5:
            self._last_cw = cw
            self._last_ch = ch
            self._draw_image_on_canvas()

    def _set_active_field(self, rule_idx: int):
        self.active_rule_idx = rule_idx
        self._draw_image_on_canvas()

    def _draw_image_on_canvas(self):
        if not self.current_pil_img:
            return

        cw = max(100, self.canvas_img.winfo_width())
        ch = max(100, self.canvas_img.winfo_height())
        iw, ih = self.current_pil_img.size

        # Identify active row data (Instant in-memory lookup)
        active_row = None
        for row_item, _, _, _ in self.field_entries:
            if row_item.get("rule_idx") == self.active_rule_idx:
                active_row = row_item
                break
        if not active_row and self.field_entries:
            active_row = self.field_entries[0][0]

        bbox = active_row.get("bbox") if active_row else None

        self.canvas_img.delete("all")

        # CASE 1: FOCUS MODE (Instant ROI Zoom & Neon Frame from RAM)
        if self.focus_mode_var.get() and bbox:
            bx1, by1, bx2, by2 = bbox
            bw = max(1, bx2 - bx1)
            bh = max(1, by2 - by1)

            pad_x = max(60, int(bw * 0.75))
            pad_y = max(40, int(bh * 1.3))

            cx1 = max(0, bx1 - pad_x)
            cy1 = max(0, by1 - pad_y)
            cx2 = min(iw, bx2 + pad_x)
            cy2 = min(ih, by2 + pad_y)

            crop_w = cx2 - cx1
            crop_h = cy2 - cy1

            if crop_w > 0 and crop_h > 0:
                roi_img = self.current_pil_img.crop((cx1, cy1, cx2, cy2))

                base_scale = min(cw / crop_w, ch / crop_h) * 0.90
                scale = base_scale * self.zoom_factor
                nw = max(1, int(crop_w * scale))
                nh = max(1, int(crop_h * scale))

                resized = roi_img.resize((nw, nh), Image.Resampling.BILINEAR)
                self.current_tk_img = ImageTk.PhotoImage(resized)

                ox = (cw - nw) // 2
                oy = (ch - nh) // 2
                self.canvas_img.create_image(ox, oy, anchor=tk.NW, image=self.current_tk_img)

                # Store mapping for mouse interactions
                self._canvas_mapping = {
                    "ox": ox, "oy": oy, "scale": scale,
                    "cx1": cx1, "cy1": cy1, "iw": iw, "ih": ih,
                    "mode": "focus",
                }

                # Map text box coordinates to canvas with padding
                bw = max(1, bx2 - bx1)
                bh = max(1, by2 - by1)
                pad_box_x = max(5, int(bw * 0.08 * scale))
                pad_box_y = max(4, int(bh * 0.12 * scale))

                tb_x1 = ox + (bx1 - cx1) * scale - pad_box_x
                tb_y1 = oy + (by1 - cy1) * scale - pad_box_y
                tb_x2 = ox + (bx2 - cx1) * scale + pad_box_x
                tb_y2 = oy + (by2 - cy1) * scale + pad_box_y

                # Neon Outer & Inner Rectangles with padding
                self.canvas_img.create_rectangle(
                    tb_x1 - 2, tb_y1 - 2, tb_x2 + 2, tb_y2 + 2, outline="#0284c7", width=3
                )
                self.canvas_img.create_rectangle(
                    tb_x1, tb_y1, tb_x2, tb_y2, outline="#10b981", width=2
                )

                # Floating Badge above Box
                badge_type = "✂️ Manual Focus" if active_row.get("manual_bbox") else "🎯 Auto Focus"
                tag_text = f"{badge_type}: {active_row.get('ocr_text', '')}"
                self.canvas_img.create_rectangle(
                    tb_x1, tb_y1 - 24, tb_x1 + len(tag_text) * 8 + 14, tb_y1 - 3,
                    fill="#0f172a", outline="#0284c7", width=1
                )
                self.canvas_img.create_text(
                    tb_x1 + 6, tb_y1 - 13,
                    text=tag_text, anchor="w", fill="#38bdf8", font=("Segoe UI", 9, "bold")
                )

                self.lbl_focus_info.config(
                    text=f"🎯 Focus: {active_row.get('field')} ({int(scale * 100)}%) | Drag on image to adjust box",
                    foreground="#10b981",
                )
                return

        # CASE 2: FULL IMAGE VIEW (or when bbox is not available)
        base_scale = min(cw / max(1, iw), ch / max(1, ih)) * 0.96
        scale = base_scale * self.zoom_factor
        nw = max(1, int(iw * scale))
        nh = max(1, int(ih * scale))

        resized = self.current_pil_img.resize((nw, nh), Image.Resampling.BILINEAR)
        self.current_tk_img = ImageTk.PhotoImage(resized)

        ox = (cw - nw) // 2
        oy = (ch - nh) // 2
        self.canvas_img.create_image(ox, oy, anchor=tk.NW, image=self.current_tk_img)

        # Store mapping for mouse interactions
        self._canvas_mapping = {
            "ox": ox, "oy": oy, "scale": scale,
            "cx1": 0, "cy1": 0, "iw": iw, "ih": ih,
            "mode": "full",
        }

        # Highlight boxes for fields on full image with padding
        for row_item, _, _, _ in self.field_entries:
            b = row_item.get("bbox")
            if b:
                is_active = (row_item.get("rule_idx") == self.active_rule_idx)
                bw = max(1, b[2] - b[0])
                bh = max(1, b[3] - b[1])
                pad_box_x = max(3, int(bw * 0.08 * scale))
                pad_box_y = max(2, int(bh * 0.12 * scale))
                rx1 = ox + b[0] * scale - pad_box_x
                ry1 = oy + b[1] * scale - pad_box_y
                rx2 = ox + b[2] * scale + pad_box_x
                ry2 = oy + b[3] * scale + pad_box_y

                color = "#10b981" if is_active else "#64748b"
                width = 3 if is_active else 1
                self.canvas_img.create_rectangle(rx1, ry1, rx2, ry2, outline=color, width=width)

        if not bbox and active_row:
            self.lbl_focus_info.config(
                text="💡 No position detected! Click & drag on image to set Manual Focus Box",
                foreground="#f59e0b",
            )
        else:
            self.lbl_focus_info.config(text="🖼️ Full View (Drag on image to create focus box)", foreground="#0284c7")

    def _get_active_row(self):
        for row_item, _, _, _ in self.field_entries:
            if row_item.get("rule_idx") == self.active_rule_idx:
                return row_item
        if self.field_entries:
            return self.field_entries[0][0]
        return None

    def _canvas_to_img_coords(self, cx, cy):
        m = self._canvas_mapping
        if not m:
            return 0, 0
        scale = max(1e-6, m.get("scale", 1.0))
        ox, oy = m.get("ox", 0), m.get("oy", 0)
        cx1, cy1 = m.get("cx1", 0), m.get("cy1", 0)
        img_x = int(round(cx1 + (cx - ox) / scale))
        img_y = int(round(cy1 + (cy - oy) / scale))
        img_x = max(0, min(m.get("iw", 1000), img_x))
        img_y = max(0, min(m.get("ih", 1000), img_y))
        return img_x, img_y

    def _on_canvas_press(self, event):
        if not self.current_pil_img:
            return
        self._drag_start = (event.x, event.y)
        if self._drag_rect_id:
            try:
                self.canvas_img.delete(self._drag_rect_id)
            except Exception:
                pass
            self._drag_rect_id = None

    def _on_canvas_drag(self, event):
        if not self._drag_start:
            return
        x0, y0 = self._drag_start
        x1, y1 = event.x, event.y
        if not self._drag_rect_id:
            self._drag_rect_id = self.canvas_img.create_rectangle(
                x0, y0, x1, y1, outline="#f59e0b", width=2, dash=(4, 2)
            )
        else:
            self.canvas_img.coords(self._drag_rect_id, x0, y0, x1, y1)

    def _on_canvas_release(self, event):
        if not self._drag_start:
            return
        x0, y0 = self._drag_start
        x1, y1 = event.x, event.y
        self._drag_start = None
        if self._drag_rect_id:
            try:
                self.canvas_img.delete(self._drag_rect_id)
            except Exception:
                pass
            self._drag_rect_id = None

        if abs(x1 - x0) >= 10 and abs(y1 - y0) >= 8:
            ix0, iy0 = self._canvas_to_img_coords(x0, y0)
            ix1, iy1 = self._canvas_to_img_coords(x1, y1)
            bx1, bx2 = min(ix0, ix1), max(ix0, ix1)
            by1, by2 = min(iy0, iy1), max(iy0, iy1)

            if (bx2 - bx1) >= 5 and (by2 - by1) >= 5:
                active_row = self._get_active_row()
                if active_row:
                    active_row["bbox"] = [bx1, by1, bx2, by2]
                    active_row["manual_bbox"] = True
                    self.focus_mode_var.set(True)
                    self._draw_image_on_canvas()
                    self.lbl_focus_info.config(
                        text=f"✂️ Manual Box set: [{bx1},{by1},{bx2},{by2}] | Click '⚡ Scan ROI' or edit text",
                        foreground="#f59e0b",
                    )

    def on_scan_selected_roi(self):
        """Runs OCR on the currently focused or manually drawn ROI."""
        active_row = self._get_active_row()
        if not active_row or not self.current_pil_img:
            return
        bbox = active_row.get("bbox")
        if not bbox:
            messagebox.showinfo("Scan ROI", "Please drag a box on the image first to define text ROI.")
            return

        bx1, by1, bx2, by2 = bbox
        if (bx2 - bx1) < 5 or (by2 - by1) < 5:
            return

        crop_img = self.current_pil_img.crop((bx1, by1, bx2, by2))
        prep_crop = preprocess_for_ocr(crop_img, mode=self.app.preprocess_mode_var.get(), upscale=True)

        self.lbl_focus_info.config(text="⏳ Scanning selected ROI...", foreground="#0284c7")
        self.win.update_idletasks()

        rule_idx = active_row.get("rule_idx", 0)
        rule = self.app.rules[rule_idx] if rule_idx < len(self.app.rules) else None
        engine_name = self.app.ocr_engine_var.get()

        def do_scan():
            detected_text = ""
            full_text = ""
            try:
                if "Google" in engine_name and HAVE_LENS:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    try:
                        full_text = loop.run_until_complete(run_lens_full_text(prep_crop))
                    except Exception as e:
                        print("Lens crop scan error:", e)
                    finally:
                        loop.close()
                elif HAVE_RAPIDOCR:
                    full_text, _ = run_rapidocr(prep_crop)

                if rule and rule.get("type") == "regex" and rule.get("pattern"):
                    detected_text = extract_by_pattern(full_text, rule["pattern"])
                elif rule and rule.get("type") == "keyword" and rule.get("keyword"):
                    detected_text = extract_by_keyword(full_text, rule["keyword"])

                if not detected_text and full_text.strip():
                    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
                    if lines:
                        detected_text = lines[0]
            except Exception as e:
                print("Error scanning ROI:", e)

            def on_done():
                if detected_text:
                    for r_item, ent, status_lbl, r_rule in self.field_entries:
                        if r_item is active_row:
                            ent.delete(0, tk.END)
                            ent.insert(0, detected_text)
                            active_row["manual_edited"] = True
                            active_row["ocr_text"] = detected_text
                            self.lbl_focus_info.config(
                                text=f"✅ ROI Scan Succeeded: '{detected_text}'",
                                foreground="#10b981",
                            )
                            self._update_live_filename_preview()
                            break
                else:
                    self.lbl_focus_info.config(
                        text="⚠️ No text detected in selection. Type text manually below.",
                        foreground="#dc2626",
                    )

            self.win.after(0, on_done)

        import threading
        threading.Thread(target=do_scan, daemon=True).start()

    def _on_reset_box(self):
        active_row = self._get_active_row()
        if active_row:
            active_row["bbox"] = None
            active_row["manual_bbox"] = False
        self.focus_mode_var.set(False)
        self._draw_image_on_canvas()
        self.lbl_focus_info.config(text="🔄 Box reset to full view. Drag on image to create new box.", foreground="#64748b")

    def _load_current_image_data(self):
        if not self.unique_image_indices:
            return

        img_idx = self.unique_image_indices[self.current_idx_pointer]
        orig_filename = self.app.image_files[img_idx]

        total = len(self.unique_image_indices)
        self.lbl_progress.config(text=f"Image {self.current_idx_pointer + 1} / {total}")
        self.lbl_filename.config(text=f"File: {orig_filename}")

        # 1. Load Image
        img_path = os.path.join(self.app.folder_path, orig_filename)
        if os.path.isfile(img_path):
            try:
                self.current_pil_img = Image.open(img_path).convert("RGB")
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

            # Auto-focus ROI when user clicks or tabs into this Entry!
            def make_focus_cb(r_id):
                return lambda event: self._set_active_field(r_id)

            ent.bind("<FocusIn>", make_focus_cb(rule_idx))

            # Bind key release to update status & filename preview live
            def make_edit_cb(entry, status, rule_ref, row_ref):
                def callback(event=None):
                    val = entry.get().strip()
                    row_ref["ocr_text"] = val
                    if not val:
                        status.config(text="⚠️ EMPTY", foreground="#dc2626")
                    elif rule_ref and rule_ref.get("type") == "regex" and rule_ref.get("pattern"):
                        try:
                            if re.search(rule_ref["pattern"], val):
                                status.config(text="✅ VALID", foreground="#059669")
                            else:
                                status.config(text="⚠️ PATTERN MISMATCH", foreground="#d97706")
                        except Exception:
                            status.config(text="✅ ENTERED", foreground="#059669")
                    else:
                        status.config(text="✅ PRESENT", foreground="#059669")
                    self._update_live_filename_preview()

                return callback

            cb = make_edit_cb(ent, status_lbl, rule, row_item)
            ent.bind("<KeyRelease>", cb)
            cb()

            self.field_entries.append((row_item, ent, status_lbl, rule))

            if focused_entry is None or (
                self.active_rule_idx is not None and rule_idx == self.active_rule_idx
            ):
                focused_entry = ent

        self._draw_image_on_canvas()

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

        # Real-time synchronization to main window results table!
        for row_item, ent, _, _ in self.field_entries:
            row_item["ocr_text"] = ent.get().strip()
        self.app._recalculate_filenames_for_image(orig_filename, img_idx)

    def save_current_edits(self):
        """Commits all currently displayed field edits to results_data and updates the main table."""
        if not self.unique_image_indices or not self.field_entries:
            return
        img_idx = self.unique_image_indices[self.current_idx_pointer]
        orig_filename = self.app.image_files[img_idx]
        for row_item, ent, _, _ in self.field_entries:
            row_item["ocr_text"] = ent.get().strip()
        self.app._recalculate_filenames_for_image(orig_filename, img_idx)

    def on_close(self):
        """Saves current edits before closing dialog and refreshes results table."""
        self.save_current_edits()
        if hasattr(self.app, "refresh_results_tree"):
            self.app.refresh_results_tree()
        self.win.destroy()

    def on_save_and_next(self):
        if not self.unique_image_indices:
            return

        self.save_current_edits()

        next_ptr = self._find_next_pointer(direction=1)
        if next_ptr is not None:
            self.current_idx_pointer = next_ptr
            self._load_current_image_data()
        else:
            if hasattr(self.app, "refresh_results_tree"):
                self.app.refresh_results_tree()
            if self.filter_issues_only_var.get():
                messagebox.showinfo("Completed", "🎉 Excellent! No more issues or empty fields found.")
            else:
                messagebox.showinfo("Completed", "🎉 All images have been reviewed!")

    def on_prev(self):
        if not self.unique_image_indices:
            return

        self.save_current_edits()

        prev_ptr = self._find_next_pointer(direction=-1)
        if prev_ptr is not None:
            self.current_idx_pointer = prev_ptr
            self._load_current_image_data()

    def _on_filter_toggled(self):
        if self.filter_issues_only_var.get():
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
                    messagebox.showinfo("Notice", "No images with issues or empty values found.")
                    self.filter_issues_only_var.set(False)

    def _find_next_pointer(self, direction=1):
        total = len(self.unique_image_indices)
        if total <= 1:
            return None

        ptr = self.current_idx_pointer + direction
        while 0 <= ptr < total:
            if not self.filter_issues_only_var.get():
                return ptr

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
