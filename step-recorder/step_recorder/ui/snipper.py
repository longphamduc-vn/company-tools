"""
Screen Snipper overlay tool for selecting a highlight region on screen.
Freezes screen and allows user to drag a rectangle to focus on a UI element.
"""

import sys
import tkinter as tk
from typing import Tuple, Optional, Callable
from PIL import Image, ImageTk, ImageDraw

from ..capture import ScreenCapture


class ScreenSnipper:
    """Full-screen interactive overlay for selecting a highlight / focus region."""

    def __init__(
        self,
        parent: tk.Tk,
        on_complete: Callable[[Optional[Tuple[int, int, int, int]], Image.Image], None]
    ):
        self.parent = parent
        self.on_complete = on_complete
        self.capture = ScreenCapture()

        # Capture current screen before opening overlay
        self.raw_image, self.mon_left, self.mon_top = self.capture.capture_full_screen()

        self.start_x = 0
        self.start_y = 0
        self.current_x = 0
        self.current_y = 0
        self.rect_id = None
        self.text_id = None

        self._create_overlay()

    def _create_overlay(self) -> None:
        self.top = tk.Toplevel(self.parent)
        self.top.title("Select Highlight / Focus Region")
        self.top.attributes("-topmost", True)
        
        # Make full screen borderless
        if sys.platform == "win32":
            self.top.state("zoomed")
        self.top.attributes("-fullscreen", True)
        self.top.configure(cursor="cross")

        # Create dimmed background image
        dimmed_img = self.raw_image.copy().convert("RGBA")
        darken_layer = Image.new("RGBA", dimmed_img.size, (0, 0, 0, 110))
        dimmed_img = Image.alpha_composite(dimmed_img, darken_layer).convert("RGB")

        # Scale to canvas size if needed
        self.photo = ImageTk.PhotoImage(dimmed_img)

        self.canvas = tk.Canvas(self.top, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")

        # Instructions banner at the top
        banner_w = 480
        banner_h = 36
        cx = self.top.winfo_screenwidth() // 2
        self.canvas.create_rectangle(
            cx - banner_w // 2, 16, cx + banner_w // 2, 16 + banner_h,
            fill="#0f172a", outline="#38bdf8", width=2
        )
        self.canvas.create_text(
            cx, 16 + banner_h // 2,
            text="🎯 Kéo chuột để chọn vùng Focus / Highlight (Nhấn Esc để hủy)",
            fill="#f8fafc", font=("Segoe UI", 10, "bold")
        )

        # Event bindings
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.top.bind("<Escape>", self._on_cancel)
        self.top.focus_force()

    def _on_press(self, event) -> None:
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        if self.text_id:
            self.canvas.delete(self.text_id)

    def _on_drag(self, event) -> None:
        self.current_x = event.x
        self.current_y = event.y

        if self.rect_id:
            self.canvas.delete(self.rect_id)
        if self.text_id:
            self.canvas.delete(self.text_id)

        # Draw highlight selection rectangle with bright border
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.current_x, self.current_y,
            outline="#38bdf8", width=3, dash=(4, 2)
        )

        w = abs(self.current_x - self.start_x)
        h = abs(self.current_y - self.start_y)
        self.text_id = self.canvas.create_text(
            max(self.start_x, self.current_x) + 5,
            max(self.start_y, self.current_y) + 12,
            text=f"{w}x{h}", fill="#38bdf8", font=("Segoe UI", 9, "bold"),
            anchor="nw"
        )

    def _on_release(self, event) -> None:
        end_x = event.x
        end_y = event.y

        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        # Only count as a rectangle if dragged > 10px
        if (x2 - x1) > 10 and (y2 - y1) > 10:
            selected_rect = (x1, y1, x2, y2)
        else:
            selected_rect = None

        self.top.destroy()
        self.on_complete(selected_rect, self.raw_image)

    def _on_cancel(self, event=None) -> None:
        self.top.destroy()
        self.on_complete(None, self.raw_image)

