"""Single place for the application's ttk theme, palette and named styles."""
import tkinter as tk
from tkinter import ttk

# Palette
BG = "#ffffff"           # window & panel background
SURFACE = "#f8fafc"      # subtle panels (headers, strips)
BORDER = "#e2e8f0"
TEXT = "#0f172a"
TEXT_MUTED = "#64748b"
ACCENT = "#0284c7"
ACCENT_ACTIVE = "#0369a1"
WARN = "#ea580c"
WARN_ACTIVE = "#c2410c"
DANGER = "#b91c1c"
OK = "#16a34a"
BANNER_BG = "#fee2e2"
BANNER_BORDER = "#fca5a5"
BANNER_FG = "#991b1b"


def apply_styles(root: tk.Misc) -> ttk.Style:
    """Configure the clam theme with one palette and all named button styles.

    Must be called before widgets are created so the option database defaults
    apply to plain tk widgets too.
    """
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    # Plain tk widgets created without an explicit bg follow the same palette.
    for cls in ("Frame", "Label", "Toplevel", "LabelFrame", "Canvas", "Checkbutton"):
        root.option_add(f"*{cls}.background", BG)
    root.option_add("*Label.foreground", TEXT)
    try:
        root.configure(bg=BG)
    except tk.TclError:
        pass

    style.configure(".", background=BG, foreground=TEXT)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("TLabelframe", background=BG, bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=BG, foreground=TEXT_MUTED)
    style.configure("TCheckbutton", background=BG)
    style.configure("TRadiobutton", background=BG)
    style.configure("TPanedwindow", background=BG)
    style.configure("Treeview", background=BG, fieldbackground=BG, bordercolor=BORDER)
    style.configure("Treeview.Heading", background=SURFACE, bordercolor=BORDER)

    style.configure("TNotebook", background=BG, bordercolor=BORDER, tabmargins=(4, 2, 4, 0))
    style.configure("TNotebook.Tab", background=SURFACE, bordercolor=BORDER, padding=(14, 3))
    style.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", ACCENT)])

    style.configure("TButton", background=SURFACE, bordercolor="#cbd5e1", padding=(8, 2))
    style.map("TButton", background=[("active", BORDER), ("disabled", BG)])

    style.configure("Accent.TButton", font=("", 9, "bold"))
    for name, bg, active in (
        ("SyncPending.TButton", ACCENT, ACCENT_ACTIVE),
        ("DirtySave.TButton", WARN, WARN_ACTIVE),
    ):
        style.configure(name, font=("", 9, "bold"), background=bg, foreground="#ffffff")
        style.map(name, background=[("active", active)], foreground=[("active", "#ffffff")])
    style.configure("Danger.TButton", foreground=DANGER)
    style.map("Danger.TButton", foreground=[("disabled", TEXT_MUTED)])

    # Segmented filter buttons (ttk.Radiobutton with the Toolbutton layout)
    style.configure("Filter.Toolbutton", background=SURFACE, padding=(8, 1), font=("", 8, "bold"))
    style.map(
        "Filter.Toolbutton",
        background=[("selected", ACCENT), ("active", BORDER)],
        foreground=[("selected", "#ffffff")],
    )

    style.configure("Header.TLabel", font=("", 11, "bold"))
    style.configure("Banner.TFrame", background=BANNER_BG)
    style.configure("Banner.TLabel", background=BANNER_BG, foreground=BANNER_FG, font=("", 9, "bold"))
    style.configure("Banner.TButton", padding=(6, 0))
    return style
