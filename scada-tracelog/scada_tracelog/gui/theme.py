# -*- coding: utf-8 -*-
import sys
from tkinter import ttk, font
import tkinter as tk

class Theme:
    # Modern Enterprise Color Palette
    BG_DARK = "#0F172A"       # Header background
    BG_LIGHT = "#F8FAFC"      # Window body background
    BG_CARD = "#FFFFFF"       # Section background
    BORDER = "#E2E8F0"        # Card borders
    
    PRIMARY = "#0284C7"       # Action button
    PRIMARY_HOVER = "#0EA5E9"
    PRIMARY_ACTIVE = "#0369A1"
    
    TEXT_MAIN = "#1E293B"
    TEXT_MUTED = "#64748B"
    TEXT_LIGHT = "#F8FAFC"
    
    # Log tag colors
    LOG_BG = "#0F172A"
    LOG_TEXT = "#E2E8F0"
    COLOR_INFO = "#38BDF8"
    COLOR_SUCCESS = "#4ADE80"
    COLOR_WARNING = "#FBBF24"
    COLOR_ERROR = "#F87171"
    COLOR_TIME = "#94A3B8"

    # Font configurations (To, rõ ràng, dễ đọc trên cả Windows và WSL)
    FONT_FAMILY = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"
    FONT_MONO = "Consolas" if sys.platform.startswith("win") else "Monospace"

    @classmethod
    def apply(cls, root: tk.Tk):
        # 1. Kích hoạt High-DPI trên Windows nếu có
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        # 2. Điều chỉnh hệ số tỷ lệ Tkinter scaling dựa trên DPI thực tế
        try:
            dpi = root.winfo_fpixels('1i')
            if dpi > 0:
                # Đảm bảo hệ số scaling luôn tối thiểu 1.25 để chữ không bị nhỏ
                target_scaling = max(1.25, dpi / 72.0)
                root.tk.call('tk', 'scaling', target_scaling)
        except Exception:
            pass
            
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
            
        root.configure(bg=cls.BG_LIGHT)
        
        # Cấu hình font hệ thống mặc định của Tkinter
        try:
            default_font = font.nametofont("TkDefaultFont")
            default_font.configure(family=cls.FONT_FAMILY, size=11)
            
            text_font = font.nametofont("TkTextFont")
            text_font.configure(family=cls.FONT_FAMILY, size=11)
        except Exception:
            pass
        
        # TTK Widget Styles
        style.configure("TFrame", background=cls.BG_LIGHT)
        style.configure("Header.TLabel", background=cls.BG_DARK, foreground=cls.TEXT_LIGHT, font=(cls.FONT_FAMILY, 16, "bold"))
        style.configure("SubHeader.TLabel", background=cls.BG_DARK, foreground=cls.TEXT_MUTED, font=(cls.FONT_FAMILY, 10))
        
        style.configure("Section.TLabelframe", background=cls.BG_CARD, relief="solid", borderwidth=1)
        style.configure("Section.TLabelframe.Label", background=cls.BG_CARD, foreground=cls.TEXT_MAIN, font=(cls.FONT_FAMILY, 11, "bold"))
        
        style.configure("TLabel", background=cls.BG_CARD, foreground=cls.TEXT_MAIN, font=(cls.FONT_FAMILY, 11))
        style.configure("TRadiobutton", background=cls.BG_CARD, foreground=cls.TEXT_MAIN, font=(cls.FONT_FAMILY, 11))
        style.configure("TCheckbutton", background=cls.BG_CARD, foreground=cls.TEXT_MAIN, font=(cls.FONT_FAMILY, 11))
        
        # Nút START CONVERSION lớn, nổi bật
        style.configure("Primary.TButton", font=(cls.FONT_FAMILY, 11, "bold"), padding=8)
        style.map("Primary.TButton",
                  foreground=[("!disabled", "#FFFFFF")],
                  background=[("!disabled", cls.PRIMARY), ("pressed", cls.PRIMARY_ACTIVE), ("active", cls.PRIMARY_HOVER)])
                  
        style.configure("Secondary.TButton", font=(cls.FONT_FAMILY, 10, "bold"), padding=6)
