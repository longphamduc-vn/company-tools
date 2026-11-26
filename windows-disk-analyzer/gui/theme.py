"""Modern High-DPI Tkinter/TTK theme and color tokens."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font, ttk


class Theme:
    BG_DARK = "#0F172A"
    BG_DARK_SUB = "#1E293B"
    BG_LIGHT = "#F8FAFC"
    BG_CARD = "#FFFFFF"
    BORDER = "#E2E8F0"

    PRIMARY = "#0284C7"
    PRIMARY_HOVER = "#0EA5E9"
    PRIMARY_ACTIVE = "#0369A1"

    SUCCESS = "#16A34A"
    SUCCESS_BG = "#DCFCE7"
    WARNING = "#D97706"
    WARNING_BG = "#FEF3C7"
    CRITICAL = "#DC2626"
    CRITICAL_BG = "#FEE2E2"
    MUTED_BG = "#F1F5F9"

    TEXT_MAIN = "#1E293B"
    TEXT_MUTED = "#64748B"
    TEXT_LIGHT = "#F8FAFC"

    LOG_BG = "#0F172A"
    LOG_TEXT = "#E2E8F0"

    FONT_FAMILY = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"
    FONT_MONO = "Consolas" if sys.platform.startswith("win") else "Monospace"

    TREEMAP_PALETTE = [
        "#0284C7",
        "#0D9488",
        "#2563EB",
        "#7C3AED",
        "#D97706",
        "#DB2777",
        "#059669",
        "#4F46E5",
        "#EA580C",
        "#0891B2",
        "#65A30D",
        "#6366F1",
    ]

    @classmethod
    def apply(cls, root: tk.Tk) -> None:
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        try:
            dpi = root.winfo_fpixels("1i")
            if dpi > 0:
                root.tk.call("tk", "scaling", max(1.2, dpi / 72.0))
        except Exception:
            pass

        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        root.configure(bg=cls.BG_LIGHT)

        try:
            for fname in ("TkDefaultFont", "TkTextFont", "TkHeadingFont"):
                f = font.nametofont(fname)
                f.configure(family=cls.FONT_FAMILY, size=10)
        except Exception:
            pass

        style.configure("TFrame", background=cls.BG_LIGHT)
        style.configure("Card.TFrame", background=cls.BG_CARD)
        style.configure("Header.TFrame", background=cls.BG_DARK)

        style.configure(
            "HeaderTitle.TLabel",
            background=cls.BG_DARK,
            foreground=cls.TEXT_LIGHT,
            font=(cls.FONT_FAMILY, 15, "bold"),
        )
        style.configure(
            "HeaderSub.TLabel",
            background=cls.BG_DARK,
            foreground="#94A3B8",
            font=(cls.FONT_FAMILY, 9),
        )
        style.configure("TLabel", background=cls.BG_LIGHT, foreground=cls.TEXT_MAIN, font=(cls.FONT_FAMILY, 10))
        style.configure("Card.TLabel", background=cls.BG_CARD, foreground=cls.TEXT_MAIN, font=(cls.FONT_FAMILY, 10))
        style.configure("CardMuted.TLabel", background=cls.BG_CARD, foreground=cls.TEXT_MUTED, font=(cls.FONT_FAMILY, 9))
        style.configure("CardBold.TLabel", background=cls.BG_CARD, foreground=cls.TEXT_MAIN, font=(cls.FONT_FAMILY, 10, "bold"))

        style.configure("Section.TLabelframe", background=cls.BG_CARD, bordercolor=cls.BORDER, relief="solid", borderwidth=1)
        style.configure("Section.TLabelframe.Label", background=cls.BG_CARD, foreground=cls.TEXT_MAIN, font=(cls.FONT_FAMILY, 10, "bold"))

        style.configure("TNotebook", background=cls.BG_LIGHT, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 7), font=(cls.FONT_FAMILY, 10, "bold"))

        style.configure("Primary.TButton", font=(cls.FONT_FAMILY, 10, "bold"), padding=(12, 6))
        style.map(
            "Primary.TButton",
            foreground=[("!disabled", "#FFFFFF"), ("disabled", "#CBD5E1")],
            background=[("!disabled", cls.PRIMARY), ("pressed", cls.PRIMARY_ACTIVE), ("active", cls.PRIMARY_HOVER), ("disabled", "#94A3B8")],
        )

        style.configure("Danger.TButton", font=(cls.FONT_FAMILY, 10, "bold"), padding=(12, 6))
        style.map(
            "Danger.TButton",
            foreground=[("!disabled", "#FFFFFF"), ("disabled", "#CBD5E1")],
            background=[("!disabled", cls.CRITICAL), ("pressed", "#991B1B"), ("active", "#EF4444"), ("disabled", "#94A3B8")],
        )

        style.configure("Secondary.TButton", font=(cls.FONT_FAMILY, 9, "bold"), padding=(10, 5))

        style.configure("Treeview", rowheight=26, font=(cls.FONT_FAMILY, 9), background=cls.BG_CARD, fieldbackground=cls.BG_CARD)
        style.configure("Treeview.Heading", font=(cls.FONT_FAMILY, 9, "bold"), background="#E2E8F0", foreground=cls.TEXT_MAIN)
