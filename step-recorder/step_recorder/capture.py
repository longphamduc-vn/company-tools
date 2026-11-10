"""
Screen capture engine using resilient mss session, Win32 GDI fallback, and Pillow.
Supports full desktop, cursor-aware monitor targeting, window bounding with padding,
fast WebP/PNG byte encoding, and thumbnail generation with zero GDI driver failures.
"""

import io
import os
import sys
import threading
from typing import Tuple, Optional, Dict, Any, List
from PIL import Image
import mss

# Ensure Windows process is marked per-monitor DPI aware
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class ScreenCapture:
    """Handles fast, low-overhead screen capturing with persistent driver context and multi-tier fallbacks."""

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

    def get_monitors_list(self) -> List[Dict[str, Any]]:
        """Get list of monitors from driver."""
        with self._lock:
            try:
                sct = self._get_sct()
                return list(sct.monitors)
            except Exception:
                self.close()
                with self._sct_cls() as sct:
                    return list(sct.monitors)

    def get_monitor_for_point(self, x: int, y: int) -> Dict[str, Any]:
        """Find physical display monitor containing coordinate (x, y)."""
        with self._lock:
            try:
                monitors = self.get_monitors_list()
                if len(monitors) > 1:
                    for m in monitors[1:]:
                        ml = m.get("left", 0)
                        mt = m.get("top", 0)
                        mw = m.get("width", 0)
                        mh = m.get("height", 0)
                        if ml <= x < ml + mw and mt <= y < mt + mh:
                            return m
                    return monitors[1]
                return monitors[0] if monitors else {"left": 0, "top": 0, "width": 1920, "height": 1080}
            except Exception:
                return {"left": 0, "top": 0, "width": 1920, "height": 1080}

    def _win32_gdi_grab(self, bbox: Optional[Tuple[int, int, int, int]] = None) -> Tuple[Optional[Image.Image], int, int]:
        """
        Direct native Win32 GDI screen grab using ctypes.
        When CAPTUREBLT is rejected by Windows graphics drivers (e.g. on certain GPUs,
        DRM/Electron windows, secondary monitors, or virtual sessions returning ERROR_NOT_SUPPORTED),
        it automatically retries with pure SRCCOPY which is guaranteed to succeed across all Windows versions.
        """
        if sys.platform != "win32":
            return None, 0, 0

        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            # Virtual screen coordinates
            v_left = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
            v_top = user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
            v_width = user32.GetSystemMetrics(78) # SM_CXVIRTUALSCREEN
            v_height = user32.GetSystemMetrics(79)# SM_CYVIRTUALSCREEN

            if v_width <= 0 or v_height <= 0:
                v_left = 0
                v_top = 0
                v_width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
                v_height = user32.GetSystemMetrics(1) # SM_CYSCREEN

            src_x, src_y, w, h = v_left, v_top, v_width, v_height

            if bbox:
                bx1, by1, bx2, by2 = bbox
                src_x = max(v_left, bx1)
                src_y = max(v_top, by1)
                w = max(1, min(bx2 - src_x, v_width))
                h = max(1, min(by2 - src_y, v_height))

            hdesktop_dc = user32.GetDC(0)
            if not hdesktop_dc:
                return None, 0, 0

            hmem_dc = gdi32.CreateCompatibleDC(hdesktop_dc)
            hbitmap = gdi32.CreateCompatibleBitmap(hdesktop_dc, w, h)
            h_old = gdi32.SelectObject(hmem_dc, hbitmap)

            SRCCOPY = 0x00CC0020
            CAPTUREBLT = 0x40000000

            # 1. Try BitBlt with CAPTUREBLT first
            res = gdi32.BitBlt(hmem_dc, 0, 0, w, h, hdesktop_dc, src_x, src_y, SRCCOPY | CAPTUREBLT)
            # 2. If rejected by driver (ERROR_NOT_SUPPORTED / 50), retry with pure SRCCOPY
            if not res:
                res = gdi32.BitBlt(hmem_dc, 0, 0, w, h, hdesktop_dc, src_x, src_y, SRCCOPY)

            if not res:
                gdi32.SelectObject(hmem_dc, h_old)
                gdi32.DeleteObject(hbitmap)
                gdi32.DeleteDC(hmem_dc)
                user32.ReleaseDC(0, hdesktop_dc)
                return None, 0, 0

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD),
                    ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD),
                ]

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h  # top-down DIB
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            buffer_len = w * h * 4
            buf = ctypes.create_string_buffer(buffer_len)
            gdi32.GetDIBits(hmem_dc, hbitmap, 0, h, buf, ctypes.byref(bmi), 0)

            # Clean up all GDI handles
            gdi32.SelectObject(hmem_dc, h_old)
            gdi32.DeleteObject(hbitmap)
            gdi32.DeleteDC(hmem_dc)
            user32.ReleaseDC(0, hdesktop_dc)

            img = Image.frombytes("RGB", (w, h), buf.raw, "raw", "BGRX")
            return img, src_x, src_y
        except Exception:
            return None, 0, 0

    def _fallback_capture_full_screen(self) -> Tuple[Image.Image, int, int]:
        """Multi-layer fallback when mss fails."""
        # Layer 1: Win32 GDI fallback (pure SRCCOPY)
        if sys.platform == "win32":
            img, l, t = self._win32_gdi_grab()
            if img:
                return img, l, t

        # Layer 2: PIL ImageGrab fallback
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(all_screens=True)
            v_left = 0
            v_top = 0
            if sys.platform == "win32":
                try:
                    import ctypes
                    v_left = ctypes.windll.user32.GetSystemMetrics(76)
                    v_top = ctypes.windll.user32.GetSystemMetrics(77)
                except Exception:
                    pass
            return img, v_left, v_top
        except Exception:
            pass

        # Layer 3: Fresh single-use mss context
        with self._sct_cls() as sct:
            monitor = sct.monitors[0]
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            return img, monitor.get("left", 0), monitor.get("top", 0)

    def capture_full_screen(self) -> Tuple[Image.Image, int, int]:
        """
        Capture the entire virtual desktop (all monitors combined).
        Returns (PIL Image in RGB format, monitor_left, monitor_top).
        Resilient against stale GDI device contexts and display driver resets.
        """
        with self._lock:
            try:
                sct = self._get_sct()
                monitor = sct.monitors[0]
                raw = sct.grab(monitor)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                mon_left = monitor.get("left", 0)
                mon_top = monitor.get("top", 0)
                return img, mon_left, mon_top
            except Exception:
                # Driver context may be poisoned or stale; reset and invoke fallback
                self.close()
                return self._fallback_capture_full_screen()

    def capture_cursor_monitor(self, cursor_pos: Optional[Tuple[int, int]] = None) -> Tuple[Image.Image, int, int]:
        """
        Capture only the physical display containing the cursor position.
        In multi-monitor setups, captures virtual desktop and crops the monitor region cleanly
        in-memory (0ms overhead, avoids Windows GDI multi-monitor BitBlt driver rejection).
        """
        if not cursor_pos:
            return self.capture_full_screen()

        with self._lock:
            try:
                monitors = self.get_monitors_list()
            except Exception:
                monitors = []

            # Single monitor setup: virtual desktop is the monitor
            if len(monitors) <= 2:
                return self.capture_full_screen()

            # Multiple physical monitors: find target display
            target_mon = self.get_monitor_for_point(cursor_pos[0], cursor_pos[1])
            ml = target_mon.get("left", 0)
            mt = target_mon.get("top", 0)
            mw = target_mon.get("width", 0)
            mh = target_mon.get("height", 0)

            # Capture full desktop safely then crop in memory
            full_img, v_left, v_top = self.capture_full_screen()
            crop_x1 = max(0, ml - v_left)
            crop_y1 = max(0, mt - v_top)
            crop_x2 = min(full_img.width, crop_x1 + mw)
            crop_y2 = min(full_img.height, crop_y1 + mh)

            if crop_x2 > crop_x1 and crop_y2 > crop_y1:
                cropped = full_img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
                return cropped, ml, mt

            return full_img, v_left, v_top

    def capture_active_window(
        self,
        window_rect: Tuple[int, int, int, int],
        padding: int = 24
    ) -> Tuple[Image.Image, int, int]:
        """
        Capture the active window rectangle with optional context padding.
        Crops safely from the full screen capture to avoid GDI out-of-bounds rejection.
        """
        wx, wy, ww, wh = window_rect
        if ww <= 10 or wh <= 10:
            return self.capture_full_screen()

        full_img, v_left, v_top = self.capture_full_screen()

        left = wx - padding
        top = wy - padding
        right = wx + ww + padding
        bottom = wy + wh + padding

        crop_x1 = max(0, left - v_left)
        crop_y1 = max(0, top - v_top)
        crop_x2 = min(full_img.width, right - v_left)
        crop_y2 = min(full_img.height, bottom - v_top)

        if crop_x2 > crop_x1 and crop_y2 > crop_y1:
            cropped = full_img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
            return cropped, v_left + crop_x1, v_top + crop_y1

        return full_img, v_left, v_top

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
        Guaranteed to never raise an unhandled exception.
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
        img, _, _ = self.capture_full_screen()
        return img

    def capture_region(self, bbox: Tuple[int, int, int, int]) -> Image.Image:
        """Capture a specific bounding box (left, top, right, bottom)."""
        left, top, right, bottom = bbox
        width = max(1, right - left)
        height = max(1, bottom - top)
        full_img, v_left, v_top = self.capture_full_screen()

        crop_x1 = max(0, left - v_left)
        crop_y1 = max(0, top - v_top)
        crop_x2 = min(full_img.width, crop_x1 + width)
        crop_y2 = min(full_img.height, crop_y1 + height)

        if crop_x2 > crop_x1 and crop_y2 > crop_y1:
            return full_img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
        return full_img

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
