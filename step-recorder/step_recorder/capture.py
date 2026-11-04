"""
Screen capture engine using mss and Pillow.
Supports full desktop, specific monitor, and thumbnail generation.
"""

import io
from typing import Tuple, Optional
from PIL import Image
import mss


class ScreenCapture:
    """Handles fast, low-overhead screen capturing."""

    def __init__(self):
        # Compatible with both modern mss.MSS and legacy mss.mss
        if hasattr(mss, "MSS"):
            self._sct_cls = mss.MSS
        else:
            self._sct_cls = mss.mss

    def capture_full_screen(self) -> Tuple[Image.Image, int, int]:
        """
        Capture the entire virtual desktop (all monitors combined).
        Returns (PIL Image in RGB format, monitor_left, monitor_top).
        """
        with self._sct_cls() as sct:
            # Monitor 0 in mss is always the virtual bounding box of all monitors
            monitor = sct.monitors[0]
            raw = sct.grab(monitor)
            # Convert mss screenshot (BGRA) to PIL Image (RGB)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            mon_left = monitor.get("left", 0)
            mon_top = monitor.get("top", 0)
            return img, mon_left, mon_top

    def capture_primary_monitor(self) -> Image.Image:
        """
        Capture the primary monitor only.
        """
        with self._sct_cls() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            return img

    def capture_region(self, bbox: Tuple[int, int, int, int]) -> Image.Image:
        """
        Capture a specific bounding box (left, top, right, bottom).
        """
        left, top, right, bottom = bbox
        width = max(1, right - left)
        height = max(1, bottom - top)
        with self._sct_cls() as sct:
            region = {"left": left, "top": top, "width": width, "height": height}
            raw = sct.grab(region)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            return img

    @staticmethod
    def get_screen_resolution_str() -> str:
        """Returns string representation of screen resolution, e.g. '3840x2400 (Virtual: 3840x2400)'."""
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
    def image_to_bytes(img: Image.Image, format: str = "PNG", optimize: bool = True) -> bytes:
        """Convert PIL Image to bytes in memory."""
        buffer = io.BytesIO()
        if format.upper() == "JPEG" or format.upper() == "JPG":
            img.save(buffer, format="JPEG", quality=85, optimize=optimize)
        else:
            img.save(buffer, format="PNG", optimize=optimize)
        return buffer.getvalue()
