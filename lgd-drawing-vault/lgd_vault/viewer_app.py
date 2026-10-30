"""
LGD Drawing Vault - Batch Blueprint Downloader & Interactive Image Viewer.
Features:
- Excel-like Input Grid with seamless copy & paste from Microsoft Excel / Google Sheets.
- Dual View Modes: High-resolution Interactive Canvas & Visual Thumbnail Card Gallery.
- Bottom Thumbnail Filmstrip for fast switching between drawings.
- Advanced Zoom, Pan, Fit, and Keyboard Shortcuts.
"""

import csv
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from lgd_vault.config import DEFAULT_DOWNLOAD_DIR, DEFAULT_SITE, DEFAULT_FAB
from lgd_vault.models import DrawingItem, DownloadResult, BatchDownloadSummary
from lgd_vault.session_manager import SessionManager
from lgd_vault.drawing_service import DrawingService
from lgd_vault.sso_client import SSOClient
from lgd_vault.excel_grid import ExcelInputGrid
from lgd_vault.image_gallery import ThumbnailGalleryView

logger = logging.getLogger("lgd_vault.viewer")


class DrawingViewerApp(tk.Tk):
    """Batch Image Viewer & Blueprint Downloader with Excel-like Grid."""

    def __init__(self):
        super().__init__()
        self.title("LGD Drawing Vault - Batch Blueprint Downloader & Viewer")
        self.geometry("1440x900")
        self.minsize(1100, 720)

        # Services
        self.session_manager = SessionManager()
        self.sso_client = SSOClient(session_manager=self.session_manager)
        self.drawing_service = DrawingService(sso_client=self.sso_client)

        # State
        self.download_dir = tk.StringVar(value=DEFAULT_DOWNLOAD_DIR)
        self.items_gallery: List[DownloadResult] = []
        self.current_index: int = -1
        self.current_image_path: Optional[str] = None
        self.raw_pil_image: Optional[Image.Image] = None
        self.tk_image_cache: Optional[ImageTk.PhotoImage] = None
        self.filmstrip_cache: Dict[str, ImageTk.PhotoImage] = {}

        # Viewport zoom & pan
        self.zoom_level: float = 1.0
        self.pan_start_x: int = 0
        self.pan_start_y: int = 0
        self.img_pos_x: int = 0
        self.img_pos_y: int = 0

        # View mode: "canvas" (single image viewer) or "gallery" (thumbnail card grid)
        self.view_mode = tk.StringVar(value="canvas")

        # Batch download control
        self.is_downloading: bool = False
        self.cancel_requested: bool = False

        self._configure_styles()
        self._build_ui()
        self._bind_keyboard_shortcuts()
        self._check_sso_status_async()
        self._load_existing_downloads()

    def _configure_styles(self):
        """Clean modern visual style."""
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        self.bg_main = "#f4f6f9"
        self.sidebar_bg = "#ffffff"
        self.canvas_bg = "#1e1e24"
        self.accent_color = "#0052cc"
        self.text_color = "#172b4d"

        self.configure(bg=self.bg_main)
        self.style.configure(".", background=self.bg_main, foreground=self.text_color, font=("Segoe UI", 9))
        self.style.configure("TFrame", background=self.bg_main)
        self.style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"), background=self.accent_color, foreground="white")
        self.style.configure("Danger.TButton", font=("Segoe UI", 9, "bold"), background="#de350b", foreground="white")
        self.style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), foreground="#0b2147")
        self.style.configure("Card.TFrame", background="#ffffff")
        self.style.configure("ActiveCard.TFrame", background="#e9f2ff", relief="solid", bordercolor="#0052cc")

    def _build_ui(self):
        # 1. TOP HEADER & SSO STATUS BAR
        top_bar = ttk.Frame(self, padding=(12, 6))
        top_bar.pack(fill=tk.X, side=tk.TOP)

        title_lbl = ttk.Label(
            top_bar,
            text="📐 LGD Drawing Vault | Batch Blueprint Viewer",
            font=("Segoe UI", 13, "bold"),
            foreground="#0b2147",
        )
        title_lbl.pack(side=tk.LEFT, padx=4)

        # SSO Status Indicator
        self.sso_status_lbl = ttk.Label(
            top_bar,
            text="🔄 Checking SSO Agent (Port 28083)...",
            font=("Segoe UI", 9, "italic"),
            foreground="#5e6c84",
        )
        self.sso_status_lbl.pack(side=tk.LEFT, padx=16)

        btn_refresh_sso = ttk.Button(top_bar, text="Check SSO", width=11, command=self._refresh_sso_session)
        btn_refresh_sso.pack(side=tk.LEFT, padx=4)

        # Target download folder chooser
        dir_frame = ttk.Frame(top_bar)
        dir_frame.pack(side=tk.RIGHT, padx=4)
        ttk.Label(dir_frame, text="Download Folder:").pack(side=tk.LEFT, padx=4)
        dir_entry = ttk.Entry(dir_frame, textvariable=self.download_dir, width=28)
        dir_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(dir_frame, text="Browse...", width=9, command=self._browse_download_dir).pack(side=tk.LEFT)

        # 2. MAIN SPLIT LAYOUT (Left: Excel Input Grid | Right: Image Viewer)
        self.main_paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        # LEFT PANE: EXCEL INPUT GRID & BATCH DOWNLOAD CONTROLLER
        left_panel = ttk.Frame(self.main_paned, width=480, padding=4)
        self.main_paned.add(left_panel, weight=1)

        # Header of Left Pane
        left_header = ttk.Frame(left_panel)
        left_header.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(
            left_header,
            text="📊 Input Queue (Excel Grid)",
            font=("Segoe UI", 11, "bold"),
            foreground="#0b2147",
        ).pack(side=tk.LEFT)

        # The Excel-like Input Grid
        self.excel_grid = ExcelInputGrid(left_panel, padding=2)
        self.excel_grid.pack(fill=tk.BOTH, expand=True)

        # Batch Download Action Box
        batch_ctrl_frame = ttk.LabelFrame(left_panel, text="Batch Download Progress", padding=8)
        batch_ctrl_frame.pack(fill=tk.X, pady=(8, 0))

        btn_action_row = ttk.Frame(batch_ctrl_frame)
        btn_action_row.pack(fill=tk.X, pady=(0, 4))

        self.btn_batch_start = ttk.Button(
            btn_action_row,
            text="📥 Download All Items",
            style="Accent.TButton",
            command=self._start_batch_download,
        )
        self.btn_batch_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.btn_batch_stop = ttk.Button(
            btn_action_row,
            text="⏹ Stop",
            style="Danger.TButton",
            width=7,
            state="disabled",
            command=self._stop_batch_download,
        )
        self.btn_batch_stop.pack(side=tk.RIGHT)

        self.progress_bar = ttk.Progressbar(batch_ctrl_frame, orient=tk.HORIZONTAL, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(4, 2))

        self.lbl_batch_progress = ttk.Label(batch_ctrl_frame, text="Ready.", font=("Segoe UI", 9), foreground="#0052cc")
        self.lbl_batch_progress.pack(anchor="w")

        # RIGHT PANE: IMAGE VIEWER & THUMBNAIL GALLERY
        right_panel = ttk.Frame(self.main_paned, padding=4)
        self.main_paned.add(right_panel, weight=3)

        # 1. Top Viewer Toolbar (View Mode Switcher + Navigation + Zoom + External Actions)
        viewer_toolbar = ttk.Frame(right_panel, padding=(4, 4))
        viewer_toolbar.pack(fill=tk.X, side=tk.TOP)

        # View Mode Selector: Canvas vs Thumbnail Grid
        mode_frame = ttk.Frame(viewer_toolbar)
        mode_frame.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Radiobutton(
            mode_frame,
            text="🖼️ Blueprint Detail",
            value="canvas",
            variable=self.view_mode,
            command=self._switch_view_mode,
        ).pack(side=tk.LEFT, padx=3)

        ttk.Radiobutton(
            mode_frame,
            text="📑 Thumbnail Gallery",
            value="gallery",
            variable=self.view_mode,
            command=self._switch_view_mode,
        ).pack(side=tk.LEFT, padx=3)

        ttk.Separator(viewer_toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        # Batch Navigation (Previous / Next)
        self.nav_frame = ttk.Frame(viewer_toolbar)
        self.nav_frame.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(self.nav_frame, text="⏮ First", width=6, command=self._go_first_image).pack(side=tk.LEFT, padx=1)
        ttk.Button(self.nav_frame, text="◀ Prev", width=7, command=self._go_prev_image).pack(side=tk.LEFT, padx=1)
        self.lbl_batch_counter = ttk.Label(self.nav_frame, text="[ 0 / 0 ]", font=("Segoe UI", 10, "bold"), width=9, anchor="center")
        self.lbl_batch_counter.pack(side=tk.LEFT, padx=3)
        ttk.Button(self.nav_frame, text="Next ▶", width=7, command=self._go_next_image).pack(side=tk.LEFT, padx=1)
        ttk.Button(self.nav_frame, text="Last ⏭", width=6, command=self._go_last_image).pack(side=tk.LEFT, padx=1)

        ttk.Separator(viewer_toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        # Zoom Controls
        self.zoom_frame = ttk.Frame(viewer_toolbar)
        self.zoom_frame.pack(side=tk.LEFT)

        ttk.Button(self.zoom_frame, text="🔍 +", width=4, command=self._zoom_in).pack(side=tk.LEFT, padx=1)
        ttk.Button(self.zoom_frame, text="🔍 -", width=4, command=self._zoom_out).pack(side=tk.LEFT, padx=1)
        ttk.Button(self.zoom_frame, text="100%", width=5, command=self._zoom_100).pack(side=tk.LEFT, padx=1)
        ttk.Button(self.zoom_frame, text="📐 Fit", width=6, command=self._fit_to_screen).pack(side=tk.LEFT, padx=1)
        ttk.Button(self.zoom_frame, text="↔ Fit Width", width=9, command=self._fit_width).pack(side=tk.LEFT, padx=1)

        self.lbl_zoom = ttk.Label(self.zoom_frame, text="100%", font=("Segoe UI", 9, "bold"), width=6, anchor="center")
        self.lbl_zoom.pack(side=tk.LEFT, padx=2)

        # External Actions
        action_frame = ttk.Frame(viewer_toolbar)
        action_frame.pack(side=tk.RIGHT)
        ttk.Button(action_frame, text="Export CSV", command=self._export_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Open File", command=self._open_in_external_app).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Open Folder", command=self._open_download_folder).pack(side=tk.LEFT, padx=2)

        # 2. Viewport Stack Container
        self.viewport_container = ttk.Frame(right_panel)
        self.viewport_container.pack(fill=tk.BOTH, expand=True)

        # Canvas Subframe (for single image inspection)
        self.canvas_subframe = ttk.Frame(self.viewport_container)

        self.canvas = tk.Canvas(self.canvas_subframe, bg=self.canvas_bg, cursor="fleur", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Filmstrip Frame at bottom of Canvas
        self.filmstrip_container = ttk.Frame(self.canvas_subframe, height=90, padding=(4, 2))
        self.filmstrip_container.pack(fill=tk.X, side=tk.BOTTOM)

        # Filmstrip Canvas with Horizontal Scrollbar
        self.filmstrip_canvas = tk.Canvas(self.filmstrip_container, height=85, bg="#2d3139", highlightthickness=0)
        self.filmstrip_canvas.pack(fill=tk.BOTH, expand=True)

        # Thumbnail Gallery View (for the visual grid mode)
        self.gallery_view = ThumbnailGalleryView(
            self.viewport_container,
            on_open_image=self._open_image_from_gallery,
        )

        # Initially show canvas view
        self.canvas_subframe.pack(fill=tk.BOTH, expand=True)

        # Canvas Mouse Bindings for Pan & Zoom
        self.canvas.bind("<ButtonPress-1>", self._on_pan_start)
        self.canvas.bind("<B1-Motion>", self._on_pan_move)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)  # Windows / macOS
        self.canvas.bind("<Button-4>", lambda e: self._zoom_delta(1.15, e.x, e.y))  # Linux scroll up
        self.canvas.bind("<Button-5>", lambda e: self._zoom_delta(0.85, e.x, e.y))  # Linux scroll down
        self.canvas.bind("<Configure>", lambda e: self._on_canvas_resize())

        # 3. Bottom Metadata & Shortcut Help Bar
        bottom_bar = ttk.Frame(right_panel, padding=(6, 4))
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_meta = ttk.Label(
            bottom_bar,
            text="Ready. Enter or paste QCode list from Excel to view batch drawings.",
            font=("Segoe UI", 9),
            foreground="#2d3748",
        )
        self.lbl_meta.pack(side=tk.LEFT, fill=tk.X, expand=True)

        lbl_shortcuts = ttk.Label(
            bottom_bar,
            text="Shortcuts: ◀ / ▶ (Switch Image) | Mouse Wheel (Zoom) | Drag (Pan) | F (Fit) | 0 (100%)",
            font=("Segoe UI", 8),
            foreground="#718096",
        )
        lbl_shortcuts.pack(side=tk.RIGHT)

    def _bind_keyboard_shortcuts(self):
        """Keyboard shortcuts for efficient batch viewing."""
        self.bind("<Left>", lambda e: self._go_prev_image())
        self.bind("<Right>", lambda e: self._go_next_image())
        self.bind("<Home>", lambda e: self._go_first_image())
        self.bind("<End>", lambda e: self._go_last_image())
        self.bind("<plus>", lambda e: self._zoom_in())
        self.bind("<equal>", lambda e: self._zoom_in())
        self.bind("<minus>", lambda e: self._zoom_out())
        self.bind("<f>", lambda e: self._fit_to_screen())
        self.bind("<F>", lambda e: self._fit_to_screen())
        self.bind("<0>", lambda e: self._zoom_100())

    # ------------------ View Mode Toggle ------------------

    def _switch_view_mode(self):
        """Switches between Canvas View and Thumbnail Grid View."""
        mode = self.view_mode.get()
        if mode == "canvas":
            self.gallery_view.pack_forget()
            self.canvas_subframe.pack(fill=tk.BOTH, expand=True)
            self.nav_frame.pack(side=tk.LEFT, padx=(0, 8))
            self.zoom_frame.pack(side=tk.LEFT)
            if self.current_index >= 0:
                self.show_image_at_index(self.current_index)
        else:
            self.canvas_subframe.pack_forget()
            self.gallery_view.pack(fill=tk.BOTH, expand=True)
            self.gallery_view.set_items(self.items_gallery)
            if self.current_index >= 0 and self.current_index < len(self.items_gallery):
                self.gallery_view.select_item(self.items_gallery[self.current_index])

    def _open_image_from_gallery(self, result: DownloadResult):
        """Triggered when an image card in gallery view is double-clicked / selected."""
        for idx, item in enumerate(self.items_gallery):
            if item.qcode == result.qcode and item.local_path == result.local_path:
                self.current_index = idx
                break
        self.view_mode.set("canvas")
        self._switch_view_mode()

    # ------------------ SSO & File Operations ------------------

    def _check_sso_status_async(self):
        def run():
            valid = self.session_manager.is_session_valid()
            info = self.session_manager.get_session_info()
            if valid:
                rem = info.get("remaining_seconds", 0)
                mins = rem // 60
                self.after(0, lambda: self.sso_status_lbl.configure(
                    text=f"🟢 SSO Session Active ({mins}m left)",
                    foreground="#00875a",
                ))
            else:
                self.after(0, lambda: self.sso_status_lbl.configure(
                    text="🟡 SSO Ready (Will connect ws://127.0.0.1:28083)",
                    foreground="#ff8b00",
                ))
        threading.Thread(target=run, daemon=True).start()

    def _refresh_sso_session(self):
        self.sso_status_lbl.configure(text="🔄 Connecting to port 28083...", foreground="#0052cc")

        def run():
            try:
                cookies = self.sso_client.authenticate()
                self.after(0, lambda: [
                    self.sso_status_lbl.configure(text="🟢 SSO Authenticated Successfully", foreground="#00875a"),
                    messagebox.showinfo("SSO Success", f"Connected and saved LG Display SSO session!\nCookies: {list(cookies.keys())}"),
                ])
            except Exception as e:
                self.after(0, lambda: [
                    self.sso_status_lbl.configure(text="🔴 SSO Offline / Refused", foreground="#de350b"),
                    messagebox.showerror(
                        "SSO Connection Error",
                        f"Cannot connect to SSO Agent:\n{e}\n\nPlease ensure LG Display SSO Agent is running on port 28083.",
                    ),
                ])
        threading.Thread(target=run, daemon=True).start()

    def _browse_download_dir(self):
        selected = filedialog.askdirectory(initialdir=self.download_dir.get(), title="Select Blueprint Download Directory")
        if selected:
            self.download_dir.set(selected)
            self._load_existing_downloads()

    def _load_existing_downloads(self):
        """Scans the download directory for previously downloaded drawings."""
        target_dir = self.download_dir.get()
        if not os.path.isdir(target_dir):
            return

        valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
        found_files = []
        for f in sorted(os.listdir(target_dir)):
            full = os.path.join(target_dir, f)
            if os.path.isfile(full) and os.path.splitext(f)[1].lower() in valid_exts:
                found_files.append(full)

        if found_files:
            for path in found_files:
                fname = os.path.basename(path)
                parts = fname.split("_")
                qcode = parts[0] if len(parts) > 0 and parts[0].startswith("QC") else "FILE"
                alias = parts[1] if len(parts) > 2 else ""

                w, h = 0, 0
                if HAS_PIL:
                    try:
                        with Image.open(path) as im:
                            w, h = im.size
                    except Exception:
                        pass

                res = DownloadResult(
                    qcode=qcode,
                    custom_name=alias,
                    status="Success",
                    file_name=fname,
                    local_path=path,
                    file_size_bytes=os.path.getsize(path),
                    image_width=w,
                    image_height=h,
                )
                self.items_gallery.append(res)

            self._update_counter_label()
            self.gallery_view.set_items(self.items_gallery)
            self._render_filmstrip()
            if self.items_gallery:
                self.show_image_at_index(0)

    # ------------------ Batch Downloading Logic ------------------

    def _start_batch_download(self):
        items = self.excel_grid.get_items()
        if not items:
            messagebox.showwarning("Empty Grid", "Please enter or paste at least 1 QCode into the Excel grid.")
            return

        self.is_downloading = True
        self.cancel_requested = False
        self.btn_batch_start.configure(state="disabled")
        self.btn_batch_stop.configure(state="normal")
        self.progress_bar["maximum"] = len(items)
        self.progress_bar["value"] = 0

        def run():
            target_dir = self.download_dir.get()

            def on_progress(current, total, result):
                self.after(0, lambda: self._update_batch_progress(current, total, result))

            def check_cancelled():
                return self.cancel_requested

            summary = self.drawing_service.execute_batch(
                items=items,
                download_dir=target_dir,
                progress_callback=on_progress,
                cancel_check=check_cancelled,
            )

            self.after(0, lambda: self._on_batch_complete(summary))

        threading.Thread(target=run, daemon=True).start()

    def _stop_batch_download(self):
        if self.is_downloading:
            self.cancel_requested = True
            self.lbl_batch_progress.configure(text="Stopping batch download...")

    def _update_batch_progress(self, current: int, total: int, result: DownloadResult):
        self.progress_bar["value"] = current
        pct = int((current / total) * 100)
        self.lbl_batch_progress.configure(
            text=f"Downloading {current}/{total} ({pct}%) - {result.qcode}: {result.status}"
        )

        # Update status in the Excel grid row
        status_tag = "✅ Done" if result.status == "Success" else "❌ Error"
        self.excel_grid.update_item_status(result.qcode, status_tag)

        # Add result to gallery list
        self._add_result_to_gallery(result, auto_display=(current == 1))

    def _on_batch_complete(self, summary: BatchDownloadSummary):
        self.is_downloading = False
        self.btn_batch_start.configure(state="normal")
        self.btn_batch_stop.configure(state="disabled")

        if summary.error_message:
            messagebox.showerror("Batch Download Error", summary.error_message)
        else:
            msg = (
                f"Batch download completed in {summary.elapsed_seconds}s:\n"
                f"- Successful: {summary.total_downloaded}/{summary.total_requested}\n"
                f"- Failed: {summary.total_failed}"
            )
            self.lbl_batch_progress.configure(text=f"Completed ({summary.total_downloaded}/{summary.total_requested} images)")
            messagebox.showinfo("Batch Download Completed", msg)

    def _add_result_to_gallery(self, result: DownloadResult, auto_display: bool = False):
        # Update if exists
        for idx, existing in enumerate(self.items_gallery):
            if existing.qcode == result.qcode and existing.file_name == result.file_name:
                self.items_gallery[idx] = result
                self.gallery_view.set_items(self.items_gallery)
                self._render_filmstrip()
                if auto_display and result.status == "Success":
                    self.show_image_at_index(idx)
                return

        self.items_gallery.append(result)
        self.gallery_view.set_items(self.items_gallery)
        self._render_filmstrip()
        self._update_counter_label()
        if auto_display and result.status == "Success":
            self.show_image_at_index(len(self.items_gallery) - 1)

    # ------------------ Filmstrip (Bottom Thumbnail Strip) ------------------

    def _render_filmstrip(self):
        """Renders horizontal thumbnail filmstrip at bottom of canvas view."""
        self.filmstrip_canvas.delete("all")
        if not self.items_gallery:
            return

        x = 10
        thumb_h = 60
        thumb_w = 90

        for idx, res in enumerate(self.items_gallery):
            if res.status != "Success" or not res.local_path or not os.path.isfile(res.local_path):
                continue

            thumb = self._get_filmstrip_thumb(res.local_path, thumb_w, thumb_h)
            is_active = (idx == self.current_index)

            # Draw thumbnail image
            if thumb:
                img_id = self.filmstrip_canvas.create_image(x, 10, anchor="nw", image=thumb)
                self.filmstrip_canvas.tag_bind(img_id, "<Button-1>", lambda e, i=idx: self.show_image_at_index(i))

            # Border rectangle (highlight if active)
            rect_color = "#0052cc" if is_active else "#555a64"
            rect_width = 3 if is_active else 1
            rect_id = self.filmstrip_canvas.create_rectangle(
                x, 10, x + thumb_w, 10 + thumb_h,
                outline=rect_color, width=rect_width
            )
            self.filmstrip_canvas.tag_bind(rect_id, "<Button-1>", lambda e, i=idx: self.show_image_at_index(i))

            # Label below thumb
            lbl_id = self.filmstrip_canvas.create_text(
                x + thumb_w // 2, 10 + thumb_h + 8,
                text=res.qcode, fill="#ffffff" if is_active else "#a0aec0",
                font=("Segoe UI", 8, "bold" if is_active else "normal")
            )
            self.filmstrip_canvas.tag_bind(lbl_id, "<Button-1>", lambda e, i=idx: self.show_image_at_index(i))

            x += thumb_w + 14

        self.filmstrip_canvas.configure(scrollregion=(0, 0, x + 20, 85))

    def _get_filmstrip_thumb(self, path: str, width: int, height: int) -> Optional[ImageTk.PhotoImage]:
        if not HAS_PIL:
            return None
        cache_key = f"{path}_{width}x{height}"
        if cache_key in self.filmstrip_cache:
            return self.filmstrip_cache[cache_key]

        try:
            with Image.open(path) as im:
                im.thumbnail((width, height), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.ANTIALIAS)
                photo = ImageTk.PhotoImage(im)
                self.filmstrip_cache[cache_key] = photo
                return photo
        except Exception:
            return None

    # ------------------ Navigation in Batch ------------------

    def show_image_at_index(self, idx: int):
        """Loads and displays image at given gallery index."""
        if not (0 <= idx < len(self.items_gallery)):
            return

        self.current_index = idx
        res = self.items_gallery[idx]

        self._update_counter_label()
        self._render_filmstrip()

        if res.status == "Success" and res.local_path and os.path.isfile(res.local_path):
            self.load_image_file(res.local_path, res)
        else:
            self.current_image_path = None
            self.raw_pil_image = None
            self.canvas.delete("all")
            self.lbl_meta.configure(
                text=f"[{idx + 1}/{len(self.items_gallery)}] {res.qcode} ({res.custom_name or 'No alias'}): {res.status}"
            )

    def _update_counter_label(self):
        total = len(self.items_gallery)
        cur = self.current_index + 1 if (0 <= self.current_index < total) else 0
        self.lbl_batch_counter.configure(text=f"[ {cur} / {total} ]")

    def _go_prev_image(self):
        if not self.items_gallery:
            return
        target = self.current_index - 1
        if target < 0:
            target = len(self.items_gallery) - 1
        self.show_image_at_index(target)

    def _go_next_image(self):
        if not self.items_gallery:
            return
        target = self.current_index + 1
        if target >= len(self.items_gallery):
            target = 0
        self.show_image_at_index(target)

    def _go_first_image(self):
        if self.items_gallery:
            self.show_image_at_index(0)

    def _go_last_image(self):
        if self.items_gallery:
            self.show_image_at_index(len(self.items_gallery) - 1)

    # ------------------ Image Rendering & Canvas Engine ------------------

    def load_image_file(self, file_path: str, meta: Optional[DownloadResult] = None):
        if not HAS_PIL:
            self.lbl_meta.configure(text="Pillow (PIL) library is not installed.")
            return

        if not os.path.isfile(file_path):
            self.lbl_meta.configure(text=f"Image file not found: {file_path}")
            return

        try:
            self.current_image_path = file_path
            self.raw_pil_image = Image.open(file_path)
            w, h = self.raw_pil_image.size
            size_kb = os.path.getsize(file_path) / 1024.0

            if meta:
                meta.image_width = w
                meta.image_height = h

            qcode_prefix = f"QCode: {meta.qcode} | " if meta else ""
            alias_prefix = f"Alias: {meta.custom_name} | " if (meta and meta.custom_name) else ""
            idx_prefix = f"[{self.current_index + 1}/{len(self.items_gallery)}] " if self.current_index >= 0 else ""

            self.lbl_meta.configure(
                text=f"{idx_prefix}{qcode_prefix}{alias_prefix}{os.path.basename(file_path)} "
                     f"({w}x{h} px, {size_kb:.1f} KB) - {file_path}"
            )

            # Fit to screen initially
            self._fit_to_screen()

        except Exception as e:
            logger.exception("Error loading image %s: %s", file_path, e)
            self.lbl_meta.configure(text=f"Error reading image file: {e}")

    def _render_image(self):
        """Renders scaled image onto canvas at current viewport offset."""
        if not self.raw_pil_image:
            return

        orig_w, orig_h = self.raw_pil_image.size
        new_w = max(10, int(orig_w * self.zoom_level))
        new_h = max(10, int(orig_h * self.zoom_level))

        resample_filter = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.ANTIALIAS
        resized = self.raw_pil_image.resize((new_w, new_h), resample_filter)
        self.tk_image_cache = ImageTk.PhotoImage(resized)

        self.canvas.delete("all")
        self.canvas.create_image(self.img_pos_x, self.img_pos_y, anchor="nw", image=self.tk_image_cache)
        self.lbl_zoom.configure(text=f"{int(self.zoom_level * 100)}%")

    def _zoom_delta(self, factor: float, center_x: Optional[int] = None, center_y: Optional[int] = None):
        if not self.raw_pil_image:
            return

        old_zoom = self.zoom_level
        new_zoom = max(0.04, min(12.0, self.zoom_level * factor))
        if new_zoom == old_zoom:
            return

        if center_x is not None and center_y is not None:
            self.img_pos_x = int(center_x - (center_x - self.img_pos_x) * (new_zoom / old_zoom))
            self.img_pos_y = int(center_y - (center_y - self.img_pos_y) * (new_zoom / old_zoom))

        self.zoom_level = new_zoom
        self._render_image()

    def _zoom_in(self):
        self._zoom_delta(1.25)

    def _zoom_out(self):
        self._zoom_delta(0.8)

    def _zoom_100(self):
        if not self.raw_pil_image:
            return
        self.zoom_level = 1.0
        self._center_image()
        self._render_image()

    def _fit_to_screen(self):
        """Scales image so entire drawing fits inside the visible canvas."""
        if not self.raw_pil_image:
            return

        canv_w = self.canvas.winfo_width()
        canv_h = self.canvas.winfo_height()
        if canv_w <= 1 or canv_h <= 1:
            canv_w, canv_h = 800, 600

        img_w, img_h = self.raw_pil_image.size
        scale = min((canv_w - 20) / img_w, (canv_h - 20) / img_h, 1.0)
        self.zoom_level = max(0.05, scale)

        scaled_w = int(img_w * self.zoom_level)
        scaled_h = int(img_h * self.zoom_level)
        self.img_pos_x = max(10, (canv_w - scaled_w) // 2)
        self.img_pos_y = max(10, (canv_h - scaled_h) // 2)

        self._render_image()

    def _fit_width(self):
        """Scales image to fit canvas width."""
        if not self.raw_pil_image:
            return
        canv_w = self.canvas.winfo_width()
        if canv_w <= 1:
            canv_w = 800
        img_w, _ = self.raw_pil_image.size
        self.zoom_level = max(0.05, (canv_w - 20) / img_w)
        self.img_pos_x = 10
        self.img_pos_y = 10
        self._render_image()

    def _center_image(self):
        if not self.raw_pil_image:
            return
        canv_w = self.canvas.winfo_width()
        canv_h = self.canvas.winfo_height()
        img_w, img_h = self.raw_pil_image.size
        scaled_w = int(img_w * self.zoom_level)
        scaled_h = int(img_h * self.zoom_level)
        self.img_pos_x = (canv_w - scaled_w) // 2
        self.img_pos_y = (canv_h - scaled_h) // 2

    def _on_canvas_resize(self):
        if self.raw_pil_image and self.zoom_level <= 1.0:
            self._fit_to_screen()

    def _on_pan_start(self, event):
        self.pan_start_x = event.x
        self.pan_start_y = event.y

    def _on_pan_move(self, event):
        dx = event.x - self.pan_start_x
        dy = event.y - self.pan_start_y
        self.img_pos_x += dx
        self.img_pos_y += dy
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        self._render_image()

    def _on_mouse_wheel(self, event):
        factor = 1.15 if event.delta > 0 else 0.85
        self._zoom_delta(factor, event.x, event.y)

    def _open_in_external_app(self):
        if not self.current_image_path or not os.path.isfile(self.current_image_path):
            return
        try:
            if sys.platform == "win32":
                os.startfile(self.current_image_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.current_image_path])
            else:
                subprocess.Popen(["xdg-open", self.current_image_path])
        except Exception as e:
            messagebox.showerror("Open File Error", f"Cannot open system image viewer: {e}")

    def _open_download_folder(self):
        target_dir = self.download_dir.get()
        if not os.path.isdir(target_dir):
            os.makedirs(target_dir, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(target_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target_dir])
            else:
                subprocess.Popen(["xdg-open", target_dir])
        except Exception as e:
            messagebox.showerror("Open Directory Error", f"Cannot open folder: {e}")

    def _export_csv(self):
        if not self.items_gallery:
            messagebox.showinfo("Empty", "No data to export.")
            return

        path = filedialog.asksaveasfilename(
            title="Save CSV Report",
            defaultextension=".csv",
            filetypes=[("CSV file", "*.csv")],
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["#", "QCode", "Alias", "Status", "Resolution", "Size (Bytes)", "File Name", "Path"])
                for i, r in enumerate(self.items_gallery, 1):
                    res_str = f"{r.image_width}x{r.image_height}" if r.image_width > 0 else ""
                    writer.writerow([i, r.qcode, r.custom_name, r.status, res_str, r.file_size_bytes, r.file_name, r.local_path])
            messagebox.showinfo("Export Successful", f"Saved CSV report to file:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Cannot save CSV file: {e}")


def launch_gui():
    """Starts the Batch Blueprint Viewer Application."""
    app = DrawingViewerApp()
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
