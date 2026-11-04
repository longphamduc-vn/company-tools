"""
Interactive Step Reviewer and Editor window.
Allows user to review, search/filter, edit descriptions, add/edit comments,
delete unwanted steps, reorder steps, adjust highlight/focus regions,
blur or redact sensitive privacy areas, crop screenshots, undo changes,
insert steps from saved documents, and export final reports in bilingual mode.
"""

import io
import os
import sys
import json
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, List, Callable, Tuple, Dict
from pathlib import Path
from PIL import Image, ImageTk

from ..models import Step, SessionMetadata
from ..annotator import (
    annotate_screenshot,
    apply_blur_region,
    apply_redact_region,
    crop_image,
    draw_box_annotation,
)
from ..capture import ScreenCapture
from ..config import RecorderConfig
from ..exporter import ReportExporter
from ..window_info import exclude_window_from_capture
from ..i18n import t, I18nManager


class StepEditorWindow:
    """Window for reviewing, editing, reordering, redacting, cropping, and exporting recorded steps."""

    def __init__(
        self,
        parent: tk.Tk,
        steps: List[Step],
        metadata: SessionMetadata,
        config: RecorderConfig,
        exporter: ReportExporter,
        on_export_complete: Optional[Callable[[dict], None]] = None
    ):
        self.parent = parent
        self.steps = list(steps)  # work on local copy
        self.metadata = metadata
        self.config = config
        self.exporter = exporter
        self.on_export_complete = on_export_complete

        # Ensure active language matches config
        I18nManager.set_language(getattr(self.config, "language", "vi"))

        self.current_index = 0 if self.steps else -1
        self.preview_photo = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.preview_scale_x = 1.0
        self.preview_scale_y = 1.0
        self.canvas_img_offset = (0, 0)
        self.new_highlight_rect = None
        self.filtered_indices = list(range(len(self.steps)))

        # Per-step undo stack for drawing/privacy/crop actions: Dict[step_id, List[bytes]]
        self.undo_stack: Dict[int, List[bytes]] = {}

        # Active drawing tool: "highlight", "blur", "redact", "red_box", "crop"
        self.active_tool: str = "highlight"

        self.window = tk.Toplevel(parent)
        self.window.title(t("editor_title"))
        self.window.attributes("-topmost", True)
        self.window.configure(bg="#0f172a")

        # Set spacious comfortable geometry
        self.window.geometry("1100x740+40+20")
        self.window.minsize(920, 620)
        self.window.resizable(True, True)

        self._build_ui()
        self._populate_list()
        if self.steps:
            self._select_step(0)

        # Bind keyboard shortcuts
        self.window.bind("<Delete>", lambda e: self._delete_current_step())
        self.window.bind("<Control-s>", lambda e: self._apply_current_step_edits())
        self.window.bind("<Control-z>", lambda e: self._undo_last_action())
        self.window.bind("<Control-e>", lambda e: self._export_final_report())
        self.window.bind("<Control-o>", lambda e: self._open_saved_document())
        self.window.bind("<Escape>", lambda e: self.window.destroy())

        self.window.after(50, lambda: exclude_window_from_capture(self.window))
        self.window.focus_force()

    def _build_ui(self) -> None:
        main_frame = tk.Frame(self.window, bg="#0f172a", padx=14, pady=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top Header Bar
        header_frame = tk.Frame(main_frame, bg="#0f172a")
        header_frame.pack(fill=tk.X, pady=(0, 10))

        self.title_lbl = tk.Label(
            header_frame,
            text=t("editor_header"),
            font=("Segoe UI", 13, "bold"),
            bg="#0f172a",
            fg="#f8fafc"
        )
        self.title_lbl.pack(side=tk.LEFT)

        header_right = tk.Frame(header_frame, bg="#0f172a")
        header_right.pack(side=tk.RIGHT)

        # Open Saved Session button
        self.open_doc_btn = tk.Button(
            header_right,
            text=t("btn_open_session"),
            command=self._open_saved_document,
            bg="#1e293b",
            fg="#38bdf8",
            activebackground="#334155",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=2,
            cursor="hand2"
        )
        self.open_doc_btn.pack(side=tk.LEFT, padx=(0, 6))

        # Insert Steps from file button
        self.insert_steps_btn = tk.Button(
            header_right,
            text=t("btn_insert_steps"),
            command=self._insert_steps_from_file,
            bg="#1e293b",
            fg="#10b981",
            activebackground="#334155",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=2,
            cursor="hand2"
        )
        self.insert_steps_btn.pack(side=tk.LEFT, padx=(0, 8))

        # Language toggle
        self.lang_btn = tk.Button(
            header_right,
            text="🇻🇳 VI" if I18nManager.get_language() == "vi" else "🇬🇧 EN",
            command=self._toggle_language,
            bg="#1e293b",
            fg="#38bdf8",
            activebackground="#334155",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=2,
            cursor="hand2"
        )
        self.lang_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.total_lbl = tk.Label(
            header_right,
            text=t("total_steps", count=len(self.steps)),
            font=("Segoe UI", 10),
            bg="#0f172a",
            fg="#94a3b8"
        )
        self.total_lbl.pack(side=tk.LEFT)

        # Split content: Left list, Right editor
        content_frame = tk.Frame(main_frame, bg="#0f172a")
        content_frame.pack(fill=tk.BOTH, expand=True)
        content_frame.columnconfigure(0, weight=4)  # Left list
        content_frame.columnconfigure(1, weight=7)  # Right editor
        content_frame.rowconfigure(0, weight=1)

        # === LEFT COLUMN: Step List & Filter ===
        left_frame = tk.Frame(content_frame, bg="#1e293b", padx=10, pady=10)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.list_header = tk.Label(
            left_frame, text=t("step_list_title"),
            font=("Segoe UI", 10, "bold"), bg="#1e293b", fg="#cbd5e1"
        )
        self.list_header.pack(anchor="w", pady=(0, 6))

        # Search / Quick Filter Bar
        search_frame = tk.Frame(left_frame, bg="#1e293b")
        search_frame.pack(fill=tk.X, pady=(0, 6))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._on_filter_changed())
        search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            bg="#0f172a",
            fg="#f8fafc",
            insertbackground="#38bdf8",
            relief=tk.FLAT,
            font=("Segoe UI", 9)
        )
        search_entry.pack(fill=tk.X, ipady=4)

        # Listbox with scrollbar
        list_container = tk.Frame(left_frame, bg="#1e293b")
        list_container.pack(fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(list_container, orient=tk.VERTICAL)
        self.step_listbox = tk.Listbox(
            list_container,
            yscrollcommand=scrollbar.set,
            bg="#0f172a",
            fg="#f8fafc",
            selectbackground="#0284c7",
            selectforeground="#ffffff",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            activestyle="none",
            highlightthickness=1,
            highlightcolor="#38bdf8"
        )
        scrollbar.config(command=self.step_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.step_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.step_listbox.bind("<<ListboxSelect>>", self._on_list_select)

        # List Action Buttons (Delete, Move Up, Move Down)
        list_btn_frame = tk.Frame(left_frame, bg="#1e293b")
        list_btn_frame.pack(fill=tk.X, pady=(8, 0))

        self.del_btn = tk.Button(
            list_btn_frame,
            text=t("btn_delete_step"),
            command=self._delete_current_step,
            bg="#dc2626", fg="#ffffff",
            activebackground="#ef4444",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=8, pady=4, cursor="hand2"
        )
        self.del_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.up_btn = tk.Button(
            list_btn_frame,
            text=t("btn_move_up"),
            command=self._move_step_up,
            bg="#334155", fg="#f8fafc",
            activebackground="#475569",
            font=("Segoe UI", 9),
            relief=tk.FLAT, padx=8, pady=4, cursor="hand2"
        )
        self.up_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.down_btn = tk.Button(
            list_btn_frame,
            text=t("btn_move_down"),
            command=self._move_step_down,
            bg="#334155", fg="#f8fafc",
            activebackground="#475569",
            font=("Segoe UI", 9),
            relief=tk.FLAT, padx=8, pady=4, cursor="hand2"
        )
        self.down_btn.pack(side=tk.LEFT)

        # === RIGHT COLUMN: Step Editor & Preview ===
        right_frame = tk.Frame(content_frame, bg="#1e293b", padx=12, pady=10)
        right_frame.grid(row=0, column=1, sticky="nsew")

        # Step meta header
        self.step_header_lbl = tk.Label(
            right_frame,
            text="",
            font=("Segoe UI", 11, "bold"),
            bg="#1e293b", fg="#38bdf8"
        )
        self.step_header_lbl.pack(anchor="w", pady=(0, 4))

        # Description Edit
        self.desc_lbl = tk.Label(
            right_frame, text=t("desc_label"),
            font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#cbd5e1"
        )
        self.desc_lbl.pack(anchor="w", pady=(2, 1))

        self.desc_var = tk.StringVar()
        self.desc_entry = tk.Entry(
            right_frame,
            textvariable=self.desc_var,
            bg="#0f172a", fg="#f8fafc",
            insertbackground="#38bdf8",
            font=("Segoe UI", 9), relief=tk.FLAT
        )
        self.desc_entry.pack(fill=tk.X, ipady=3, pady=(0, 4))

        # Comment Edit
        self.comment_lbl = tk.Label(
            right_frame, text=t("comment_label"),
            font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#cbd5e1"
        )
        self.comment_lbl.pack(anchor="w", pady=(1, 1))

        self.comment_var = tk.StringVar()
        self.comment_entry = tk.Entry(
            right_frame,
            textvariable=self.comment_var,
            bg="#0f172a", fg="#f8fafc",
            insertbackground="#38bdf8",
            font=("Segoe UI", 9), relief=tk.FLAT
        )
        self.comment_entry.pack(fill=tk.X, ipady=3, pady=(0, 6))

        # Section & Chapter Header Frame (SOP Section)
        self.sec_box = tk.LabelFrame(
            right_frame,
            text=f" {t('sec_group_title')} ",
            bg="#1e293b",
            fg="#38bdf8",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=4,
            relief=tk.GROOVE
        )
        self.sec_box.pack(fill=tk.X, pady=(0, 6))

        self.is_section_var = tk.BooleanVar(value=False)
        self.sec_chk = tk.Checkbutton(
            self.sec_box,
            text=t("chk_section_header"),
            variable=self.is_section_var,
            command=self._on_section_chk_changed,
            bg="#1e293b",
            fg="#cbd5e1",
            activebackground="#1e293b",
            activeforeground="#f8fafc",
            selectcolor="#0f172a",
            font=("Segoe UI", 8)
        )
        self.sec_chk.pack(anchor="w")

        self.sec_inputs_frame = tk.Frame(self.sec_box, bg="#1e293b")
        # Unpacked by default until is_section_var is True

        self.sec_title_lbl = tk.Label(
            self.sec_inputs_frame,
            text=t("lbl_section_title"),
            font=("Segoe UI", 8, "bold"),
            bg="#1e293b",
            fg="#94a3b8"
        )
        self.sec_title_lbl.pack(anchor="w", pady=(1, 1))

        self.sec_title_var = tk.StringVar()
        self.sec_title_entry = tk.Entry(
            self.sec_inputs_frame,
            textvariable=self.sec_title_var,
            bg="#0f172a",
            fg="#f8fafc",
            insertbackground="#38bdf8",
            font=("Segoe UI", 9),
            relief=tk.FLAT
        )
        self.sec_title_entry.pack(fill=tk.X, ipady=2, pady=(0, 2))

        self.sec_desc_lbl = tk.Label(
            self.sec_inputs_frame,
            text=t("lbl_section_desc"),
            font=("Segoe UI", 8, "bold"),
            bg="#1e293b",
            fg="#94a3b8"
        )
        self.sec_desc_lbl.pack(anchor="w", pady=(1, 1))

        self.sec_desc_var = tk.StringVar()
        self.sec_desc_entry = tk.Entry(
            self.sec_inputs_frame,
            textvariable=self.sec_desc_var,
            bg="#0f172a",
            fg="#f8fafc",
            insertbackground="#38bdf8",
            font=("Segoe UI", 9),
            relief=tk.FLAT
        )
        self.sec_desc_entry.pack(fill=tk.X, ipady=2, pady=(0, 2))

        # === INTERACTIVE DRAWING & PRIVACY TOOLBAR ===
        tool_frame = tk.Frame(right_frame, bg="#1e293b")
        tool_frame.pack(fill=tk.X, pady=(2, 2))

        # Left tools
        self.tool_btns: Dict[str, tk.Button] = {}

        self.tool_btns["highlight"] = tk.Button(
            tool_frame,
            text=t("tool_highlight"),
            command=lambda: self._set_active_tool("highlight"),
            bg="#0284c7", fg="#ffffff",
            activebackground="#0369a1",
            font=("Segoe UI", 8, "bold"),
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2"
        )
        self.tool_btns["highlight"].pack(side=tk.LEFT, padx=(0, 3))

        self.tool_btns["blur"] = tk.Button(
            tool_frame,
            text=t("tool_blur"),
            command=lambda: self._set_active_tool("blur"),
            bg="#334155", fg="#cbd5e1",
            activebackground="#475569",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2"
        )
        self.tool_btns["blur"].pack(side=tk.LEFT, padx=(0, 3))

        self.tool_btns["redact"] = tk.Button(
            tool_frame,
            text=t("tool_redact"),
            command=lambda: self._set_active_tool("redact"),
            bg="#334155", fg="#cbd5e1",
            activebackground="#475569",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2"
        )
        self.tool_btns["redact"].pack(side=tk.LEFT, padx=(0, 3))

        self.tool_btns["red_box"] = tk.Button(
            tool_frame,
            text=t("tool_red_box"),
            command=lambda: self._set_active_tool("red_box"),
            bg="#334155", fg="#cbd5e1",
            activebackground="#475569",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2"
        )
        self.tool_btns["red_box"].pack(side=tk.LEFT, padx=(0, 3))

        self.tool_btns["crop"] = tk.Button(
            tool_frame,
            text=t("tool_crop"),
            command=lambda: self._set_active_tool("crop"),
            bg="#334155", fg="#cbd5e1",
            activebackground="#475569",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2"
        )
        self.tool_btns["crop"].pack(side=tk.LEFT, padx=(0, 8))

        # Right utility buttons: Undo & Reset
        self.reset_marker_btn = tk.Button(
            tool_frame,
            text=t("btn_reset_raw"),
            command=self._reset_to_raw,
            bg="#334155", fg="#cbd5e1",
            activebackground="#475569",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2"
        )
        self.reset_marker_btn.pack(side=tk.RIGHT)

        self.undo_btn = tk.Button(
            tool_frame,
            text=t("btn_undo"),
            command=self._undo_last_action,
            bg="#334155", fg="#cbd5e1",
            activebackground="#475569",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=6, pady=2, cursor="hand2"
        )
        self.undo_btn.pack(side=tk.RIGHT, padx=(0, 4))

        # Tool Instruction Hint Label
        self.tool_hint_lbl = tk.Label(
            right_frame,
            text=t("drag_hint_highlight"),
            font=("Segoe UI", 8),
            bg="#1e293b",
            fg="#94a3b8"
        )
        self.tool_hint_lbl.pack(anchor="w", pady=(1, 3))

        # Canvas for Screenshot Display & Interactive Drawing
        self.preview_canvas = tk.Canvas(
            right_frame,
            bg="#000000",
            highlightthickness=1,
            highlightbackground="#334155",
            cursor="cross"
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.preview_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.preview_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        # Apply edit button
        self.update_step_btn = tk.Button(
            right_frame,
            text=t("btn_apply_step"),
            command=self._apply_current_step_edits,
            bg="#0284c7", fg="#ffffff",
            activebackground="#0369a1",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=14, pady=4, cursor="hand2"
        )
        self.update_step_btn.pack(anchor="e")

        # === BOTTOM ACTION BAR ===
        bottom_bar = tk.Frame(main_frame, bg="#0f172a")
        bottom_bar.pack(fill=tk.X, pady=(10, 0))

        self.cancel_btn = tk.Button(
            bottom_bar,
            text=t("btn_close_editor"),
            command=self.window.destroy,
            bg="#334155", fg="#f8fafc",
            activebackground="#475569",
            font=("Segoe UI", 9),
            relief=tk.FLAT, padx=14, pady=5, cursor="hand2"
        )
        self.cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))

        self.export_btn = tk.Button(
            bottom_bar,
            text=t("btn_export_report"),
            command=self._export_final_report,
            bg="#059669", fg="#ffffff",
            activebackground="#10b981",
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT, padx=18, pady=5, cursor="hand2"
        )
        self.export_btn.pack(side=tk.RIGHT)

    def _set_active_tool(self, tool_name: str) -> None:
        """Switch active drawing tool on the toolbar."""
        self.active_tool = tool_name

        # Update button highlights
        for name, btn in self.tool_btns.items():
            if name == tool_name:
                btn.configure(bg="#0284c7", fg="#ffffff", font=("Segoe UI", 8, "bold"))
            else:
                btn.configure(bg="#334155", fg="#cbd5e1", font=("Segoe UI", 8))

        # Update instruction hint label
        hint_key = f"drag_hint_{tool_name}"
        self.tool_hint_lbl.configure(text=t(hint_key))

        # Update cursor
        if tool_name == "crop":
            self.preview_canvas.configure(cursor="crosshair")
        else:
            self.preview_canvas.configure(cursor="cross")

    def _on_section_chk_changed(self) -> None:
        """Show or hide section title/desc inputs based on checkbox."""
        if self.is_section_var.get():
            self.sec_inputs_frame.pack(fill=tk.X, pady=(2, 0))
            if not self.sec_title_var.get():
                self.sec_title_entry.focus_set()
        else:
            self.sec_inputs_frame.pack_forget()

    def _toggle_language(self) -> None:
        """Toggle editor between Vietnamese and English."""
        curr = I18nManager.get_language()
        new_lang = "en" if curr == "vi" else "vi"
        I18nManager.set_language(new_lang)
        self.config.language = new_lang
        try:
            self.config.save()
        except Exception:
            pass
        self._update_ui_texts()

    def _update_ui_texts(self) -> None:
        """Update all strings in editor window."""
        self.window.title(t("editor_title"))
        self.title_lbl.configure(text=t("editor_header"))
        self.open_doc_btn.configure(text=t("btn_open_session"))
        self.insert_steps_btn.configure(text=t("btn_insert_steps"))
        self.lang_btn.configure(text="🇻🇳 VI" if I18nManager.get_language() == "vi" else "🇬🇧 EN")
        self.total_lbl.configure(text=t("total_steps", count=len(self.steps)))
        self.list_header.configure(text=t("step_list_title"))
        self.del_btn.configure(text=t("btn_delete_step"))
        self.up_btn.configure(text=t("btn_move_up"))
        self.down_btn.configure(text=t("btn_move_down"))
        self.desc_lbl.configure(text=t("desc_label"))
        self.comment_lbl.configure(text=t("comment_label"))
        self.sec_box.configure(text=f" {t('sec_group_title')} ")
        self.sec_chk.configure(text=t("chk_section_header"))
        self.sec_title_lbl.configure(text=t("lbl_section_title"))
        self.sec_desc_lbl.configure(text=t("lbl_section_desc"))
        self.tool_btns["highlight"].configure(text=t("tool_highlight"))
        self.tool_btns["blur"].configure(text=t("tool_blur"))
        self.tool_btns["redact"].configure(text=t("tool_redact"))
        self.tool_btns["red_box"].configure(text=t("tool_red_box"))
        self.tool_btns["crop"].configure(text=t("tool_crop"))
        self.undo_btn.configure(text=t("btn_undo"))
        self.reset_marker_btn.configure(text=t("btn_reset_raw"))
        self.tool_hint_lbl.configure(text=t(f"drag_hint_{self.active_tool}"))
        self.update_step_btn.configure(text=t("btn_apply_step"))
        self.cancel_btn.configure(text=t("btn_close_editor"))
        self.export_btn.configure(text=t("btn_export_report"))

        if 0 <= self.current_index < len(self.steps):
            step = self.steps[self.current_index]
            self.step_header_lbl.configure(
                text=t("step_detail_title", id=step.step_id, action=step.action_type.replace('_', ' ').title(), time=step.time_str)
            )

    # --- Step List Management & Search Filter ---
    def _on_filter_changed(self) -> None:
        query = self.search_var.get().strip().lower()
        if not query:
            self.filtered_indices = list(range(len(self.steps)))
        else:
            self.filtered_indices = [
                i for i, s in enumerate(self.steps)
                if query in s.description.lower()
                or query in s.window_title.lower()
                or query in s.process_name.lower()
                or query in (s.user_comment or "").lower()
                or query in (s.section_title or "").lower()
                or query in (s.section_description or "").lower()
            ]
        self._populate_list()

    def _populate_list(self) -> None:
        """Refresh Listbox items with filtered steps and section headers."""
        self.step_listbox.delete(0, tk.END)
        sec_num = 0
        for i in self.filtered_indices:
            s = self.steps[i]
            prefix = ""
            if s.is_section_header:
                sec_num += 1
                sec_display = s.section_title or f"Phần {sec_num}"
                if len(sec_display) > 20:
                    sec_display = sec_display[:20] + "..."
                prefix = f"📑 [P.{sec_num}: {sec_display}] "

            icon = s.action_icon
            desc_short = (s.description[:32] + "...") if len(s.description) > 32 else s.description
            comment_tag = " [💬]" if s.user_comment else ""
            self.step_listbox.insert(tk.END, f"{prefix}#{s.step_id} {icon} {desc_short}{comment_tag}")

        self.total_lbl.configure(text=t("total_steps", count=len(self.steps)))

    def _on_list_select(self, event=None) -> None:
        selected = self.step_listbox.curselection()
        if selected:
            list_idx = selected[0]
            if list_idx < len(self.filtered_indices):
                real_idx = self.filtered_indices[list_idx]
                self._select_step(real_idx)

    def _select_step(self, index: int) -> None:
        if index < 0 or index >= len(self.steps):
            return

        self.current_index = index
        step = self.steps[index]

        # Update input fields
        self.step_header_lbl.configure(
            text=t("step_detail_title", id=step.step_id, action=step.action_type.replace('_', ' ').title(), time=step.time_str)
        )
        self.desc_var.set(step.description)
        self.comment_var.set(step.user_comment or "")
        self.is_section_var.set(bool(step.is_section_header))
        self.sec_title_var.set(step.section_title or "")
        self.sec_desc_var.set(step.section_description or "")
        self._on_section_chk_changed()

        # Highlight in listbox if visible
        try:
            if index in self.filtered_indices:
                list_idx = self.filtered_indices.index(index)
                self.step_listbox.selection_clear(0, tk.END)
                self.step_listbox.selection_set(list_idx)
                self.step_listbox.activate(list_idx)
        except Exception:
            pass

        # Render preview image
        self._render_step_preview(step)

    def _render_step_preview(self, step: Step) -> None:
        """Render screenshot of step inside the preview canvas."""
        self.preview_canvas.delete("all")

        img_bytes = step.annotated_image_bytes
        if not img_bytes and step.annotated_image_path and os.path.exists(step.annotated_image_path):
            with open(step.annotated_image_path, "rb") as f:
                img_bytes = f.read()

        if not img_bytes and step.raw_image_bytes:
            img_bytes = step.raw_image_bytes

        if not img_bytes:
            self.preview_canvas.create_text(
                200, 100, text=t("no_screenshot_available"),
                fill="#94a3b8", font=("Segoe UI", 10)
            )
            return

        try:
            pil_img = Image.open(io.BytesIO(img_bytes))

            # Scale to fit canvas
            self.window.update_idletasks()
            cw = max(200, self.preview_canvas.winfo_width())
            ch = max(150, self.preview_canvas.winfo_height())

            orig_w, orig_h = pil_img.size
            ratio = min(cw / orig_w, ch / orig_h)
            disp_w = max(10, int(orig_w * ratio))
            disp_h = max(10, int(orig_h * ratio))

            self.preview_scale_x = orig_w / disp_w
            self.preview_scale_y = orig_h / disp_h

            scaled_img = pil_img.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
            self.preview_photo = ImageTk.PhotoImage(scaled_img)

            # Center on canvas
            offset_x = (cw - disp_w) // 2
            offset_y = (ch - disp_h) // 2
            self.canvas_img_offset = (offset_x, offset_y)

            self.preview_canvas.create_image(
                offset_x, offset_y, image=self.preview_photo, anchor="nw"
            )
        except Exception as e:
            self.preview_canvas.create_text(
                200, 100, text=t("image_render_error", err=e),
                fill="#ef4444", font=("Segoe UI", 9)
            )

    # --- Interactive Highlighting, Privacy (Blur / Redact) & Crop ---
    def _on_canvas_press(self, event) -> None:
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def _on_canvas_drag(self, event) -> None:
        self.preview_canvas.delete("tool_drag_box")

        # Color outline based on active tool
        colors = {
            "highlight": "#38bdf8",
            "blur": "#818cf8",
            "redact": "#64748b",
            "red_box": "#ef4444",
            "crop": "#f59e0b"
        }
        outline_col = colors.get(self.active_tool, "#38bdf8")

        self.preview_canvas.create_rectangle(
            self.drag_start_x, self.drag_start_y, event.x, event.y,
            outline=outline_col, width=2, dash=(4, 2), tags="tool_drag_box"
        )

    def _push_undo(self, step: Step) -> None:
        """Save a snapshot of the current image state for undo."""
        current_bytes = step.annotated_image_bytes or step.raw_image_bytes
        if current_bytes:
            if step.step_id not in self.undo_stack:
                self.undo_stack[step.step_id] = []
            self.undo_stack[step.step_id].append(current_bytes)
            # Limit undo stack depth per step to 15
            if len(self.undo_stack[step.step_id]) > 15:
                self.undo_stack[step.step_id].pop(0)

    def _on_canvas_release(self, event) -> None:
        self.preview_canvas.delete("tool_drag_box")
        ox, oy = getattr(self, "canvas_img_offset", (0, 0))

        # Map canvas coordinates back to original full screenshot coordinates
        x1 = int((min(self.drag_start_x, event.x) - ox) * self.preview_scale_x)
        y1 = int((min(self.drag_start_y, event.y) - oy) * self.preview_scale_y)
        x2 = int((max(self.drag_start_x, event.x) - ox) * self.preview_scale_x)
        y2 = int((max(self.drag_start_y, event.y) - oy) * self.preview_scale_y)

        # Ignore accidental micro-clicks (< 10px)
        if (x2 - x1) < 10 or (y2 - y1) < 10:
            return

        if self.current_index < 0 or self.current_index >= len(self.steps):
            return

        step = self.steps[self.current_index]
        rect = (x1, y1, x2, y2)

        base_bytes = step.annotated_image_bytes or step.raw_image_bytes
        if not base_bytes:
            return

        # Execute according to active tool
        if self.active_tool == "highlight":
            self._push_undo(step)
            step.highlight_rect = rect
            base_img = Image.open(io.BytesIO(step.raw_image_bytes or base_bytes))
            annotated = annotate_screenshot(
                base_img,
                cursor_pos=(step.cursor_x, step.cursor_y) if step.cursor_x is not None else None,
                step_id=step.step_id,
                highlight_rect=rect,
                color_hex=self.config.highlight_color,
                radius=self.config.highlight_radius,
                style=self.config.highlight_style,
                show_badge=self.config.show_step_badge_on_screenshot
            )
            step.annotated_image_bytes = ScreenCapture.image_to_bytes(annotated)
            step.thumbnail_bytes = ScreenCapture.image_to_bytes(ScreenCapture.create_thumbnail(annotated))
            self._render_step_preview(step)

        elif self.active_tool == "blur":
            self._push_undo(step)
            base_img = Image.open(io.BytesIO(base_bytes))
            blurred = apply_blur_region(base_img, rect, radius=18)
            step.annotated_image_bytes = ScreenCapture.image_to_bytes(blurred)
            step.thumbnail_bytes = ScreenCapture.image_to_bytes(ScreenCapture.create_thumbnail(blurred))
            self._render_step_preview(step)

        elif self.active_tool == "redact":
            self._push_undo(step)
            base_img = Image.open(io.BytesIO(base_bytes))
            redacted = apply_redact_region(base_img, rect)
            step.annotated_image_bytes = ScreenCapture.image_to_bytes(redacted)
            step.thumbnail_bytes = ScreenCapture.image_to_bytes(ScreenCapture.create_thumbnail(redacted))
            self._render_step_preview(step)

        elif self.active_tool == "red_box":
            self._push_undo(step)
            base_img = Image.open(io.BytesIO(base_bytes))
            boxed = draw_box_annotation(base_img, rect, color_hex="#ef4444", width=3)
            step.annotated_image_bytes = ScreenCapture.image_to_bytes(boxed)
            step.thumbnail_bytes = ScreenCapture.image_to_bytes(ScreenCapture.create_thumbnail(boxed))
            self._render_step_preview(step)

        elif self.active_tool == "crop":
            crop_w = x2 - x1
            crop_h = y2 - y1
            if messagebox.askyesno(
                t("crop_confirm_title"),
                t("crop_confirm_msg", w=crop_w, h=crop_h),
                parent=self.window
            ):
                self._push_undo(step)
                base_img = Image.open(io.BytesIO(base_bytes))
                cropped = crop_image(base_img, rect)
                step.annotated_image_bytes = ScreenCapture.image_to_bytes(cropped)
                step.thumbnail_bytes = ScreenCapture.image_to_bytes(ScreenCapture.create_thumbnail(cropped))
                self._render_step_preview(step)

    def _undo_last_action(self) -> None:
        """Revert the most recent drawing, privacy or crop action for current step."""
        if 0 <= self.current_index < len(self.steps):
            step = self.steps[self.current_index]
            history = self.undo_stack.get(step.step_id, [])
            if history:
                prev_bytes = history.pop()
                step.annotated_image_bytes = prev_bytes
                prev_img = Image.open(io.BytesIO(prev_bytes))
                step.thumbnail_bytes = ScreenCapture.image_to_bytes(ScreenCapture.create_thumbnail(prev_img))
                self._render_step_preview(step)

    def _reset_to_raw(self) -> None:
        """Reset current step back to original raw unedited screenshot."""
        if 0 <= self.current_index < len(self.steps):
            step = self.steps[self.current_index]
            if step.raw_image_bytes:
                self._push_undo(step)
                step.highlight_rect = None
                base_img = Image.open(io.BytesIO(step.raw_image_bytes))
                c_pos = (step.cursor_x, step.cursor_y) if step.cursor_x is not None else None
                annotated = annotate_screenshot(
                    base_img,
                    cursor_pos=c_pos,
                    step_id=step.step_id,
                    highlight_rect=None,
                    color_hex=self.config.highlight_color,
                    radius=self.config.highlight_radius,
                    style=self.config.highlight_style,
                    show_badge=self.config.show_step_badge_on_screenshot
                )
                step.annotated_image_bytes = ScreenCapture.image_to_bytes(annotated)
                step.thumbnail_bytes = ScreenCapture.image_to_bytes(ScreenCapture.create_thumbnail(annotated))
                self._render_step_preview(step)

    # --- Document Management: Open Saved Document & Insert Steps ---
    def _open_saved_document(self) -> None:
        """Open a saved session from disk, replacing current workspace steps."""
        file_path = filedialog.askopenfilename(
            title=t("open_session_title"),
            filetypes=[("Session JSON", "session.json"), ("JSON Files", "*.json"), ("All Files", "*.*")],
            parent=self.window
        )
        if not file_path or not os.path.exists(file_path):
            return

        if self.steps:
            if not messagebox.askyesno(t("open_confirm_title"), t("open_confirm_msg"), parent=self.window):
                return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            sess_info = data.get("session", {})
            self.metadata.title = sess_info.get("title", self.metadata.title)
            self.metadata.description = sess_info.get("description", self.metadata.description)
            self.metadata.os_name = sess_info.get("os", self.metadata.os_name)

            steps_data = data.get("steps", [])
            loaded_steps = [Step.from_dict(s) for s in steps_data]
            base_dir = Path(file_path).parent

            for s in loaded_steps:
                self._resolve_step_images(s, base_dir)

            self.steps = loaded_steps
            self.undo_stack.clear()
            self._renumber_and_refresh_badges()
            self.search_var.set("")
            self._on_filter_changed()
            if self.steps:
                self._select_step(0)
        except Exception as e:
            messagebox.showerror(t("editor_title"), f"Error opening file: {e}", parent=self.window)

    def _insert_steps_from_file(self) -> None:
        """Insert steps from another saved session into the current session."""
        file_path = filedialog.askopenfilename(
            title=t("open_session_title"),
            filetypes=[("Session JSON", "session.json"), ("JSON Files", "*.json"), ("All Files", "*.*")],
            parent=self.window
        )
        if not file_path or not os.path.exists(file_path):
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            steps_data = data.get("steps", [])
            if not steps_data:
                return

            new_steps = [Step.from_dict(s) for s in steps_data]
            base_dir = Path(file_path).parent

            for s in new_steps:
                self._resolve_step_images(s, base_dir)

            insert_idx = (self.current_index + 1) if (0 <= self.current_index < len(self.steps)) else len(self.steps)
            for i, s in enumerate(new_steps):
                self.steps.insert(insert_idx + i, s)

            self._renumber_and_refresh_badges()
            self._on_filter_changed()
            self._select_step(insert_idx)

            messagebox.showinfo(
                t("editor_title"),
                t("insert_success", count=len(new_steps)),
                parent=self.window
            )
        except Exception as e:
            messagebox.showerror(
                t("editor_title"),
                t("insert_failed", err=e),
                parent=self.window
            )

    def _resolve_step_images(self, step: Step, base_dir: Path) -> None:
        """Helper to load image bytes for a step if files exist on disk."""
        target_p = None
        if step.annotated_image_path:
            p = Path(step.annotated_image_path)
            if not p.is_absolute():
                p = base_dir / p
            if p.exists():
                target_p = p
        if not target_p and step.raw_image_path:
            p = Path(step.raw_image_path)
            if not p.is_absolute():
                p = base_dir / p
            if p.exists():
                target_p = p

        if target_p and target_p.exists():
            step.annotated_image_path = str(target_p)
            with open(target_p, "rb") as f:
                step.annotated_image_bytes = f.read()
                if not step.raw_image_bytes:
                    step.raw_image_bytes = step.annotated_image_bytes
            try:
                im = Image.open(io.BytesIO(step.annotated_image_bytes))
                step.thumbnail_bytes = ScreenCapture.image_to_bytes(ScreenCapture.create_thumbnail(im))
            except Exception:
                pass

    # --- Edit, Delete, Renumbering & Reordering ---
    def _apply_current_step_edits(self) -> None:
        """Save text description, comment and section changes for selected step."""
        if 0 <= self.current_index < len(self.steps):
            step = self.steps[self.current_index]
            step.description = self.desc_var.get().strip() or step.description
            step.user_comment = self.comment_var.get().strip() or None
            step.is_section_header = self.is_section_var.get()
            step.section_title = self.sec_title_var.get().strip() if step.is_section_header else None
            step.section_description = self.sec_desc_var.get().strip() if step.is_section_header else None

            # Refresh list item text
            self._on_filter_changed()
            messagebox.showinfo(t("editor_title"), t("step_updated_msg", id=step.step_id), parent=self.window)

    def _renumber_and_refresh_badges(self) -> None:
        """Renumber all steps sequentially (#1..N) and re-burn badge numbers onto images."""
        for i, s in enumerate(self.steps):
            s.step_id = i + 1
            if s.raw_image_bytes:
                try:
                    base_img = Image.open(io.BytesIO(s.raw_image_bytes))
                    c_pos = (s.cursor_x, s.cursor_y) if s.cursor_x is not None else None
                    annotated = annotate_screenshot(
                        base_img,
                        cursor_pos=c_pos,
                        step_id=s.step_id,
                        highlight_rect=s.highlight_rect,
                        color_hex=self.config.highlight_color,
                        radius=self.config.highlight_radius,
                        style=self.config.highlight_style,
                        show_badge=self.config.show_step_badge_on_screenshot
                    )
                    s.annotated_image_bytes = ScreenCapture.image_to_bytes(annotated)
                    s.thumbnail_bytes = ScreenCapture.image_to_bytes(ScreenCapture.create_thumbnail(annotated))
                except Exception:
                    pass

    def _delete_current_step(self) -> None:
        """Delete currently selected step, renumber remaining steps, and refresh badges."""
        if not self.steps or self.current_index < 0 or self.current_index >= len(self.steps):
            return

        del_id = self.steps[self.current_index].step_id
        if messagebox.askyesno(t("confirm_delete_title"), t("confirm_delete_msg", id=del_id), parent=self.window):
            self.steps.pop(self.current_index)

            # Smoothly renumber and burn new sequential badges
            self._renumber_and_refresh_badges()
            self._on_filter_changed()

            if self.steps:
                new_idx = min(self.current_index, len(self.steps) - 1)
                self._select_step(new_idx)
            else:
                self.current_index = -1
                self.desc_var.set("")
                self.comment_var.set("")
                self.is_section_var.set(False)
                self.sec_title_var.set("")
                self.sec_desc_var.set("")
                self.preview_canvas.delete("all")
                self.step_header_lbl.configure(text=t("no_steps_left"))

    def _move_step_up(self) -> None:
        """Move selected step up in sequence and refresh badge numbers."""
        idx = self.current_index
        if idx > 0:
            self.steps[idx - 1], self.steps[idx] = self.steps[idx], self.steps[idx - 1]
            self._renumber_and_refresh_badges()
            self._on_filter_changed()
            self._select_step(idx - 1)

    def _move_step_down(self) -> None:
        """Move selected step down in sequence and refresh badge numbers."""
        idx = self.current_index
        if 0 <= idx < len(self.steps) - 1:
            self.steps[idx + 1], self.steps[idx] = self.steps[idx], self.steps[idx + 1]
            self._renumber_and_refresh_badges()
            self._on_filter_changed()
            self._select_step(idx + 1)

    # --- Final Export ---
    def _export_final_report(self) -> None:
        """Export edited steps into HTML, Markdown, and ZIP archive."""
        if not self.steps:
            messagebox.showwarning(t("editor_title"), t("export_empty_warning"), parent=self.window)
            return

        # Ensure active inputs are applied
        if 0 <= self.current_index < len(self.steps):
            cur = self.steps[self.current_index]
            cur.description = self.desc_var.get().strip() or cur.description
            cur.user_comment = self.comment_var.get().strip() or None
            cur.is_section_header = self.is_section_var.get()
            cur.section_title = self.sec_title_var.get().strip() if cur.is_section_header else None
            cur.section_description = self.sec_desc_var.get().strip() if cur.is_section_header else None

        session_folder = Path(self.config.output_dir) / self.metadata.session_id
        session_folder.mkdir(parents=True, exist_ok=True)

        self.metadata.total_steps = len(self.steps)

        results = self.exporter.export(
            steps=self.steps,
            metadata=self.metadata,
            output_dir=str(session_folder)
        )

        html_path = results.get("html")
        if html_path and getattr(self.config, "auto_open_report", True):
            try:
                webbrowser.open(f"file://{os.path.abspath(html_path)}")
            except Exception:
                pass

        if self.on_export_complete:
            self.on_export_complete(results)

        msg = t(
            "export_success_msg",
            steps=len(self.steps),
            duration=self.metadata.duration_str,
            folder=str(session_folder)
        )
        if messagebox.askyesno(t("export_success_title"), msg, parent=self.window):
            self._open_folder(str(session_folder))

        self.window.destroy()

    def _open_folder(self, path: str) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", path])
            else:
                import subprocess
                subprocess.run(["xdg-open", path])
        except Exception:
            pass
