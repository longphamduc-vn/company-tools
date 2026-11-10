"""
Interactive Step Reviewer and Editor window.
Studio-grade, modern Dark-Mode workspace for reviewing, searching, editing descriptions,
adding comments, deleting, reordering, cropping, blurring/redacting privacy regions,
inserting saved steps, and exporting publication-ready SOP guides.
"""

import io
import os
import sys
import json
import threading
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
from ..i18n import t, I18nManager, TRANSLATIONS
from .icon_utils import apply_window_icon


# UI Design Palette - Studio Dark Theme
COLOR_BG = "#090d16"           # Deep space background
COLOR_PANEL = "#111827"        # Card / panel background
COLOR_PANEL_ALT = "#162036"    # Toolbar & header container
COLOR_BORDER = "#1e293b"       # Subtle border
COLOR_BORDER_FOCUS = "#0ea5e9" # Active / focus highlight
COLOR_INPUT_BG = "#060911"     # Recessed dark inputs
COLOR_TEXT_MAIN = "#f8fafc"    # High-contrast white
COLOR_TEXT_MUTED = "#94a3b8"   # Secondary slate
COLOR_TEXT_DIM = "#64748b"     # Dim text & shortcut hints
COLOR_CYAN = "#0ea5e9"         # Brand electric cyan
COLOR_EMERALD = "#10b981"      # Success / Apply / Export
COLOR_ROSE = "#f43f5e"         # Danger / Delete
COLOR_AMBER = "#f59e0b"        # Chapter / Warning / Crop
COLOR_PURPLE = "#8b5cf6"       # Blur / Privacy


def bind_hover(widget: tk.Widget, normal_bg: str, hover_bg: str, normal_fg: str = None, hover_fg: str = None) -> None:
    """Add smooth hover background & foreground transition to flat buttons."""
    def _on_enter(e):
        try:
            widget.configure(bg=hover_bg)
            if hover_fg:
                widget.configure(fg=hover_fg)
        except Exception:
            pass

    def _on_leave(e):
        try:
            widget.configure(bg=normal_bg)
            if normal_fg:
                widget.configure(fg=normal_fg)
        except Exception:
            pass

    widget.bind("<Enter>", _on_enter, add="+")
    widget.bind("<Leave>", _on_leave, add="+")


