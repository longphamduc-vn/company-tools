"""
Comment and region annotation dialog.
Allows user to type a note explaining the current step and select a highlight / focus region.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple, Callable
from PIL import Image

from ..window_info import exclude_window_from_capture
from ..i18n import t
from .snipper import ScreenSnipper
from .icon_utils import apply_window_icon


class CommentDialog:
    """Dialog for user to add comments, notes, and select focus regions on screen."""

    def __init__(
        self,
        parent: tk.Tk,
        on_submit: Callable[[str, Optional[Tuple[int, int, int, int]]], None]
    ):
        self.parent = parent
        self.on_submit = on_submit
        self.selected_rect: Optional[Tuple[int, int, int, int]] = None

        self.window = tk.Toplevel(parent)
        self.window.title(t("comment_win_title"))
        apply_window_icon(self.window)
        self.window.attributes("-topmost", True)
        self.window.transient(parent)
        self.window.configure(bg="#1e293b")

        self._build_ui()
        self._apply_geometry()

        self.window.after(50, lambda: exclude_window_from_capture(self.window))

        try:
            self.window.grab_set()
        except Exception:
            pass

    def _apply_geometry(self) -> None:
        """Calculate dynamic responsive geometry for high-DPI screens."""
        self.window.update_idletasks()
        req_w = max(580, self.window.winfo_reqwidth() + 20)
        req_h = max(380, self.window.winfo_reqheight() + 20)

        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        pos_x = max(20, (screen_w - req_w) // 2)
        pos_y = max(20, (screen_h - req_h) // 2)

        self.window.geometry(f"{req_w}x{req_h}+{pos_x}+{pos_y}")
        self.window.minsize(500, 320)
        self.window.resizable(True, True)

    def _build_ui(self) -> None:
        # Bottom Buttons frame packed FIRST with side=BOTTOM to guarantee visibility
        btn_frame = tk.Frame(self.window, bg="#0f172a", padx=18, pady=12, relief=tk.RAISED, bd=1)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        cancel_btn = tk.Button(
            btn_frame,
            text=t("btn_cancel"),
            command=self._cancel,
            bg="#334155",
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=14,
            pady=6,
            font=("Segoe UI", 9),
            cursor="hand2"
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))

        save_btn = tk.Button(
            btn_frame,
            text=t("btn_save_comment"),
            command=self._submit,
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=16,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2"
        )
        save_btn.pack(side=tk.RIGHT)

        # Top & Center Content frame
        main_frame = tk.Frame(self.window, bg="#1e293b", padx=18, pady=16)
        main_frame.pack(fill=tk.BOTH, expand=True)

        title_lbl = tk.Label(
            main_frame,
            text=t("comment_heading"),
            font=("Segoe UI", 11, "bold"),
            bg="#1e293b",
            fg="#f8fafc"
        )
        title_lbl.pack(anchor="w", pady=(0, 4))

        subtitle_lbl = tk.Label(
            main_frame,
            text=t("comment_subheading"),
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#94a3b8"
        )
        subtitle_lbl.pack(anchor="w", pady=(0, 8))

        # Text input area
        self.text_entry = tk.Text(
            main_frame,
            height=4,
            bg="#0f172a",
            fg="#f8fafc",
            insertbackground="#38bdf8",
            relief=tk.FLAT,
            font=("Segoe UI", 10),
            padx=10,
            pady=8
        )
        self.text_entry.pack(fill=tk.X, pady=(0, 10))
        self.text_entry.focus_set()

        # Highlight Snipping tool row
        snip_row = tk.Frame(main_frame, bg="#1e293b")
        snip_row.pack(fill=tk.X, pady=(0, 10))

        self.snip_btn = tk.Button(
            snip_row,
            text=t("btn_launch_snipper"),
            command=self._launch_snipper,
            bg="#334155",
            fg="#38bdf8",
            activebackground="#0284c7",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=10,
            pady=5,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2"
        )
        self.snip_btn.pack(side=tk.LEFT)

        self.region_lbl = tk.Label(
            snip_row,
            text=t("region_fullscreen"),
            font=("Segoe UI", 8),
            bg="#1e293b",
            fg="#64748b"
        )
        self.region_lbl.pack(side=tk.LEFT, padx=(10, 0))

        # Section Header Checkbox & Title Entry
        sec_box = tk.Frame(main_frame, bg="#1e293b")
        sec_box.pack(fill=tk.X, pady=(0, 6))

        self.is_section_var = tk.BooleanVar(value=False)
        self.sec_chk = tk.Checkbutton(
            sec_box,
            text=t("comment_chk_section"),
            variable=self.is_section_var,
            command=self._on_section_chk_toggled,
            bg="#1e293b",
            fg="#cbd5e1",
            activebackground="#1e293b",
            activeforeground="#f8fafc",
            selectcolor="#0f172a",
            font=("Segoe UI", 9)
        )
        self.sec_chk.pack(anchor="w")

        self.sec_title_frame = tk.Frame(sec_box, bg="#1e293b")
        self.sec_title_lbl = tk.Label(
            self.sec_title_frame,
            text=t("comment_lbl_section_title"),
            font=("Segoe UI", 8),
            bg="#1e293b",
            fg="#94a3b8"
        )
        self.sec_title_lbl.pack(anchor="w", pady=(2, 2))
        self.sec_title_var = tk.StringVar()
        self.sec_title_entry = tk.Entry(
            self.sec_title_frame,
            textvariable=self.sec_title_var,
            bg="#0f172a",
            fg="#f8fafc",
            insertbackground="#38bdf8",
            relief=tk.FLAT,
            font=("Segoe UI", 9)
        )
        self.sec_title_entry.pack(fill=tk.X, ipady=3)

        # Key bindings
        self.window.bind("<Control-Return>", lambda e: self._submit())
        self.window.bind("<Escape>", lambda e: self._cancel())

    def _launch_snipper(self) -> None:
        """Temporarily hide comment dialog and show fullscreen region selector."""
        self.window.withdraw()
        ScreenSnipper(self.parent, on_complete=self._on_snip_completed)

    def _on_snip_completed(self, rect: Optional[Tuple[int, int, int, int]], raw_img: Image.Image) -> None:
        """Called when snipper selection is finished."""
        self.selected_rect = rect
        if rect:
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            self.region_lbl.configure(text=t("region_custom", x1=rect[0], y1=rect[1], w=w, h=h), fg="#10b981")
            self.snip_btn.configure(text=t("btn_snip_selected"), fg="#10b981")
        else:
            self.region_lbl.configure(text=t("region_fullscreen"), fg="#64748b")
            self.snip_btn.configure(text=t("btn_launch_snipper"), fg="#38bdf8")

        self.window.deiconify()
        self.window.attributes("-topmost", True)
        self.window.focus_force()
        self.text_entry.focus_set()

    def _on_section_chk_toggled(self) -> None:
        """Show or hide section title input based on checkbox."""
        if self.is_section_var.get():
            self.sec_title_frame.pack(fill=tk.X, pady=(4, 0))
            self.sec_title_entry.focus_set()
        else:
            self.sec_title_frame.pack_forget()

    def _submit(self) -> None:
        content = self.text_entry.get("1.0", tk.END).strip()
        if not content:
            content = t("default_comment_text")
        is_sec = self.is_section_var.get()
        sec_title = self.sec_title_var.get().strip() if is_sec else None
        if is_sec and not sec_title:
            sec_title = content.split('\n')[0][:50]

        try:
            self.on_submit(content, self.selected_rect, is_sec, sec_title)
        except TypeError:
            self.on_submit(content, self.selected_rect)

        self.window.destroy()

    def _cancel(self) -> None:
        self.window.destroy()
