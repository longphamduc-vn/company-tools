"""
Screen capture engine using persistent mss session and Pillow.
Supports full desktop, cursor-aware monitor targeting, window bounding with padding,
fast WebP/PNG byte encoding, and thumbnail generation.
"""

import io
import os
import threading
from typing import Tuple, Optional, Dict, Any, List
from PIL import Image
import mss


class ScreenCapture:
    """Handles fast, low-overhead screen capturing with persistent driver context."""

    def __init__(self):
        # Compatible with both modern mss.MSS and legacy mss.mss
        if hasattr(mss, "MSS"):
            self._sct_cls = mss.MSS
        else:
            self._sct_cls = mss.mss
        self._lock = threading.RLock()
        self._sct = None

    def _get_sct(self) -> Any:
        """Get or initialize persistent thread-safe mss instance."""
        with self._lock:
            if self._sct is None:
                self._sct = self._sct_cls()
            return self._sct

    def close(self) -> None:
        """Release underlying screen capture driver handles."""
        with self._lock:
            if self._sct is not None:
                try:
                    self._sct.close()
                except Exception:
                    pass
                self._sct = None

    def get_monitor_for_point(self, x: int, y: int) -> Dict[str, Any]:
        """Find physical display monitor containing coordinate (x, y)."""
        with self._lock:
            sct = self._get_sct()
            monitors = sct.monitors
            if len(monitors) > 1:
                for m in monitors[1:]:
                    ml = m.get("left", 0)
                    mt = m.get("top", 0)
                    mw = m.get("width", 0)
                    mh = m.get("height", 0)
                    if ml <= x < ml + mw and mt <= y < mt + mh:
                        return m
                return monitors[1]
            return monitors[0]

    def capture_full_screen(self) -> Tuple[Image.Image, int, int]:
        """
        Capture the entire virtual desktop (all monitors combined).
        Returns (PIL Image in RGB format, monitor_left, monitor_top).
        """
        with self._lock:
            sct = self._get_sct()
            monitor = sct.monitors[0]
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            mon_left = monitor.get("left", 0)
            mon_top = monitor.get("top", 0)
            return img, mon_left, mon_top

    def capture_cursor_monitor(self, cursor_pos: Optional[Tuple[int, int]] = None) -> Tuple[Image.Image, int, int]:
        """
        Capture only the physical display containing the cursor position.
        Eliminates wasted pixels on inactive displays in multi-monitor setups.
        """
        if not cursor_pos:
            return self.capture_full_screen()

        with self._lock:
            sct = self._get_sct()
            # If single monitor setup or virtual display only, delegate to capture_full_screen
            if len(sct.monitors) <= 2:
                return self.capture_full_screen()

            mon = self.get_monitor_for_point(cursor_pos[0], cursor_pos[1])
            raw = sct.grab(mon)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            return img, mon.get("left", 0), mon.get("top", 0)

    def capture_active_window(
        self,
        window_rect: Tuple[int, int, int, int],
        padding: int = 24
    ) -> Tuple[Image.Image, int, int]:
        """
        Capture the active window rectangle with optional drop-shadow / context padding.
        window_rect format: (left, top, width, height)
        """
        wx, wy, ww, wh = window_rect
        if ww <= 10 or wh <= 10:
            return self.capture_full_screen()

        left = max(0, wx - padding)
        top = max(0, wy - padding)
        width = ww + 2 * padding
        height = wh + 2 * padding

        with self._lock:
            sct = self._get_sct()
            region = {"left": left, "top": top, "width": width, "height": height}
            raw = sct.grab(region)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            return img, left, top

    def capture_for_event(
        self,
        cursor_pos: Optional[Tuple[int, int]] = None,
        window_rect: Optional[Tuple[int, int, int, int]] = None,
        scope: str = "cursor_monitor",
        padding: int = 24
    ) -> Tuple[Image.Image, int, int]:
        """
        Unified capture dispatcher according to configured scope.
        Scopes: 'cursor_monitor' (default), 'active_window', 'all_monitors'.
        """
        try:
            if scope == "active_window" and window_rect and window_rect[2] > 20 and window_rect[3] > 20:
                return self.capture_active_window(window_rect, padding=padding)
            elif scope == "cursor_monitor" and cursor_pos:
                return self.capture_cursor_monitor(cursor_pos)
        except Exception:
            pass
        return self.capture_full_screen()

    def capture_primary_monitor(self) -> Image.Image:
        """Capture the primary monitor only."""
        with self._lock:
            sct = self._get_sct()
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            return img

    def capture_region(self, bbox: Tuple[int, int, int, int]) -> Image.Image:
        """Capture a specific bounding box (left, top, right, bottom)."""
        left, top, right, bottom = bbox
        width = max(1, right - left)
        height = max(1, bottom - top)
        with self._lock:
            sct = self._get_sct()
            region = {"left": left, "top": top, "width": width, "height": height}
            raw = sct.grab(region)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            return img

    @staticmethod
    def get_screen_resolution_str() -> str:
        """Returns string representation of screen resolution."""
        try:
            with mss.MSS() as sct:
                virtual_mon = sct.monitors[0]
                primary_mon = sct.monitors[1] if len(sct.monitors) > 1 else virtual_mon
                mon_count = len(sct.monitors) - 1
                if mon_count > 1:
                    return f"{virtual_mon['width']}x{virtual_mon['height']} ({mon_count} Monitors)"
                return f"{primary_mon['width']}x{primary_mon['height']}"
        except Exception:
            return "Unknown"

    @staticmethod
    def get_detailed_monitors_info() -> str:
        """Returns formatted string describing all connected displays."""
        try:
            with mss.MSS() as sct:
                lines = []
                for i, m in enumerate(sct.monitors[1:], 1):
                    primary_tag = " [Primary]" if m.get("is_primary") else ""
                    lines.append(f"Display #{i}: {m['width']}x{m['height']} at ({m['left']}, {m['top']}){primary_tag}")
                return " | ".join(lines) if lines else "Single Monitor"
        except Exception:
            return "Display Information Unavailable"

    @staticmethod
    def create_thumbnail(img: Image.Image, max_size: Tuple[int, int] = (400, 250)) -> Image.Image:
        """Create a scaled down thumbnail for preview/report efficiency."""
        thumb = img.copy()
        thumb.thumbnail(max_size, Image.Resampling.LANCZOS)
        return thumb

    @staticmethod
    def image_to_bytes(
        img: Image.Image,
        format: str = "PNG",
        quality: int = 85,
        optimize: bool = True
    ) -> bytes:
        """
        Convert PIL Image to bytes in memory.
        Supports WebP (drastically smaller file sizes), PNG, and JPEG.
        """
        buffer = io.BytesIO()
        fmt_upper = format.upper()
        if fmt_upper in ("WEBP", "IMAGE/WEBP"):
            img.save(buffer, format="WEBP", quality=quality, method=4)
        elif fmt_upper in ("JPEG", "JPG"):
            img.save(buffer, format="JPEG", quality=quality, optimize=optimize)
        else:
            img.save(buffer, format="PNG", optimize=optimize)
        return buffer.getvalue()

    @staticmethod
    def save_image_to_file(
        img: Image.Image,
        dest_path: str,
        format: str = "WEBP",
        quality: int = 85
    ) -> str:
        """Save PIL Image directly to disk file, creating parent directories if needed."""
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
        fmt_upper = format.upper()
        if fmt_upper in ("WEBP", "IMAGE/WEBP"):
            img.save(dest_path, format="WEBP", quality=quality, method=4)
        elif fmt_upper in ("JPEG", "JPG"):
            img.save(dest_path, format="JPEG", quality=quality)
        else:
            img.save(dest_path, format="PNG")
        return dest_path
