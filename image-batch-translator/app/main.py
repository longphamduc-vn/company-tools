#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Bootstrap & Main Entry Point.
"""

import sys
import tkinter as tk
from tkinter import messagebox

from .config import HAVE_LENS, HAVE_RAPIDOCR, MISSING_PACKAGES
from .ui.main_window import SmartBatchExtractorApp


def main():
    """Main application startup with dependency validation."""
    if not HAVE_LENS and not HAVE_RAPIDOCR:
        error_msg = (
            f"Thiếu các thư viện Python cần thiết: {', '.join(MISSING_PACKAGES)}\n\n"
            f"Vui lòng cài đặt bằng lệnh:\n"
            f"    pip install -r requirements.txt\n"
            f"hoặc:\n"
            f"    pip install pillow chrome-lens-py rapidocr-onnxruntime opencv-python deep-translator\n"
        )
        print(error_msg, file=sys.stderr)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Thiếu Thư Viện", error_msg)
            root.destroy()
        except Exception:
            pass
        sys.exit(1)

    root = tk.Tk()
    app = SmartBatchExtractorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