class StepEditorWindow:
    """Studio Review, Drawing & Editing workspace for recorded steps."""

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
        self.raw_img_size = (0, 0)
        self.filtered_indices = list(range(len(self.steps)))

        # Per-step undo stack: Dict[step_id, List[bytes]]
        self.undo_stack: Dict[int, List[bytes]] = {}

        # Unified action history for multi-level undo (drawing edits & step deletions)
        self.action_history: List[Dict] = []

        # Active drawing tool
        self.active_tool: str = "highlight"

        # Background badge renumbering thread management
        self._badge_refresh_generation: int = 0
        self._active_badge_thread: Optional[threading.Thread] = None

        # Scaled PhotoImage LRU Cache for buttery smooth 60fps preview
        self._preview_cache: Dict[Tuple[int, int, int], Any] = {}

        self.window = tk.Toplevel(parent)
        self.window.title(t("editor_title"))
        apply_window_icon(self.window)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=COLOR_BG)

        # Set spacious comfortable geometry
        self.window.geometry("1160x780+40+20")
        self.window.minsize(980, 660)
        self.window.resizable(True, True)

        self._build_ui()
        self._populate_list()
        if self.steps:
            self._select_step(0)

        # Keyboard shortcuts
        def _handle_key_delete(event):
            # Don't trigger step deletion if user is typing inside an entry/text input
            if isinstance(event.widget, (tk.Entry, tk.Text, tk.Spinbox)):
                return
            self._delete_current_step()

        def _handle_key_select_all(event):
            # If user is in an entry/text widget, let native text select-all happen
            if isinstance(event.widget, (tk.Entry, tk.Text, tk.Spinbox)):
                return
            self._select_all_steps()
            return "break"

        self.window.bind("<Delete>", _handle_key_delete)
        self.window.bind("<Control-s>", lambda e: self._apply_current_step_edits())
        self.window.bind("<Control-z>", lambda e: self._undo_last_action())
        self.window.bind("<Control-e>", lambda e: self._export_final_report())
        self.window.bind("<Control-o>", lambda e: self._open_saved_document())
        self.window.bind("<Control-a>", _handle_key_select_all)
        self.window.bind("<Control-A>", _handle_key_select_all)
        self.window.bind("<Escape>", lambda e: self.window.destroy())

        self.window.after(50, lambda: exclude_window_from_capture(self.window))
        self.window.focus_force()

    def _build_ui(self) -> None:
        main_frame = tk.Frame(self.window, bg=COLOR_BG, padx=14, pady=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ================= TOP HEADER BAR =================
        header_frame = tk.Frame(main_frame, bg=COLOR_PANEL, padx=14, pady=8, highlightbackground=COLOR_BORDER, highlightthickness=1)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        # Brand / Title
        header_left = tk.Frame(header_frame, bg=COLOR_PANEL)
        header_left.pack(side=tk.LEFT)

        self.logo_badge = tk.Label(
            header_left,
            text=" 📸 STEP STUDIO ",
            font=("Segoe UI", 9, "bold"),
            bg="#0369a1",
            fg="#ffffff"
        )
        self.logo_badge.pack(side=tk.LEFT, padx=(0, 8))

        self.title_lbl = tk.Label(
            header_left,
            text=t("editor_header"),
            font=("Segoe UI", 12, "bold"),
            bg=COLOR_PANEL,
            fg=COLOR_TEXT_MAIN
        )
        self.title_lbl.pack(side=tk.LEFT)

        # Header Right Controls
        header_right = tk.Frame(header_frame, bg=COLOR_PANEL)
        header_right.pack(side=tk.RIGHT)

        # Open Saved Session button
        self.open_doc_btn = tk.Button(
            header_right,
            text=t("btn_open_session"),
            command=self._open_saved_document,
            bg=COLOR_PANEL_ALT,
            fg=COLOR_CYAN,
            activebackground="#1e293b",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=9,
            pady=3,
            cursor="hand2"
        )
        self.open_doc_btn.pack(side=tk.LEFT, padx=(0, 5))
        bind_hover(self.open_doc_btn, COLOR_PANEL_ALT, "#1e293b", COLOR_CYAN, "#38bdf8")

        # Insert Steps from file button
        self.insert_steps_btn = tk.Button(
            header_right,
            text=t("btn_insert_steps"),
            command=self._insert_steps_from_file,
            bg=COLOR_PANEL_ALT,
            fg=COLOR_EMERALD,
            activebackground="#1e293b",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=9,
            pady=3,
            cursor="hand2"
        )
        self.insert_steps_btn.pack(side=tk.LEFT, padx=(0, 8))
        bind_hover(self.insert_steps_btn, COLOR_PANEL_ALT, "#1e293b", COLOR_EMERALD, "#34d399")

        # Language toggle pill
        self.lang_btn = tk.Button(
            header_right,
            text="🇻🇳 VI" if I18nManager.get_language() == "vi" else "🇬🇧 EN",
            command=self._toggle_language,
            bg=COLOR_PANEL_ALT,
            fg="#cbd5e1",
            activebackground="#1e293b",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=3,
            cursor="hand2"
        )
        self.lang_btn.pack(side=tk.LEFT, padx=(0, 10))
        bind_hover(self.lang_btn, COLOR_PANEL_ALT, "#1e293b", "#cbd5e1", "#ffffff")

        # Total steps pill
        self.total_lbl = tk.Label(
            header_right,
            text=t("total_steps", count=len(self.steps)),
            font=("Segoe UI", 9, "bold"),
            bg="#030712",
            fg=COLOR_CYAN,
            padx=10,
            pady=3,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1
        )
        self.total_lbl.pack(side=tk.LEFT)

        # ================= WORKSPACE SPLIT =================
        content_frame = tk.Frame(main_frame, bg=COLOR_BG)
        content_frame.pack(fill=tk.BOTH, expand=True)
        content_frame.columnconfigure(0, weight=4)  # Left list navigator
        content_frame.columnconfigure(1, weight=8)  # Right drawing & editing studio
        content_frame.rowconfigure(0, weight=1)

        # === LEFT COLUMN: Step Navigator & Filters ===
        left_frame = tk.Frame(content_frame, bg=COLOR_PANEL, padx=12, pady=12, highlightbackground=COLOR_BORDER, highlightthickness=1)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Title row with icon
        list_header_row = tk.Frame(left_frame, bg=COLOR_PANEL)
        list_header_row.pack(fill=tk.X, pady=(0, 6))

        self.list_header = tk.Label(
            list_header_row,
            text=t("step_list_title"),
            font=("Segoe UI", 9, "bold"),
            bg=COLOR_PANEL,
            fg="#cbd5e1"
        )
        self.list_header.pack(side=tk.LEFT)

        # Modern Search / Filter Pill
        search_frame = tk.Frame(left_frame, bg=COLOR_INPUT_BG, highlightbackground=COLOR_BORDER, highlightthickness=1, padx=6, pady=2)
        search_frame.pack(fill=tk.X, pady=(0, 8))

        search_icon = tk.Label(search_frame, text="🔍", font=("Segoe UI", 8), bg=COLOR_INPUT_BG, fg=COLOR_TEXT_DIM)
        search_icon.pack(side=tk.LEFT, padx=(2, 4))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._on_filter_changed())
        search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_MAIN,
            insertbackground=COLOR_CYAN,
            relief=tk.FLAT,
            font=("Segoe UI", 9)
        )
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)

        # Step Listbox Container with custom scrollbar
        list_container = tk.Frame(left_frame, bg=COLOR_PANEL)
        list_container.pack(fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(list_container, orient=tk.VERTICAL)
        self.step_listbox = tk.Listbox(
            list_container,
            selectmode=tk.EXTENDED,
            yscrollcommand=scrollbar.set,
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_MAIN,
            selectbackground=COLOR_CYAN,
            selectforeground="#ffffff",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            activestyle="none",
            highlightthickness=1,
            highlightcolor=COLOR_BORDER_FOCUS,
            selectborderwidth=0
        )
        scrollbar.config(command=self.step_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.step_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.step_listbox.bind("<<ListboxSelect>>", self._on_list_select)

        # Step List Action Buttons: Row 1 (Delete, Undo Delete, Select All)
        list_btn_frame = tk.Frame(left_frame, bg=COLOR_PANEL)
        list_btn_frame.pack(fill=tk.X, pady=(8, 0))

        self.del_btn = tk.Button(
            list_btn_frame,
            text=t("btn_delete_step"),
            command=self._delete_current_step,
            bg="#991b1b", fg="#ffffff",
            activebackground=COLOR_ROSE,
            font=("Segoe UI", 8, "bold"),
            relief=tk.FLAT, padx=7, pady=4, cursor="hand2"
        )
        self.del_btn.pack(side=tk.LEFT, padx=(0, 4))
        bind_hover(self.del_btn, "#991b1b", COLOR_ROSE)

        self.undo_del_btn = tk.Button(
            list_btn_frame,
            text=t("btn_undo_delete"),
            command=self._undo_delete_only,
            bg=COLOR_INPUT_BG, fg=COLOR_CYAN,
            activebackground="#1e293b",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=7, pady=4, cursor="hand2",
            state=tk.DISABLED
        )
        self.undo_del_btn.pack(side=tk.LEFT, padx=(0, 4))
        bind_hover(self.undo_del_btn, COLOR_INPUT_BG, "#1e293b", COLOR_CYAN, "#ffffff")

        self.select_all_btn = tk.Button(
            list_btn_frame,
            text=t("btn_select_all"),
            command=self._toggle_select_all,
            bg=COLOR_PANEL_ALT, fg=COLOR_TEXT_MUTED,
            activebackground="#1e293b",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=6, pady=4, cursor="hand2"
        )
        self.select_all_btn.pack(side=tk.RIGHT)
        bind_hover(self.select_all_btn, COLOR_PANEL_ALT, "#1e293b", COLOR_TEXT_MUTED, COLOR_TEXT_MAIN)

        # Row 2: Reorder Buttons
        reorder_frame = tk.Frame(left_frame, bg=COLOR_PANEL)
        reorder_frame.pack(fill=tk.X, pady=(4, 0))

        self.up_btn = tk.Button(
            reorder_frame,
            text=t("btn_move_up"),
            command=self._move_step_up,
            bg=COLOR_PANEL_ALT, fg=COLOR_TEXT_MAIN,
            activebackground="#1e293b",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=8, pady=3, cursor="hand2"
        )
        self.up_btn.pack(side=tk.LEFT, padx=(0, 4))
        bind_hover(self.up_btn, COLOR_PANEL_ALT, "#1e293b")

        self.down_btn = tk.Button(
            reorder_frame,
            text=t("btn_move_down"),
            command=self._move_step_down,
            bg=COLOR_PANEL_ALT, fg=COLOR_TEXT_MAIN,
            activebackground="#1e293b",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=8, pady=3, cursor="hand2"
        )
        self.down_btn.pack(side=tk.LEFT)
        bind_hover(self.down_btn, COLOR_PANEL_ALT, "#1e293b")

        # Step count footer
        self.list_footer_lbl = tk.Label(
            left_frame,
            text="",
            font=("Segoe UI", 7),
            bg=COLOR_PANEL,
            fg=COLOR_TEXT_DIM
        )
        self.list_footer_lbl.pack(anchor="w", pady=(6, 0))

        # === RIGHT COLUMN: Studio Editor, Toolbar & Canvas ===
        right_frame = tk.Frame(content_frame, bg=COLOR_PANEL, padx=14, pady=12, highlightbackground=COLOR_BORDER, highlightthickness=1)
        right_frame.grid(row=0, column=1, sticky="nsew")

        # Stylized Step Metadata Card Header
        meta_card = tk.Frame(right_frame, bg=COLOR_PANEL_ALT, padx=10, pady=6, highlightbackground=COLOR_BORDER, highlightthickness=1)
        meta_card.pack(fill=tk.X, pady=(0, 8))

        self.step_badge_pill = tk.Label(
            meta_card,
            text="#01",
            font=("Segoe UI", 9, "bold"),
            bg=COLOR_CYAN,
            fg="#ffffff",
            padx=6,
            pady=1
        )
        self.step_badge_pill.pack(side=tk.LEFT, padx=(0, 6))

        self.action_pill = tk.Label(
            meta_card,
            text="Action",
            font=("Segoe UI", 8, "bold"),
            bg="#030712",
            fg="#38bdf8",
            padx=6,
            pady=1,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1
        )
        self.action_pill.pack(side=tk.LEFT, padx=(0, 6))

        self.time_pill = tk.Label(
            meta_card,
            text="00:00:00",
            font=("Consolas", 8),
            bg=COLOR_PANEL_ALT,
            fg=COLOR_TEXT_MUTED
        )
        self.time_pill.pack(side=tk.LEFT, padx=(0, 8))

        self.window_tag_lbl = tk.Label(
            meta_card,
            text="",
            font=("Segoe UI", 8),
            bg=COLOR_PANEL_ALT,
            fg=COLOR_TEXT_DIM,
            anchor="w"
        )
        self.window_tag_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Fields Grid for Description and Comment
        fields_row = tk.Frame(right_frame, bg=COLOR_PANEL)
        fields_row.pack(fill=tk.X, pady=(0, 6))
        fields_row.columnconfigure(0, weight=1)
        fields_row.columnconfigure(1, weight=1)

        # Description Field Card
        desc_box = tk.Frame(fields_row, bg=COLOR_PANEL)
        desc_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.desc_lbl = tk.Label(
            desc_box, text=t("desc_label"),
            font=("Segoe UI", 8, "bold"), bg=COLOR_PANEL, fg="#cbd5e1"
        )
        self.desc_lbl.pack(anchor="w", pady=(0, 2))

        self.desc_var = tk.StringVar()
        self.desc_entry = tk.Entry(
            desc_box,
            textvariable=self.desc_var,
            bg=COLOR_INPUT_BG, fg=COLOR_TEXT_MAIN,
            insertbackground=COLOR_CYAN,
            font=("Segoe UI", 9), relief=tk.FLAT,
            highlightbackground=COLOR_BORDER, highlightthickness=1
        )
        self.desc_entry.pack(fill=tk.X, ipady=3)

        # Comment Field Card
        comment_box = tk.Frame(fields_row, bg=COLOR_PANEL)
        comment_box.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self.comment_lbl = tk.Label(
            comment_box, text=t("comment_label"),
            font=("Segoe UI", 8, "bold"), bg=COLOR_PANEL, fg="#cbd5e1"
        )
        self.comment_lbl.pack(anchor="w", pady=(0, 2))

        self.comment_var = tk.StringVar()
        self.comment_entry = tk.Entry(
            comment_box,
            textvariable=self.comment_var,
            bg=COLOR_INPUT_BG, fg=COLOR_TEXT_MAIN,
            insertbackground=COLOR_CYAN,
            font=("Segoe UI", 9), relief=tk.FLAT,
            highlightbackground=COLOR_BORDER, highlightthickness=1
        )
        self.comment_entry.pack(fill=tk.X, ipady=3)

        # Section & Chapter Header Card (SOP Section)
        self.sec_box = tk.Frame(
            right_frame,
            bg=COLOR_PANEL_ALT,
            padx=10,
            pady=6,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1
        )
        self.sec_box.pack(fill=tk.X, pady=(0, 6))

        self.is_section_var = tk.BooleanVar(value=False)
        self.sec_chk = tk.Checkbutton(
            self.sec_box,
            text=t("chk_section_header"),
            variable=self.is_section_var,
            command=self._on_section_chk_changed,
            bg=COLOR_PANEL_ALT,
            fg=COLOR_AMBER,
            activebackground=COLOR_PANEL_ALT,
            activeforeground="#fbbf24",
            selectcolor="#030712",
            font=("Segoe UI", 8, "bold")
        )
        self.sec_chk.pack(anchor="w")

        self.sec_inputs_frame = tk.Frame(self.sec_box, bg=COLOR_PANEL_ALT)
        # Unpacked by default until is_section_var is True

        sec_input_row = tk.Frame(self.sec_inputs_frame, bg=COLOR_PANEL_ALT)
        sec_input_row.pack(fill=tk.X, pady=(2, 0))
        sec_input_row.columnconfigure(0, weight=1)
        sec_input_row.columnconfigure(1, weight=1)

        # Title column
        title_col = tk.Frame(sec_input_row, bg=COLOR_PANEL_ALT)
        title_col.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self.sec_title_lbl = tk.Label(
            title_col,
            text=t("lbl_section_title"),
            font=("Segoe UI", 8),
            bg=COLOR_PANEL_ALT,
            fg=COLOR_TEXT_MUTED
        )
        self.sec_title_lbl.pack(anchor="w")

        self.sec_title_var = tk.StringVar()
        self.sec_title_entry = tk.Entry(
            title_col,
            textvariable=self.sec_title_var,
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_MAIN,
            insertbackground=COLOR_CYAN,
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1
        )
        self.sec_title_entry.pack(fill=tk.X, ipady=2, pady=(1, 0))

        # Description column
        desc_col = tk.Frame(sec_input_row, bg=COLOR_PANEL_ALT)
        desc_col.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        self.sec_desc_lbl = tk.Label(
            desc_col,
            text=t("lbl_section_desc"),
            font=("Segoe UI", 8),
            bg=COLOR_PANEL_ALT,
            fg=COLOR_TEXT_MUTED
        )
        self.sec_desc_lbl.pack(anchor="w")

        self.sec_desc_var = tk.StringVar()
        self.sec_desc_entry = tk.Entry(
            desc_col,
            textvariable=self.sec_desc_var,
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_MAIN,
            insertbackground=COLOR_CYAN,
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1
        )
        self.sec_desc_entry.pack(fill=tk.X, ipady=2, pady=(1, 0))

        # Decision Point & Branching Workflow Card (Yes/No Decision)
        self.decision_box = tk.Frame(
            right_frame,
            bg=COLOR_PANEL_ALT,
            padx=10,
            pady=6,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1
        )
        self.decision_box.pack(fill=tk.X, pady=(0, 6))

        self.is_decision_var = tk.BooleanVar(value=False)
        self.decision_chk = tk.Checkbutton(
            self.decision_box,
            text=t("chk_decision_point"),
            variable=self.is_decision_var,
            command=self._on_decision_chk_changed,
            bg=COLOR_PANEL_ALT,
            fg="#38bdf8",
            activebackground=COLOR_PANEL_ALT,
            activeforeground="#38bdf8",
            selectcolor="#030712",
            font=("Segoe UI", 8, "bold")
        )
        self.decision_chk.pack(anchor="w")

        self.decision_inputs_frame = tk.Frame(self.decision_box, bg=COLOR_PANEL_ALT)
        # Unpacked by default until is_decision_var is True

        # Row 1: Condition Question
        q_row = tk.Frame(self.decision_inputs_frame, bg=COLOR_PANEL_ALT)
        q_row.pack(fill=tk.X, pady=(2, 4))

        self.cond_q_lbl = tk.Label(
            q_row,
            text=t("lbl_condition_question"),
            font=("Segoe UI", 8),
            bg=COLOR_PANEL_ALT,
            fg=COLOR_TEXT_MUTED
        )
        self.cond_q_lbl.pack(anchor="w")

        self.cond_q_var = tk.StringVar()
        self.cond_q_entry = tk.Entry(
            q_row,
            textvariable=self.cond_q_var,
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_MAIN,
            insertbackground=COLOR_CYAN,
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1
        )
        self.cond_q_entry.pack(fill=tk.X, ipady=2, pady=(1, 0))

        # Row 2: Two columns for YES branch and NO branch
        branches_row = tk.Frame(self.decision_inputs_frame, bg=COLOR_PANEL_ALT)
        branches_row.pack(fill=tk.X, pady=(2, 0))
        branches_row.columnconfigure(0, weight=1)
        branches_row.columnconfigure(1, weight=1)

        # Left column: YES / TRUE
        yes_col = tk.Frame(branches_row, bg=COLOR_PANEL_ALT)
        yes_col.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.yes_lbl = tk.Label(
            yes_col,
            text=t("lbl_yes_branch"),
            font=("Segoe UI", 8, "bold"),
            bg=COLOR_PANEL_ALT,
            fg=COLOR_EMERALD
        )
        self.yes_lbl.pack(anchor="w")

        self.yes_text_var = tk.StringVar()
        self.yes_text_entry = tk.Entry(
            yes_col,
            textvariable=self.yes_text_var,
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_MAIN,
            insertbackground=COLOR_CYAN,
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            highlightbackground="#065f46",
            highlightthickness=1
        )
        self.yes_text_entry.pack(fill=tk.X, ipady=2, pady=(1, 2))

        yes_jump_row = tk.Frame(yes_col, bg=COLOR_PANEL_ALT)
        yes_jump_row.pack(fill=tk.X)
        self.yes_jump_lbl = tk.Label(yes_jump_row, text=t("lbl_jump_step"), font=("Segoe UI", 7), bg=COLOR_PANEL_ALT, fg=COLOR_TEXT_DIM)
        self.yes_jump_lbl.pack(side=tk.LEFT)
        self.yes_step_var = tk.IntVar(value=0)
        self.yes_jump_spin = tk.Spinbox(yes_jump_row, from_=0, to=999, textvariable=self.yes_step_var, width=5, bg=COLOR_INPUT_BG, fg=COLOR_TEXT_MAIN, relief=tk.FLAT)
        self.yes_jump_spin.pack(side=tk.LEFT, padx=(4, 0))
        tk.Label(yes_jump_row, text="(0 = bước kế)", font=("Segoe UI", 7), bg=COLOR_PANEL_ALT, fg=COLOR_TEXT_DIM).pack(side=tk.LEFT, padx=(4, 0))

        # Right column: NO / FALSE / EXCEPTION
        no_col = tk.Frame(branches_row, bg=COLOR_PANEL_ALT)
        no_col.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self.no_lbl = tk.Label(
            no_col,
            text=t("lbl_no_branch"),
            font=("Segoe UI", 8, "bold"),
            bg=COLOR_PANEL_ALT,
            fg=COLOR_ROSE
        )
        self.no_lbl.pack(anchor="w")

        self.no_text_var = tk.StringVar()
        self.no_text_entry = tk.Entry(
            no_col,
            textvariable=self.no_text_var,
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_MAIN,
            insertbackground=COLOR_CYAN,
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            highlightbackground="#881337",
            highlightthickness=1
        )
        self.no_text_entry.pack(fill=tk.X, ipady=2, pady=(1, 2))

        no_jump_row = tk.Frame(no_col, bg=COLOR_PANEL_ALT)
        no_jump_row.pack(fill=tk.X)
        self.no_jump_lbl = tk.Label(no_jump_row, text=t("lbl_jump_step"), font=("Segoe UI", 7), bg=COLOR_PANEL_ALT, fg=COLOR_TEXT_DIM)
        self.no_jump_lbl.pack(side=tk.LEFT)
        self.no_step_var = tk.IntVar(value=0)
        self.no_jump_spin = tk.Spinbox(no_jump_row, from_=0, to=999, textvariable=self.no_step_var, width=5, bg=COLOR_INPUT_BG, fg=COLOR_TEXT_MAIN, relief=tk.FLAT)
        self.no_jump_spin.pack(side=tk.LEFT, padx=(4, 0))
        tk.Label(no_jump_row, text="(0 = bước kế)", font=("Segoe UI", 7), bg=COLOR_PANEL_ALT, fg=COLOR_TEXT_DIM).pack(side=tk.LEFT, padx=(4, 0))

        # ================= INTERACTIVE DRAWING STUDIO TOOLBAR =================
        tool_frame = tk.Frame(
            right_frame,
            bg=COLOR_PANEL_ALT,
            padx=8,
            pady=4,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1
        )
        tool_frame.pack(fill=tk.X, pady=(2, 2))

        # Tool buttons dictionary
        self.tool_btns: Dict[str, tk.Button] = {}

        # 1. Focus / Highlight
        self.tool_btns["highlight"] = tk.Button(
            tool_frame,
            text=t("tool_highlight"),
            command=lambda: self._set_active_tool("highlight"),
            bg="#0369a1", fg="#ffffff",
            activebackground="#0284c7",
            font=("Segoe UI", 8, "bold"),
            relief=tk.FLAT, padx=7, pady=2, cursor="hand2"
        )
        self.tool_btns["highlight"].pack(side=tk.LEFT, padx=(0, 3))

        # 2. Blur Privacy
        self.tool_btns["blur"] = tk.Button(
            tool_frame,
            text=t("tool_blur"),
            command=lambda: self._set_active_tool("blur"),
            bg=COLOR_INPUT_BG, fg=COLOR_TEXT_MUTED,
            activebackground=COLOR_PURPLE,
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=7, pady=2, cursor="hand2"
        )
        self.tool_btns["blur"].pack(side=tk.LEFT, padx=(0, 3))

        # 3. Redact Blackout
        self.tool_btns["redact"] = tk.Button(
            tool_frame,
            text=t("tool_redact"),
            command=lambda: self._set_active_tool("redact"),
            bg=COLOR_INPUT_BG, fg=COLOR_TEXT_MUTED,
            activebackground="#334155",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=7, pady=2, cursor="hand2"
        )
        self.tool_btns["redact"].pack(side=tk.LEFT, padx=(0, 3))

        # 4. Red Attention Box
        self.tool_btns["red_box"] = tk.Button(
            tool_frame,
            text=t("tool_red_box"),
            command=lambda: self._set_active_tool("red_box"),
            bg=COLOR_INPUT_BG, fg=COLOR_TEXT_MUTED,
            activebackground=COLOR_ROSE,
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=7, pady=2, cursor="hand2"
        )
        self.tool_btns["red_box"].pack(side=tk.LEFT, padx=(0, 3))

        # 5. Crop Tool
        self.tool_btns["crop"] = tk.Button(
            tool_frame,
            text=t("tool_crop"),
            command=lambda: self._set_active_tool("crop"),
            bg=COLOR_INPUT_BG, fg=COLOR_TEXT_MUTED,
            activebackground=COLOR_AMBER,
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=7, pady=2, cursor="hand2"
        )
        self.tool_btns["crop"].pack(side=tk.LEFT, padx=(0, 8))

        # Right utility actions: Reset to Raw & Undo
        self.reset_marker_btn = tk.Button(
            tool_frame,
            text=t("btn_reset_raw"),
            command=self._reset_to_raw,
            bg=COLOR_INPUT_BG, fg=COLOR_TEXT_MUTED,
            activebackground="#1e293b",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=7, pady=2, cursor="hand2"
        )
        self.reset_marker_btn.pack(side=tk.RIGHT)
        bind_hover(self.reset_marker_btn, COLOR_INPUT_BG, "#1e293b", COLOR_TEXT_MUTED, COLOR_TEXT_MAIN)

        self.undo_btn = tk.Button(
            tool_frame,
            text=t("btn_undo"),
            command=self._undo_last_action,
            bg=COLOR_INPUT_BG, fg=COLOR_TEXT_MUTED,
            activebackground="#1e293b",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=7, pady=2, cursor="hand2"
        )
        self.undo_btn.pack(side=tk.RIGHT, padx=(0, 4))
        bind_hover(self.undo_btn, COLOR_INPUT_BG, "#1e293b", COLOR_TEXT_MUTED, COLOR_TEXT_MAIN)

        # Dynamic Tool Instruction Hint Bar
        hint_bar = tk.Frame(right_frame, bg=COLOR_PANEL)
        hint_bar.pack(fill=tk.X, pady=(2, 3))

        self.tool_hint_lbl = tk.Label(
            hint_bar,
            text=f"💡 {t('drag_hint_highlight')}",
            font=("Segoe UI", 8),
            bg=COLOR_PANEL,
            fg=COLOR_TEXT_MUTED
        )
        self.tool_hint_lbl.pack(side=tk.LEFT)

        self.canvas_dim_lbl = tk.Label(
            hint_bar,
            text="",
            font=("Consolas", 8),
            bg=COLOR_PANEL,
            fg=COLOR_TEXT_DIM
        )
        self.canvas_dim_lbl.pack(side=tk.RIGHT)

        # Canvas for Screenshot Display & Interactive Drawing
        self.preview_canvas = tk.Canvas(
            right_frame,
            bg="#030712",
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            cursor="cross"
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.preview_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.preview_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        # Bottom row of right pane: Apply changes button
        apply_row = tk.Frame(right_frame, bg=COLOR_PANEL)
        apply_row.pack(fill=tk.X)

        self.save_hint_lbl = tk.Label(
            apply_row,
            text="Ctrl+S: Cập nhật | Ctrl+Z: Hoàn tác",
            font=("Segoe UI", 7),
            bg=COLOR_PANEL,
            fg=COLOR_TEXT_DIM
        )
        self.save_hint_lbl.pack(side=tk.LEFT)

        self.update_step_btn = tk.Button(
            apply_row,
            text=t("btn_apply_step"),
            command=self._apply_current_step_edits,
            bg="#0284c7", fg="#ffffff",
            activebackground="#0369a1",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=16, pady=4, cursor="hand2"
        )
        self.update_step_btn.pack(side=tk.RIGHT)
        bind_hover(self.update_step_btn, "#0284c7", "#0ea5e9")

        # ================= BOTTOM ACTION BAR =================
        bottom_bar = tk.Frame(main_frame, bg=COLOR_BG)
        bottom_bar.pack(fill=tk.X, pady=(10, 0))

        # Left shortcut badge
        self.kb_shortcut_lbl = tk.Label(
            bottom_bar,
            text="⌨️ Ctrl+S: Lưu bước | Ctrl+Z: Hoàn tác | Ctrl+E: Xuất file | Del: Xóa | Esc: Đóng",
            font=("Segoe UI", 8),
            bg=COLOR_BG,
            fg=COLOR_TEXT_DIM
        )
        self.kb_shortcut_lbl.pack(side=tk.LEFT)

        # Right actions
        self.cancel_btn = tk.Button(
            bottom_bar,
            text=t("btn_close_editor"),
            command=self.window.destroy,
            bg=COLOR_PANEL, fg="#cbd5e1",
            activebackground="#1e293b",
            font=("Segoe UI", 9),
            relief=tk.FLAT, padx=14, pady=5, cursor="hand2"
        )
        self.cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))
        bind_hover(self.cancel_btn, COLOR_PANEL, "#1e293b", "#cbd5e1", "#ffffff")

        self.export_btn = tk.Button(
            bottom_bar,
            text=t("btn_export_report"),
            command=self._export_final_report,
            bg="#059669", fg="#ffffff",
            activebackground="#10b981",
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT, padx=20, pady=5, cursor="hand2"
        )
        self.export_btn.pack(side=tk.RIGHT)
        bind_hover(self.export_btn, "#059669", "#10b981")

    def _set_active_tool(self, tool_name: str) -> None:
        """Switch active drawing tool on the toolbar with dynamic styling."""
        self.active_tool = tool_name

        tool_active_colors = {
            "highlight": ("#0369a1", "#0284c7"),
            "blur": ("#6d28d9", "#7c3aed"),
            "redact": ("#334155", "#475569"),
            "red_box": ("#be123c", "#e11d48"),
            "crop": ("#b45309", "#d97706"),
        }

        # Update button highlights
        for name, btn in self.tool_btns.items():
            if name == tool_name:
                bg_col, _ = tool_active_colors.get(name, ("#0369a1", "#0284c7"))
                btn.configure(bg=bg_col, fg="#ffffff", font=("Segoe UI", 8, "bold"))
            else:
                btn.configure(bg=COLOR_INPUT_BG, fg=COLOR_TEXT_MUTED, font=("Segoe UI", 8))

        # Update instruction hint label
        hint_key = f"drag_hint_{tool_name}"
        self.tool_hint_lbl.configure(text=f"💡 {t(hint_key)}")

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

    def _on_decision_chk_changed(self) -> None:
        """Show or hide decision inputs based on checkbox."""
        if self.is_decision_var.get():
            self.decision_inputs_frame.pack(fill=tk.X, pady=(2, 0))
            if not self.cond_q_var.get():
                self.cond_q_entry.focus_set()
        else:
            self.decision_inputs_frame.pack_forget()

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
        if hasattr(self, "undo_del_btn"):
            self.undo_del_btn.configure(text=t("btn_undo_delete"))
        if hasattr(self, "select_all_btn"):
            self.select_all_btn.configure(text=t("btn_select_all"))
        self._update_selection_buttons()
        self._update_undo_button_state()
        self.up_btn.configure(text=t("btn_move_up"))
        self.down_btn.configure(text=t("btn_move_down"))
        self.desc_lbl.configure(text=t("desc_label"))
        self.comment_lbl.configure(text=t("comment_label"))
        self.sec_chk.configure(text=t("chk_section_header"))
        self.sec_title_lbl.configure(text=t("lbl_section_title"))
        self.sec_desc_lbl.configure(text=t("lbl_section_desc"))
        self.decision_chk.configure(text=t("chk_decision_point"))
        self.cond_q_lbl.configure(text=t("lbl_condition_question"))
        self.yes_lbl.configure(text=t("lbl_yes_branch"))
        self.yes_jump_lbl.configure(text=t("lbl_jump_step"))
        self.no_lbl.configure(text=t("lbl_no_branch"))
        self.no_jump_lbl.configure(text=t("lbl_jump_step"))
        self.tool_btns["highlight"].configure(text=t("tool_highlight"))
        self.tool_btns["blur"].configure(text=t("tool_blur"))
        self.tool_btns["redact"].configure(text=t("tool_redact"))
        self.tool_btns["red_box"].configure(text=t("tool_red_box"))
        self.tool_btns["crop"].configure(text=t("tool_crop"))
        self.undo_btn.configure(text=t("btn_undo"))
        self.reset_marker_btn.configure(text=t("btn_reset_raw"))
        self.tool_hint_lbl.configure(text=f"💡 {t(f'drag_hint_{self.active_tool}')}")
        self.update_step_btn.configure(text=t("btn_apply_step"))
        self.cancel_btn.configure(text=t("btn_close_editor"))
        self.export_btn.configure(text=t("btn_export_report"))

        if 0 <= self.current_index < len(self.steps):
            step = self.steps[self.current_index]
            self.step_badge_pill.configure(text=f" #{step.step_id:02d} ")
            action_key = f"action_name_{step.action_type}"
            action_name = t(action_key) if action_key in TRANSLATIONS else step.action_type.replace('_', ' ').title()
            self.action_pill.configure(text=f" {step.action_icon} {action_name} ")
            self.time_pill.configure(text=f" ⏱️ {step.time_str} ")
            self.window_tag_lbl.configure(text=f"🪟 {step.window_title[:45]}")

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
                or query in (s.condition_question or "").lower()
                or query in (s.yes_branch_text or "").lower()
                or query in (s.no_branch_text or "").lower()
            ]
        self._populate_list()

    def _populate_list(self) -> None:
        """Refresh Listbox items with filtered steps, branch badges, and chapter headers."""
        self.step_listbox.delete(0, tk.END)
        sec_num = 0
        for i in self.filtered_indices:
            s = self.steps[i]
            prefix = ""
            if s.is_section_header:
                sec_num += 1
                sec_display = s.section_title or f"Phần {sec_num}"
                if len(sec_display) > 18:
                    sec_display = sec_display[:18] + "..."
                prefix = f"📑 [P.{sec_num}: {sec_display}] "

            icon = s.action_icon
            desc_short = (s.description[:26] + "...") if len(s.description) > 26 else s.description
            decision_tag = " [🔀 Y/N]" if s.is_decision_point else ""
            comment_tag = " [💬]" if s.user_comment else ""
            self.step_listbox.insert(tk.END, f"{prefix}#{s.step_id:02d} {icon} {desc_short}{decision_tag}{comment_tag}")

        self.total_lbl.configure(text=t("total_steps", count=len(self.steps)))

        if 0 <= self.current_index < len(self.steps):
            self.list_footer_lbl.configure(
                text=f"Đang xem: Bước #{self.steps[self.current_index].step_id} / {len(self.steps)}"
            )

    def _on_list_select(self, event=None) -> None:
        """Handle selection change in the step listbox."""
        selected = self.step_listbox.curselection()
        self._update_selection_buttons()

        if not selected:
            return

        # Find the active or last selected index to display in preview
        target_list_idx = self.step_listbox.index(tk.ACTIVE)
        if target_list_idx not in selected:
            target_list_idx = selected[-1]

        if target_list_idx < len(self.filtered_indices):
            real_idx = self.filtered_indices[target_list_idx]
            self._display_step_details(real_idx)

    def _display_step_details(self, index: int) -> None:
        """Update form inputs and preview canvas for a step without altering listbox selection."""
        if index < 0 or index >= len(self.steps):
            return

        self.current_index = index
        step = self.steps[index]

        # Update stylized header card
        self.step_badge_pill.configure(text=f" #{step.step_id:02d} ")
        action_key = f"action_name_{step.action_type}"
        action_name = t(action_key) if action_key in TRANSLATIONS else step.action_type.replace('_', ' ').title()
        self.action_pill.configure(text=f" {step.action_icon} {action_name} ")
        self.time_pill.configure(text=f" ⏱️ {step.time_str} ")
        self.window_tag_lbl.configure(text=f"🪟 {step.window_title[:45]}")

        # Update input fields
        self.desc_var.set(step.description)
        self.comment_var.set(step.user_comment or "")
        self.is_section_var.set(bool(step.is_section_header))
        self.sec_title_var.set(step.section_title or "")
        self.sec_desc_var.set(step.section_description or "")
        self._on_section_chk_changed()

        self.is_decision_var.set(bool(step.is_decision_point))
        self.cond_q_var.set(step.condition_question or "")
        self.yes_text_var.set(step.yes_branch_text or "")
        self.yes_step_var.set(step.yes_next_step or 0)
        self.no_text_var.set(step.no_branch_text or "")
        self.no_step_var.set(step.no_next_step or 0)
        self._on_decision_chk_changed()

        # Update footer text if single selection
        selected = self.step_listbox.curselection()
        if len(selected) <= 1:
            self.list_footer_lbl.configure(
                text=f"Đang xem: Bước #{step.step_id} / {len(self.steps)}"
            )

        # Render preview image
        self._render_step_preview(step)

    def _select_step(self, index: int) -> None:
        """Select a single step in listbox and show its details."""
        if index < 0 or index >= len(self.steps):
            return

        try:
            if index in self.filtered_indices:
                list_idx = self.filtered_indices.index(index)
                self.step_listbox.selection_clear(0, tk.END)
                self.step_listbox.selection_set(list_idx)
                self.step_listbox.activate(list_idx)
                self.step_listbox.see(list_idx)
        except Exception:
            pass

        self._display_step_details(index)
        self._update_selection_buttons()

    def _update_selection_buttons(self) -> None:
        """Update delete and select-all buttons based on current selection."""
        selected = self.step_listbox.curselection()
        num_selected = len(selected)
        total_visible = len(self.filtered_indices)

        if not selected:
            self.del_btn.configure(text=t("btn_delete_step"), state=tk.DISABLED)
            self.up_btn.configure(state=tk.DISABLED)
            self.down_btn.configure(state=tk.DISABLED)
            if hasattr(self, "select_all_btn"):
                self.select_all_btn.configure(text=t("btn_select_all"))
            return

        self.del_btn.configure(state=tk.NORMAL)
        if hasattr(self, "select_all_btn"):
            if num_selected >= total_visible and total_visible > 0:
                self.select_all_btn.configure(text=t("btn_deselect_all"))
            else:
                self.select_all_btn.configure(text=t("btn_select_all"))

        if num_selected > 1:
            self.del_btn.configure(text=t("btn_delete_multi", count=num_selected))
            self.list_footer_lbl.configure(
                text=t("status_selected_count", selected=num_selected, total=len(self.steps))
            )
            self.up_btn.configure(state=tk.DISABLED)
            self.down_btn.configure(state=tk.DISABLED)
        else:
            self.del_btn.configure(text=t("btn_delete_step"))
            self.up_btn.configure(state=tk.NORMAL)
            self.down_btn.configure(state=tk.NORMAL)
            if selected[0] < len(self.filtered_indices):
                step = self.steps[self.filtered_indices[selected[0]]]
                self.list_footer_lbl.configure(
                    text=f"Đang xem: Bước #{step.step_id} / {len(self.steps)}"
                )

    def _toggle_select_all(self) -> None:
        """Toggle between selecting all visible steps and clearing selection."""
        selected = self.step_listbox.curselection()
        total_visible = len(self.filtered_indices)

        if len(selected) >= total_visible and total_visible > 0:
            self.step_listbox.selection_clear(0, tk.END)
            self._update_selection_buttons()
        else:
            self.step_listbox.selection_set(0, tk.END)
            self._on_list_select()

    def _select_all_steps(self) -> None:
        """Select all visible steps in the listbox."""
        if not self.steps:
            return
        self.step_listbox.selection_set(0, tk.END)
        self._on_list_select()

    def _render_step_preview(self, step: Step) -> None:
        """Render screenshot of step inside the preview canvas with LRU scaling cache."""
        self.preview_canvas.delete("all")

        # Scale to fit canvas cleanly
        self.window.update_idletasks()
        cw = max(240, self.preview_canvas.winfo_width())
        ch = max(180, self.preview_canvas.winfo_height())

        cache_key = (step.step_id, cw, ch)
        if hasattr(self, "_preview_cache") and cache_key in self._preview_cache:
            photo, (disp_w, disp_h), (orig_w, orig_h), sx, sy = self._preview_cache[cache_key]
            self.preview_photo = photo
            self.raw_img_size = (orig_w, orig_h)
            self.preview_scale_x = sx
            self.preview_scale_y = sy
            offset_x = (cw - disp_w) // 2
            offset_y = (ch - disp_h) // 2
            self.canvas_img_offset = (offset_x, offset_y)
            self.preview_canvas.create_image(offset_x, offset_y, image=self.preview_photo, anchor="nw")
            self.canvas_dim_lbl.configure(text=f"📐 {orig_w} × {orig_h} px")
            return

        img_bytes = step.get_annotated_bytes() or step.get_raw_bytes()

        if not img_bytes:
            self.preview_canvas.create_text(
                220, 120, text=f"📷 {t('no_screenshot_available')}",
                fill=COLOR_TEXT_DIM, font=("Segoe UI", 10)
            )
            self.canvas_dim_lbl.configure(text="")
            return

        try:
            pil_img = Image.open(io.BytesIO(img_bytes))
            orig_w, orig_h = pil_img.size
            self.raw_img_size = (orig_w, orig_h)

            ratio = min(cw / orig_w, ch / orig_h)
            disp_w = max(10, int(orig_w * ratio))
            disp_h = max(10, int(orig_h * ratio))

            self.preview_scale_x = orig_w / disp_w
            self.preview_scale_y = orig_h / disp_h

            scaled_img = pil_img.resize((disp_w, disp_h), Image.Resampling.BILINEAR)
            self.preview_photo = ImageTk.PhotoImage(scaled_img)

            # Store in preview cache
            if not hasattr(self, "_preview_cache"):
                self._preview_cache = {}
            if len(self._preview_cache) > 25:
                self._preview_cache.pop(next(iter(self._preview_cache)))
            self._preview_cache[cache_key] = (self.preview_photo, (disp_w, disp_h), (orig_w, orig_h), self.preview_scale_x, self.preview_scale_y)

            # Center on canvas
            offset_x = (cw - disp_w) // 2
            offset_y = (ch - disp_h) // 2
            self.canvas_img_offset = (offset_x, offset_y)

            self.preview_canvas.create_image(
                offset_x, offset_y, image=self.preview_photo, anchor="nw"
            )

            # Update dimensions indicator
            self.canvas_dim_lbl.configure(text=f"📐 {orig_w} × {orig_h} px")
        except Exception as e:
            self.preview_canvas.create_text(
                220, 120, text=t("image_render_error", err=e),
                fill=COLOR_ROSE, font=("Segoe UI", 9)
            )

    # --- Interactive Highlighting, Privacy (Blur / Redact) & Crop ---
    def _on_canvas_press(self, event) -> None:
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def _on_canvas_drag(self, event) -> None:
        self.preview_canvas.delete("tool_drag_box")

        # Color outline based on active tool
        colors = {
            "highlight": COLOR_CYAN,
            "blur": COLOR_PURPLE,
            "redact": "#94a3b8",
            "red_box": COLOR_ROSE,
            "crop": COLOR_AMBER
        }
        outline_col = colors.get(self.active_tool, COLOR_CYAN)

        self.preview_canvas.create_rectangle(
            self.drag_start_x, self.drag_start_y, event.x, event.y,
            outline=outline_col, width=2, dash=(4, 2), tags="tool_drag_box"
        )

    def _push_undo(self, step: Step) -> None:
        """Save a snapshot of the current image state for undo."""
        current_bytes = step.get_annotated_bytes() or step.get_raw_bytes()
        if current_bytes:
            if step.step_id not in self.undo_stack:
                self.undo_stack[step.step_id] = []
            self.undo_stack[step.step_id].append(current_bytes)
            if len(self.undo_stack[step.step_id]) > 15:
                self.undo_stack[step.step_id].pop(0)

            self.action_history.append({
                "type": "drawing",
                "step_id": step.step_id,
                "prev_bytes": current_bytes
            })
            if len(self.action_history) > 40:
                self.action_history.pop(0)
            self._update_undo_button_state()

    def _undo_last_action(self) -> None:
        """
        Revert the most recent action in chronological order:
        - If last action was a step deletion, restore the deleted step(s) in place.
        - If last action was a drawing/crop/privacy action, revert the image bytes.
        """
        if not self.action_history:
            return

        action = self.action_history.pop()
        self._update_undo_button_state()
        action_type = action.get("type")

        if action_type == "delete_steps":
            items = action.get("items", [])
            self._apply_restore_deleted_steps(items)

        elif action_type == "drawing":
            step_id = action.get("step_id")
            prev_bytes = action.get("prev_bytes")
            for s in self.steps:
                if s.step_id == step_id:
                    s.annotated_image_bytes = prev_bytes
                    if hasattr(self, "_preview_cache"):
                        self._preview_cache = {k: v for k, v in self._preview_cache.items() if k[0] != step_id}
                    # Check if step has further drawing actions
                    has_more = any(
                        a.get("type") == "drawing" and a.get("step_id") == step_id
                        for a in self.action_history
                    )
                    if not has_more:
                        s._is_custom_edited = False
                    if 0 <= self.current_index < len(self.steps) and self.steps[self.current_index].step_id == step_id:
                        self._render_step_preview(s)
                    break

    def _apply_restore_deleted_steps(self, items: List[Tuple[int, Step]]) -> None:
        """Re-insert deleted steps back into the list at their original positions."""
        if not items:
            return

        restored_indices = []
        # Re-insert items in ascending order of original index
        for orig_idx, step_obj in items:
            insert_pos = min(orig_idx, len(self.steps))
            self.steps.insert(insert_pos, step_obj)
            restored_indices.append(insert_pos)

        min_idx = min(restored_indices)
        self._renumber_steps(from_index=min_idx)
        self._on_filter_changed()

        # Select and highlight all restored steps in the listbox
        self.step_listbox.selection_clear(0, tk.END)
        for r_idx in restored_indices:
            if r_idx in self.filtered_indices:
                list_pos = self.filtered_indices.index(r_idx)
                self.step_listbox.selection_set(list_pos)

        self._display_step_details(min_idx)
        self._update_selection_buttons()

    def _undo_delete_only(self) -> None:
        """Specifically undo the most recent step deletion."""
        for i in range(len(self.action_history) - 1, -1, -1):
            if self.action_history[i].get("type") == "delete_steps":
                action = self.action_history.pop(i)
                self._apply_restore_deleted_steps(action.get("items", []))
                self._update_undo_button_state()
                return

    def _update_undo_button_state(self) -> None:
        """Update enabled/disabled state for Undo and Undo-Delete buttons."""
        has_undo = bool(self.action_history)
        has_del_undo = any(a.get("type") == "delete_steps" for a in self.action_history)

        state_all = tk.NORMAL if has_undo else tk.DISABLED
        state_del = tk.NORMAL if has_del_undo else tk.DISABLED

        if hasattr(self, "undo_btn"):
            self.undo_btn.configure(state=state_all)
        if hasattr(self, "undo_del_btn"):
            self.undo_del_btn.configure(state=state_del)

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

        base_bytes = step.get_annotated_bytes() or step.get_raw_bytes()
        if not base_bytes:
            return

        raw_bytes = step.get_raw_bytes() or base_bytes

        def _finish_tool_apply(result_img: Image.Image):
            step.annotated_image_bytes = ScreenCapture.image_to_bytes(result_img)
            step.thumbnail_bytes = ScreenCapture.image_to_bytes(ScreenCapture.create_thumbnail(result_img))
            if hasattr(self, "_preview_cache"):
                self._preview_cache = {k: v for k, v in self._preview_cache.items() if k[0] != step.step_id}
            if step.spool_annotated_path and os.path.exists(step.spool_annotated_path):
                try:
                    with open(step.spool_annotated_path, "wb") as f:
                        f.write(step.annotated_image_bytes)
                except Exception:
                    pass
            self._render_step_preview(step)

        # Execute according to active tool
        if self.active_tool == "highlight":
            self._push_undo(step)
            step.highlight_rect = rect
            base_img = Image.open(io.BytesIO(raw_bytes))
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
            _finish_tool_apply(annotated)

        elif self.active_tool == "blur":
            self._push_undo(step)
            step._is_custom_edited = True
            base_img = Image.open(io.BytesIO(base_bytes))
            blurred = apply_blur_region(base_img, rect, radius=18)
            _finish_tool_apply(blurred)

        elif self.active_tool == "redact":
            self._push_undo(step)
            step._is_custom_edited = True
            base_img = Image.open(io.BytesIO(base_bytes))
            redacted = apply_redact_region(base_img, rect)
            _finish_tool_apply(redacted)

        elif self.active_tool == "red_box":
            self._push_undo(step)
            step._is_custom_edited = True
            base_img = Image.open(io.BytesIO(base_bytes))
            boxed = draw_box_annotation(base_img, rect, color_hex="#ef4444", width=3)
            _finish_tool_apply(boxed)

        elif self.active_tool == "crop":
            crop_w = x2 - x1
            crop_h = y2 - y1
            if messagebox.askyesno(
                t("crop_confirm_title"),
                t("crop_confirm_msg", w=crop_w, h=crop_h),
                parent=self.window
            ):
                self._push_undo(step)
                step._is_custom_edited = True
                base_img = Image.open(io.BytesIO(base_bytes))
                cropped = crop_image(base_img, rect)
                _finish_tool_apply(cropped)

    def _reset_to_raw(self) -> None:
        """Reset current step back to original raw unedited screenshot."""
        if 0 <= self.current_index < len(self.steps):
            step = self.steps[self.current_index]
            raw_b = step.get_raw_bytes()
            if raw_b:
                self._push_undo(step)
                step.highlight_rect = None
                step._is_custom_edited = False
                base_img = Image.open(io.BytesIO(raw_b))
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
                if hasattr(self, "_preview_cache"):
                    self._preview_cache = {k: v for k, v in self._preview_cache.items() if k[0] != step.step_id}
                self.undo_stack[step.step_id] = []
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
            self.action_history.clear()
            self._update_undo_button_state()
            self._renumber_steps(from_index=0)
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

            self._renumber_steps(from_index=insert_idx)
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
        """Save text description, comment, section and decision changes for selected step."""
        if 0 <= self.current_index < len(self.steps):
            step = self.steps[self.current_index]
            step.description = self.desc_var.get().strip() or step.description
            step.user_comment = self.comment_var.get().strip() or None
            step.is_section_header = self.is_section_var.get()
            step.section_title = self.sec_title_var.get().strip() if step.is_section_header else None
            step.section_description = self.sec_desc_var.get().strip() if step.is_section_header else None
            step.is_decision_point = self.is_decision_var.get()
            step.condition_question = self.cond_q_var.get().strip() if step.is_decision_point else None
            step.yes_branch_text = self.yes_text_var.get().strip() if step.is_decision_point else None
            step.yes_next_step = self.yes_step_var.get() if (step.is_decision_point and self.yes_step_var.get() > 0) else None
            step.no_branch_text = self.no_text_var.get().strip() if step.is_decision_point else None
            step.no_next_step = self.no_step_var.get() if (step.is_decision_point and self.no_step_var.get() > 0) else None

            # Refresh list item text
            self._on_filter_changed()
            messagebox.showinfo(t("editor_title"), t("step_updated_msg", id=step.step_id), parent=self.window)

    def _renumber_steps(self, from_index: int = 0) -> None:
        """
        Instantly renumber all steps sequentially (#1..N) in memory with 0ms latency.
        Badge re-burning on screenshot images is executed asynchronously in a background
        thread so the UI remains completely responsive without freezing.
        """
        needs_badge_refresh = []
        for i, s in enumerate(self.steps):
            old_id = s.step_id
            new_id = i + 1
            s.step_id = new_id

            # Only steps at or after the modification point whose ID changed
            # and that have not been manually edited/blurred/cropped need badge re-burning
            if i >= from_index and old_id != new_id:
                if self.config.show_step_badge_on_screenshot and s.raw_image_bytes and not getattr(s, "_is_custom_edited", False):
                    needs_badge_refresh.append(s)

        if needs_badge_refresh:
            self._queue_background_badge_refresh(needs_badge_refresh)

    def _queue_background_badge_refresh(self, steps: List[Step]) -> None:
        """Process badge re-rendering asynchronously in background thread."""
        self._badge_refresh_generation += 1
        gen = self._badge_refresh_generation

        # Snapshot task items to avoid race conditions
        tasks = []
        for s in steps:
            if s.raw_image_bytes and not getattr(s, "_is_custom_edited", False):
                tasks.append((s, s.step_id, s.cursor_x, s.cursor_y, s.highlight_rect, s.raw_image_bytes))

        if not tasks:
            return

        def _worker():
            for step_obj, target_step_id, cx, cy, h_rect, raw_bytes in tasks:
                if gen != self._badge_refresh_generation:
                    return

                try:
                    base_img = Image.open(io.BytesIO(raw_bytes))
                    c_pos = (cx, cy) if cx is not None else None
                    annotated = annotate_screenshot(
                        base_img,
                        cursor_pos=c_pos,
                        step_id=target_step_id,
                        highlight_rect=h_rect,
                        color_hex=self.config.highlight_color,
                        radius=self.config.highlight_radius,
                        style=self.config.highlight_style,
                        show_badge=self.config.show_step_badge_on_screenshot
                    )
                    png_bytes = ScreenCapture.image_to_bytes(annotated)

                    if gen != self._badge_refresh_generation:
                        return

                    step_obj.annotated_image_bytes = png_bytes

                    # If this step is currently viewed in preview canvas, update it
                    self.window.after(0, lambda sid=target_step_id: self._on_step_bg_refreshed(sid, gen))
                except Exception:
                    pass

        t = threading.Thread(target=_worker, daemon=True)
        self._active_badge_thread = t
        t.start()

    def _on_step_bg_refreshed(self, step_id: int, gen: int) -> None:
        """Safely refresh preview canvas on main thread if the viewed step was updated."""
        if gen != self._badge_refresh_generation:
            return
        if 0 <= self.current_index < len(self.steps):
            if self.steps[self.current_index].step_id == step_id:
                self._render_step_preview(self.steps[self.current_index])

    def _renumber_and_refresh_badges(self) -> None:
        """Compatibility wrapper for legacy callers."""
        self._renumber_steps(from_index=0)

    def _delete_current_step(self) -> None:
        """Delete currently selected step(s) with undo capability and instant renumbering."""
        if not self.steps:
            return

        selected_list_indices = self.step_listbox.curselection()
        if not selected_list_indices:
            if 0 <= self.current_index < len(self.steps):
                if self.current_index in self.filtered_indices:
                    selected_list_indices = (self.filtered_indices.index(self.current_index),)
                else:
                    return
            else:
                return

        # Map listbox indices to real step indices
        real_indices = sorted(list(set(
            self.filtered_indices[i] for i in selected_list_indices if i < len(self.filtered_indices)
        )))
        if not real_indices:
            return

        count = len(real_indices)
        if count == 1:
            del_id = self.steps[real_indices[0]].step_id
            msg = t("confirm_delete_msg", id=del_id)
        else:
            msg = t("confirm_delete_multi_msg", count=count)

        if messagebox.askyesno(t("confirm_delete_title"), msg, parent=self.window):
            # Save deleted steps to action history for UNDO
            deleted_items = [(idx, self.steps[idx]) for idx in real_indices]
            self.action_history.append({
                "type": "delete_steps",
                "items": deleted_items
            })
            self._update_undo_button_state()

            # Remove steps in reverse order so earlier indices remain valid
            for idx in reversed(real_indices):
                self.steps.pop(idx)

            first_del_idx = real_indices[0]
            self._renumber_steps(from_index=first_del_idx)
            self._on_filter_changed()

            if self.steps:
                new_idx = min(first_del_idx, len(self.steps) - 1)
                self._select_step(new_idx)
            else:
                self.current_index = -1
                self.desc_var.set("")
                self.comment_var.set("")
                self.is_section_var.set(False)
                self.sec_title_var.set("")
                self.sec_desc_var.set("")
                self.is_decision_var.set(False)
                self.cond_q_var.set("")
                self.yes_text_var.set("")
                self.yes_step_var.set(0)
                self.no_text_var.set("")
                self.no_step_var.set(0)
                self._on_decision_chk_changed()
                self.preview_canvas.delete("all")
                self.step_badge_pill.configure(text="#00")
                self.action_pill.configure(text=t("no_steps_left"))
                self.time_pill.configure(text="")
                self.window_tag_lbl.configure(text="")
                self.canvas_dim_lbl.configure(text="")

            self._update_selection_buttons()

    def _move_step_up(self) -> None:
        """Move selected step up in sequence instantly."""
        idx = self.current_index
        if idx > 0:
            self.steps[idx - 1], self.steps[idx] = self.steps[idx], self.steps[idx - 1]
            self._renumber_steps(from_index=idx - 1)
            self._on_filter_changed()
            self._select_step(idx - 1)

    def _move_step_down(self) -> None:
        """Move selected step down in sequence instantly."""
        idx = self.current_index
        if 0 <= idx < len(self.steps) - 1:
            self.steps[idx + 1], self.steps[idx] = self.steps[idx], self.steps[idx + 1]
            self._renumber_steps(from_index=idx)
            self._on_filter_changed()
            self._select_step(idx + 1)

    # --- Final Export ---
    def _export_final_report(self) -> None:
        """Export edited steps into HTML, Markdown, and ZIP archive."""
        if not self.steps:
            messagebox.showwarning(t("editor_title"), t("export_empty_warning"), parent=self.window)
            return

        # Wait up to 1.5s for any background badge refresh thread if running
        if self._active_badge_thread and self._active_badge_thread.is_alive():
            try:
                self._active_badge_thread.join(timeout=1.5)
            except Exception:
                pass

        # Ensure active inputs are applied
        if 0 <= self.current_index < len(self.steps):
            cur = self.steps[self.current_index]
            cur.description = self.desc_var.get().strip() or cur.description
            cur.user_comment = self.comment_var.get().strip() or None
            cur.is_section_header = self.is_section_var.get()
            cur.section_title = self.sec_title_var.get().strip() if cur.is_section_header else None
            cur.section_description = self.sec_desc_var.get().strip() if cur.is_section_header else None
            cur.is_decision_point = self.is_decision_var.get()
            cur.condition_question = self.cond_q_var.get().strip() if cur.is_decision_point else None
            cur.yes_branch_text = self.yes_text_var.get().strip() if cur.is_decision_point else None
            cur.yes_next_step = self.yes_step_var.get() if (cur.is_decision_point and self.yes_step_var.get() > 0) else None
            cur.no_branch_text = self.no_text_var.get().strip() if cur.is_decision_point else None
            cur.no_next_step = self.no_step_var.get() if (cur.is_decision_point and self.no_step_var.get() > 0) else None

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
