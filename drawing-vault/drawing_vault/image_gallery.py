"""
Thumbnail Image Gallery & Card List View Component.
Displays downloaded blueprints as visual thumbnail cards in a responsive grid.
"""

import logging
import os
from typing import List, Optional, Callable, Dict

import tkinter as tk
from tkinter import ttk

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from lgd_vault.models import DownloadResult

logger = logging.getLogger("lgd_vault.gallery")


class ImageCard(ttk.Frame):
    """An individual visual thumbnail card for a blueprint drawing."""

    def __init__(
        self,
        parent,
        result: DownloadResult,
        on_select: Callable[[DownloadResult], None],
        on_double_click: Callable[[DownloadResult], None],
        thumb_image: Optional[ImageTk.PhotoImage] = None,
        is_active: bool = False,
        **kwargs,
    ):
        super().__init__(parent, relief="solid", borderwidth=2 if is_active else 1, padding=6, **kwargs)
        self.result = result
        self.on_select = on_select
        self.on_double_click = on_double_click

        # Border color for active card
        card_bg = "#ffffff"
        self.configure(style="Card.TFrame" if not is_active else "ActiveCard.TFrame")

        # 1. Image Thumbnail Label
        self.lbl_img = tk.Label(
            self,
            image=thumb_image,
            bg="#202225",
            width=200,
            height=130,
            cursor="hand2",
        )
        self.lbl_img.pack(fill=tk.BOTH, expand=True)

        # 2. Metadata Info
        info_frame = ttk.Frame(self)
        info_frame.pack(fill=tk.X, pady=(4, 0))

        qcode_lbl = ttk.Label(
            info_frame,
            text=result.qcode,
            font=("Segoe UI", 10, "bold"),
            foreground="#0052cc",
            cursor="hand2",
        )
        qcode_lbl.pack(anchor="w")

        alias_text = result.custom_name or "(No alias)"
        alias_lbl = ttk.Label(
            info_frame,
            text=alias_text,
            font=("Segoe UI", 8),
            foreground="#4a5568",
            cursor="hand2",
        )
        alias_lbl.pack(anchor="w")

        # Resolution & Size
        meta_sub = ttk.Frame(info_frame)
        meta_sub.pack(fill=tk.X, pady=(2, 0))

        res_str = f"{result.image_width}x{result.image_height}" if result.image_width > 0 else "-"
        size_str = f"{result.file_size_bytes / 1024:.1f} KB" if result.file_size_bytes > 0 else "-"

        ttk.Label(meta_sub, text=res_str, font=("Segoe UI", 8), foreground="#718096").pack(side=tk.LEFT)
        ttk.Label(meta_sub, text=size_str, font=("Segoe UI", 8), foreground="#718096").pack(side=tk.RIGHT)

        # Bind clicks to all child widgets
        for widget in (self, self.lbl_img, qcode_lbl, alias_lbl, info_frame, meta_sub):
            widget.bind("<Button-1>", lambda e: self.on_select(self.result))
            widget.bind("<Double-1>", lambda e: self.on_double_click(self.result))


class ThumbnailGalleryView(ttk.Frame):
    """
    Scrollable Grid Gallery displaying drawings as image thumbnail cards.
    """

    def __init__(
        self,
        parent,
        on_open_image: Callable[[DownloadResult], None],
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.on_open_image = on_open_image

        self.items: List[DownloadResult] = []
        self.selected_item: Optional[DownloadResult] = None
        self._thumb_cache: Dict[str, ImageTk.PhotoImage] = {}
        self.cards: List[ImageCard] = []

        self._build_ui()

    def _build_ui(self):
        # Canvas + Scrollbar for scrollable card grid
        self.canvas = tk.Canvas(self, bg="#f0f2f5", highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.grid_frame = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")

        self.grid_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Bind mouse wheel for scrolling
        self.canvas.bind_all("<MouseWheel>", self._on_mouse_wheel)

    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        # Resize grid frame width to fit canvas
        self.canvas.itemconfig(self.window_id, width=event.width)
        self._reposition_cards(event.width)

    def _on_mouse_wheel(self, event):
        # Only scroll if mouse is over this gallery
        widget = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        if widget and (widget == self.canvas or widget.master == self.grid_frame or widget == self.grid_frame):
            if sys.platform == "darwin":
                self.canvas.yview_scroll(int(-1 * event.delta), "units")
            else:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def set_items(self, items: List[DownloadResult]):
        """Sets data items and re-renders grid."""
        self.items = items
        self._render_cards()

    def select_item(self, result: DownloadResult):
        """Marks a card as currently active."""
        self.selected_item = result
        self._render_cards()

    def _render_cards(self):
        """Builds all card widgets."""
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.cards.clear()

        canv_w = self.canvas.winfo_width()
        if canv_w <= 10:
            canv_w = 800

        cols = max(1, canv_w // 230)

        for i, res in enumerate(self.items):
            thumb = self._get_thumbnail(res.local_path)
            is_active = (self.selected_item and self.selected_item.qcode == res.qcode and self.selected_item.local_path == res.local_path)

            card = ImageCard(
                self.grid_frame,
                result=res,
                thumb_image=thumb,
                is_active=is_active,
                on_select=self._handle_select,
                on_double_click=self.on_open_image,
            )
            r = i // cols
            c = i % cols
            card.grid(row=r, column=c, padx=8, pady=8, sticky="nsew")
            self.cards.append(card)

        # Configure columns equally
        for c in range(cols):
            self.grid_frame.grid_columnconfigure(c, weight=1)

    def _reposition_cards(self, width: int):
        if not self.cards:
            return
        cols = max(1, width // 230)
        for i, card in enumerate(self.cards):
            r = i // cols
            c = i % cols
            card.grid(row=r, column=c, padx=8, pady=8, sticky="nsew")

    def _handle_select(self, res: DownloadResult):
        self.selected_item = res
        self._render_cards()
        self.on_open_image(res)

    def _get_thumbnail(self, path: Optional[str]) -> Optional[ImageTk.PhotoImage]:
        """Generates or retrieves cached thumbnail for a local image path."""
        if not HAS_PIL or not path or not os.path.isfile(path):
            return None

        if path in self._thumb_cache:
            return self._thumb_cache[path]

        try:
            with Image.open(path) as im:
                im.thumbnail((190, 125), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.ANTIALIAS)
                thumb = ImageTk.PhotoImage(im)
                self._thumb_cache[path] = thumb
                return thumb
        except Exception as e:
            logger.debug("Failed to create thumbnail for %s: %s", path, e)
            return None
