"""
Comment and region annotation dialog.
Allows user to type a note explaining the current step and select a highlight / focus region.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple, Callable
from PIL import Image

from .snipper import ScreenSnipper


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
        self.window.title("Thêm Ghi Chú & Highlight Vùng Lỗi")
        self.window.attributes("-topmost", True)
        self.window.transient(parent)
        self.window.configure(bg="#1e293b")

        self._build_ui()
        self._apply_geometry()

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
            text="Hủy (Esc)",
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
            text="✓ Lưu Bước Ghi Chú (Ctrl+Enter)",
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
            text="💬 Thêm Ghi Chú / Mô Tả Lỗi (Comment)",
            font=("Segoe UI", 11, "bold"),
            bg="#1e293b",
            fg="#f8fafc"
        )
        title_lbl.pack(anchor="w", pady=(0, 4))

        subtitle_lbl = tk.Label(
            main_frame,
            text="Nhập mô tả vấn đề hoặc khoanh vùng khu vực cần Focus:",
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
        snip_row.pack(fill=tk.X, pady=(0, 12))

        self.snip_btn = tk.Button(
            snip_row,
            text="🎯 Khoanh vùng Focus / Highlight trên màn hình",
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
            text="Khu vực: Toàn màn hình",
            font=("Segoe UI", 8),
            bg="#1e293b",
            fg="#64748b"
        )
        self.region_lbl.pack(side=tk.LEFT, padx=(10, 0))

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
            self.region_lbl.configure(text=f"Đã chọn: ({rect[0]}, {rect[1]}) - {w}x{h} px", fg="#10b981")
            self.snip_btn.configure(text="✓ Đã khoanh vùng (Nhấn để chọn lại)", fg="#10b981")
        else:
            self.region_lbl.configure(text="Khu vực: Toàn màn hình", fg="#64748b")
            self.snip_btn.configure(text="🎯 Khoanh vùng Focus / Highlight trên màn hình", fg="#38bdf8")

        self.window.deiconify()
        self.window.attributes("-topmost", True)
        self.window.focus_force()
        self.text_entry.focus_set()

    def _submit(self) -> None:
        content = self.text_entry.get("1.0", tk.END).strip()
        if not content:
            content = "Ghi chú người dùng / User flagged observation"
        self.on_submit(content, self.selected_rect)
        self.window.destroy()

    def _cancel(self) -> None:
        self.window.destroy()
