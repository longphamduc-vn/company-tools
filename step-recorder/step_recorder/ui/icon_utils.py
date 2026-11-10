"""
Icon utilities for Python Step Recorder.
Handles multi-platform window icon loading, Windows AppUserModelID registration,
and HTML report favicon embedding.
"""

import sys
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageTk


ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
ICON_ICO_PATH = ASSETS_DIR / "icon.ico"
ICON_PNG_PATH = ASSETS_DIR / "icon.png"
ICON_32_PATH = ASSETS_DIR / "icon_32.png"

_app_user_model_id_set = False


def setup_windows_app_id() -> None:
    """Set explicit AppUserModelID on Windows so taskbar uses custom app icon."""
    global _app_user_model_id_set
    if _app_user_model_id_set:
        return
    if sys.platform == "win32":
        try:
            import ctypes
            app_id = "company.steprecorder.steprecordingtool.1.0"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
            _app_user_model_id_set = True
        except Exception:
            pass


def apply_window_icon(window: tk.Misc) -> None:
    """
    Apply app icon to a Tkinter window or Toplevel dialog.
    Supports Windows (.ico), Linux (.png via iconphoto), and macOS.
    """
    setup_windows_app_id()

    # 1. On Windows, try setting iconbitmap
    if sys.platform == "win32" and ICON_ICO_PATH.exists():
        try:
            window.iconbitmap(str(ICON_ICO_PATH))
        except Exception:
            pass

    # 2. Universal iconphoto across Windows, Linux X11, and macOS
    target_png = ICON_PNG_PATH if ICON_PNG_PATH.exists() else ICON_32_PATH
    if target_png.exists():
        try:
            pil_img = Image.open(str(target_png))
            photo = ImageTk.PhotoImage(pil_img)
            # iconphoto(True, ...) sets the default icon for this and future toplevels
            window.iconphoto(True, photo)
            # Retain a reference to prevent garbage collection
            setattr(window, "_app_icon_photo_ref", photo)
        except Exception:
            pass


def get_favicon_base64() -> str:
    """Return base64 string of 32x32 icon for HTML reports."""
    target_png = ICON_32_PATH if ICON_32_PATH.exists() else ICON_PNG_PATH
    if target_png.exists():
        try:
            import base64
            with open(target_png, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
        except Exception:
            pass
    return ""

