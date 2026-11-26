"""Main Tkinter Desktop Window for Windows Disk Analyzer."""

from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Dict, List, Optional, Set

from disk_analyzer import __app_name__, __version__
from disk_analyzer.cleaner import SafeCleaner
from disk_analyzer.diagnostics import WindowsDiagnostics
from disk_analyzer.exporter import export_csv, export_html, export_json, export_markdown
from disk_analyzer.formatters import format_bytes, format_duration, format_timestamp, truncate_middle
from disk_analyzer.models import (
    CleanupSummary,
    DiagnosticItem,
    DiagnosticSummary,
    FileEntry,
    FolderNode,
    SafetyLevel,
    ScanResult,
)
from disk_analyzer.scanner import DiskScanner
from disk_analyzer.win32_api import is_admin, launch_disk_cleanup, open_in_explorer
from gui.chart_canvas import DriveCardsStrip, TreemapCanvas
from gui.theme import Theme


_EXT_GROUPS = {
    "All Types": None,
    "Virtual Disks (.vhdx/.vmdk/.iso)": {".vhdx", ".vhd", ".vmdk", ".vdi", ".iso", ".img"},
    "Archives (.zip/.rar/.7z/.tar)": {".zip", ".rar", ".7z", ".tar", ".gz", ".xz"},
    "Videos (.mp4/.mkv/.avi/.mov)": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"},
    "Installers (.exe/.msi/.msix)": {".exe", ".msi", ".msix", ".cab"},
    "Logs & Dumps (.log/.dmp/.tmp)": {".log", ".dmp", ".hdmp", ".mdmp", ".tmp", ".etl"},
    "Outlook Data (.ost/.pst)": {".ost", ".pst"},
}


class DiskAnalyzerWindow(tk.Tk):
    """Main desktop UI for auditing Windows disk usage and safely reclaiming space."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{__app_name__} v{__version__}")
        self.geometry("1260x800")
        self.minsize(1020, 660)
        Theme.apply(self)

        self._ui_queue: queue.Queue = queue.Queue()
        self._cancel_event: Optional[threading.Event] = None
        self._worker_busy = False

        self._diag_summary: Optional[DiagnosticSummary] = None
        self._scan_result: Optional[ScanResult] = None

        self._node_by_iid: Dict[str, FolderNode] = {}
        self._iid_by_path: Dict[str, str] = {}
        self._diag_by_iid: Dict[str, DiagnosticItem] = {}
        self._clean_checked: Set[str] = set()
        self._clean_by_iid: Dict[str, DiagnosticItem] = {}
        self._file_by_iid: Dict[str, FileEntry] = {}

        self._build_header()
        self._build_toolbar()
        self._build_status_strip()
        self._build_tabs()
        self._build_footer()

        self.after(80, self._drain_ui_queue)
        self.after(180, self.start_diagnostic_audit)

    # ------------------------------------------------------------------
    # Layout builders
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=Theme.BG_DARK, padx=16, pady=12)
        header.pack(fill=tk.X, side=tk.TOP)

        left = tk.Frame(header, bg=Theme.BG_DARK)
        left.pack(side=tk.LEFT)

        tk.Label(
            left,
            text=f"{__app_name__}",
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_LIGHT,
            font=(Theme.FONT_FAMILY, 16, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            left,
            text="Diagnose Windows low-disk-space causes • Analyze folder trees • Safe cleanup",
            bg=Theme.BG_DARK,
            fg="#94A3B8",
            font=(Theme.FONT_FAMILY, 9),
        ).pack(anchor=tk.W)

        right = tk.Frame(header, bg=Theme.BG_DARK)
        right.pack(side=tk.RIGHT)

        admin_ok = is_admin()
        badge_bg = Theme.SUCCESS if admin_ok else "#475569"
        badge_txt = "Privilege: Administrator" if admin_ok else "Privilege: Standard User"
        tk.Label(
            right,
            text=badge_txt,
            bg=badge_bg,
            fg="#FFFFFF",
            font=(Theme.FONT_FAMILY, 9, "bold"),
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            right,
            text="Disk Cleanup",
            style="Secondary.TButton",
            command=self._open_cleanmgr,
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            right,
            text="Export Report...",
            style="Primary.TButton",
            command=self._export_report_dialog,
        ).pack(side=tk.LEFT, padx=(4, 0))

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self, bg=Theme.BG_CARD, highlightbackground=Theme.BORDER, highlightthickness=1, padx=14, pady=8)
        bar.pack(fill=tk.X, padx=12, pady=(10, 6))

        self.btn_audit = ttk.Button(
            bar,
            text="1. Run Windows Audit",
            style="Primary.TButton",
            command=self.start_diagnostic_audit,
        )
        self.btn_audit.pack(side=tk.LEFT)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12)

        tk.Label(
            bar,
            text="Scan Target:",
            bg=Theme.BG_CARD,
            fg=Theme.TEXT_MAIN,
            font=(Theme.FONT_FAMILY, 9, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 6))

        default_targets = self._default_scan_targets()
        self.var_scan_path = tk.StringVar(value=default_targets[0] if default_targets else "C:\\")
        self.combo_scan_path = ttk.Combobox(
            bar,
            textvariable=self.var_scan_path,
            values=default_targets,
            width=36,
        )
        self.combo_scan_path.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(bar, text="Browse...", style="Secondary.TButton", command=self._browse_scan_path).pack(side=tk.LEFT, padx=(0, 6))

        self.btn_scan = ttk.Button(
            bar,
            text="2. Scan Folder & Large Files",
            style="Primary.TButton",
            command=lambda: self.start_folder_scan(self.var_scan_path.get()),
        )
        self.btn_scan.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_cancel = ttk.Button(
            bar,
            text="Stop",
            style="Danger.TButton",
            command=self._cancel_current_task,
        )
        self.btn_cancel.pack(side=tk.LEFT)
        self.btn_cancel.state(["disabled"])

    def _build_status_strip(self) -> None:
        strip = tk.Frame(self, bg=Theme.BG_LIGHT, padx=14, pady=2)
        strip.pack(fill=tk.X)

        self.var_status = tk.StringVar(value="Ready to inspect Windows storage.")
        tk.Label(
            strip,
            textvariable=self.var_status,
            bg=Theme.BG_LIGHT,
            fg=Theme.TEXT_MUTED,
            font=(Theme.FONT_FAMILY, 9),
            anchor=tk.W,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.progress_bar = ttk.Progressbar(strip, mode="indeterminate", length=200)
        self.progress_bar.pack(side=tk.RIGHT)

    def _build_tabs(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 8))

        self.tab_overview = ttk.Frame(self.notebook, padding=8)
        self.tab_tree = ttk.Frame(self.notebook, padding=8)
        self.tab_files = ttk.Frame(self.notebook, padding=8)
        self.tab_cleanup = ttk.Frame(self.notebook, padding=8)

        self.notebook.add(self.tab_overview, text="  Overview & Diagnostics  ")
        self.notebook.add(self.tab_tree, text="  Folder Tree & Treemap  ")
        self.notebook.add(self.tab_files, text="  Largest Files & Types  ")
        self.notebook.add(self.tab_cleanup, text="  Safe Cleanup & Guides  ")

        self._build_overview_tab()
        self._build_tree_tab()
        self._build_files_tab()
        self._build_cleanup_tab()

    def _build_overview_tab(self) -> None:
        self.drive_cards = DriveCardsStrip(self.tab_overview, on_scan_drive=self._scan_drive_and_switch)
        self.drive_cards.pack(fill=tk.X, pady=(0, 10))

        mid = tk.Frame(self.tab_overview, bg=Theme.BG_LIGHT)
        mid.pack(fill=tk.X, pady=(0, 10))

        kpi_box = tk.Frame(mid, bg=Theme.BG_CARD, highlightbackground=Theme.BORDER, highlightthickness=1, padx=16, pady=12, width=250)
        kpi_box.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        kpi_box.pack_propagate(False)

        tk.Label(kpi_box, text="STORAGE HEALTH SCORE", bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED, font=(Theme.FONT_FAMILY, 8, "bold")).pack(anchor=tk.W)
        self.lbl_health_score = tk.Label(kpi_box, text="--/100", bg=Theme.BG_CARD, fg=Theme.PRIMARY, font=(Theme.FONT_FAMILY, 24, "bold"))
        self.lbl_health_score.pack(anchor=tk.W, pady=(2, 6))
        self.lbl_reclaimable = tk.Label(kpi_box, text="Safe to reclaim: --", bg=Theme.BG_CARD, fg=Theme.SUCCESS, font=(Theme.FONT_FAMILY, 9, "bold"), wraplength=215, justify=tk.LEFT)
        self.lbl_reclaimable.pack(anchor=tk.W)

        rec_frame = ttk.LabelFrame(mid, text="Priority Analysis & Recommendations", style="Section.TLabelframe", padding=10)
        rec_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.txt_recs = tk.Text(
            rec_frame,
            height=5,
            wrap=tk.WORD,
            bg=Theme.BG_CARD,
            fg=Theme.TEXT_MAIN,
            relief=tk.FLAT,
            font=(Theme.FONT_FAMILY, 9),
        )
        self.txt_recs.pack(fill=tk.BOTH, expand=True)
        self.txt_recs.configure(state=tk.DISABLED)

        tbl_wrap = ttk.LabelFrame(
            self.tab_overview,
            text="Windows Disk Space Consumers Breakdown",
            style="Section.TLabelframe",
            padding=8,
        )
        tbl_wrap.pack(fill=tk.BOTH, expand=True)

        filter_bar = tk.Frame(tbl_wrap, bg=Theme.BG_CARD)
        filter_bar.pack(fill=tk.X, pady=(0, 6))

        tk.Label(filter_bar, text="Safety Filter:", bg=Theme.BG_CARD, font=(Theme.FONT_FAMILY, 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        self.var_diag_filter = tk.StringVar(value="all")
        for val, text in [("all", "All"), ("safe", "Safe"), ("review", "Review First"), ("system", "System")]:
            ttk.Radiobutton(
                filter_bar,
                text=text,
                value=val,
                variable=self.var_diag_filter,
                command=self._refresh_diag_table,
            ).pack(side=tk.LEFT, padx=6)

        self.var_hide_empty = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            filter_bar,
            text="Hide empty / missing items (0 B)",
            variable=self.var_hide_empty,
            command=self._refresh_diag_table,
        ).pack(side=tk.RIGHT)

        cols = ("name", "category", "safety", "size", "files", "action")
        tree_frame = tk.Frame(tbl_wrap, bg=Theme.BG_CARD)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.tree_diag = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.tree_diag.heading("name", text="Diagnostic Item")
        self.tree_diag.heading("category", text="Category")
        self.tree_diag.heading("safety", text="Safety")
        self.tree_diag.heading("size", text="Size on Disk")
        self.tree_diag.heading("files", text="Files")
        self.tree_diag.heading("action", text="Recommended Action")

        self.tree_diag.column("name", width=280, anchor=tk.W)
        self.tree_diag.column("category", width=165, anchor=tk.W)
        self.tree_diag.column("safety", width=95, anchor=tk.CENTER)
        self.tree_diag.column("size", width=105, anchor=tk.E)
        self.tree_diag.column("files", width=80, anchor=tk.E)
        self.tree_diag.column("action", width=410, anchor=tk.W)

        self.tree_diag.tag_configure("safe", foreground=Theme.SUCCESS)
        self.tree_diag.tag_configure("review", foreground=Theme.WARNING)
        self.tree_diag.tag_configure("system", foreground="#475569")

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree_diag.yview)
        self.tree_diag.configure(yscrollcommand=vsb.set)
        self.tree_diag.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        action_bar = tk.Frame(tbl_wrap, bg=Theme.BG_CARD)
        action_bar.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(action_bar, text="Open in File Explorer", style="Secondary.TButton", command=self._open_selected_diag_path).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(action_bar, text="Deep-Scan Item", style="Secondary.TButton", command=self._scan_selected_diag_path).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(action_bar, text="Copy Suggested Command", style="Secondary.TButton", command=self._copy_selected_diag_cmd).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(action_bar, text="Go to Cleanup Tab ->", style="Primary.TButton", command=lambda: self.notebook.select(self.tab_cleanup)).pack(side=tk.RIGHT)

    def _build_tree_tab(self) -> None:
        paned = ttk.PanedWindow(self.tab_tree, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        top_box = ttk.Frame(paned)
        paned.add(top_box, weight=3)

        top_bar = tk.Frame(top_box, bg=Theme.BG_LIGHT)
        top_bar.pack(fill=tk.X, pady=(0, 6))
        self.lbl_scan_summary = tk.Label(
            top_bar,
            text="No folder scan yet. Select a drive or directory above and click 'Scan Folder & Large Files'.",
            bg=Theme.BG_LIGHT,
            fg=Theme.TEXT_MAIN,
            font=(Theme.FONT_FAMILY, 9, "bold"),
        )
        self.lbl_scan_summary.pack(side=tk.LEFT)

        ttk.Button(top_bar, text="Open in Explorer", style="Secondary.TButton", command=self._open_selected_tree_node).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(top_bar, text="Copy Path", style="Secondary.TButton", command=self._copy_selected_tree_path).pack(side=tk.RIGHT)

        cols = ("disk", "logical", "pct", "files", "dirs", "mtime")
        tree_wrap = tk.Frame(top_box)
        tree_wrap.pack(fill=tk.BOTH, expand=True)

        self.tree_folders = ttk.Treeview(tree_wrap, columns=cols, show="tree headings", selectmode="browse")
        self.tree_folders.heading("#0", text="Folder")
        self.tree_folders.heading("disk", text="Size on Disk")
        self.tree_folders.heading("logical", text="Logical Size")
        self.tree_folders.heading("pct", text="Share %")
        self.tree_folders.heading("files", text="Files")
        self.tree_folders.heading("dirs", text="Subfolders")
        self.tree_folders.heading("mtime", text="Last Modified")

        self.tree_folders.column("#0", width=440, anchor=tk.W)
        self.tree_folders.column("disk", width=115, anchor=tk.E)
        self.tree_folders.column("logical", width=115, anchor=tk.E)
        self.tree_folders.column("pct", width=75, anchor=tk.E)
        self.tree_folders.column("files", width=85, anchor=tk.E)
        self.tree_folders.column("dirs", width=85, anchor=tk.E)
        self.tree_folders.column("mtime", width=120, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=self.tree_folders.yview)
        self.tree_folders.configure(yscrollcommand=vsb.set)
        self.tree_folders.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree_folders.bind("<<TreeviewOpen>>", self._on_folder_expand)
        self.tree_folders.bind("<<TreeviewSelect>>", self._on_folder_select)
        self.tree_folders.bind("<Double-1>", self._on_folder_double_click)

        bottom_box = ttk.Frame(paned)
        paned.add(bottom_box, weight=2)
        self.treemap = TreemapCanvas(bottom_box, on_select_node=self._focus_tree_on_node)
        self.treemap.pack(fill=tk.BOTH, expand=True)

    def _build_files_tab(self) -> None:
        paned = ttk.PanedWindow(self.tab_files, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(paned, padding=(0, 0, 6, 0))
        right = ttk.Frame(paned, padding=(6, 0, 0, 0))
        paned.add(left, weight=3)
        paned.add(right, weight=1)

        fbar = tk.Frame(left, bg=Theme.BG_CARD, highlightbackground=Theme.BORDER, highlightthickness=1, padx=8, pady=6)
        fbar.pack(fill=tk.X, pady=(0, 6))

        tk.Label(fbar, text="Filter:", bg=Theme.BG_CARD, font=(Theme.FONT_FAMILY, 9)).pack(side=tk.LEFT)
        self.var_file_search = tk.StringVar()
        ent = ttk.Entry(fbar, textvariable=self.var_file_search, width=18)
        ent.pack(side=tk.LEFT, padx=(4, 10))
        ent.bind("<KeyRelease>", lambda _e: self._refresh_files_table())

        tk.Label(fbar, text="Min Size (MB):", bg=Theme.BG_CARD, font=(Theme.FONT_FAMILY, 9)).pack(side=tk.LEFT)
        self.var_min_mb = tk.StringVar(value="10")
        cb_mb = ttk.Combobox(fbar, textvariable=self.var_min_mb, values=["1", "10", "50", "100", "500", "1024"], width=6, state="readonly")
        cb_mb.pack(side=tk.LEFT, padx=(4, 10))
        cb_mb.bind("<<ComboboxSelected>>", lambda _e: self._refresh_files_table())

        tk.Label(fbar, text="Type:", bg=Theme.BG_CARD, font=(Theme.FONT_FAMILY, 9)).pack(side=tk.LEFT)
        self.var_ext_group = tk.StringVar(value="All Types")
        cb_ext = ttk.Combobox(fbar, textvariable=self.var_ext_group, values=list(_EXT_GROUPS.keys()), width=25, state="readonly")
        cb_ext.pack(side=tk.LEFT, padx=(4, 10))
        cb_ext.bind("<<ComboboxSelected>>", lambda _e: self._refresh_files_table())

        tk.Label(fbar, text="Older than:", bg=Theme.BG_CARD, font=(Theme.FONT_FAMILY, 9)).pack(side=tk.LEFT)
        self.var_age_days = tk.StringVar(value="Any")
        cb_age = ttk.Combobox(fbar, textvariable=self.var_age_days, values=["Any", "30 days", "90 days", "180 days", "365 days"], width=10, state="readonly")
        cb_age.pack(side=tk.LEFT, padx=4)
        cb_age.bind("<<ComboboxSelected>>", lambda _e: self._refresh_files_table())

        cols = ("name", "ext", "disk", "logical", "state", "mtime", "dir")
        wrap = tk.Frame(left)
        wrap.pack(fill=tk.BOTH, expand=True)

        self.tree_files = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="extended")
        self.tree_files.heading("name", text="File Name")
        self.tree_files.heading("ext", text="Ext")
        self.tree_files.heading("disk", text="Size on Disk")
        self.tree_files.heading("logical", text="Logical Size")
        self.tree_files.heading("state", text="Storage")
        self.tree_files.heading("mtime", text="Modified")
        self.tree_files.heading("dir", text="Parent Folder")

        self.tree_files.column("name", width=210, anchor=tk.W)
        self.tree_files.column("ext", width=65, anchor=tk.CENTER)
        self.tree_files.column("disk", width=95, anchor=tk.E)
        self.tree_files.column("logical", width=95, anchor=tk.E)
        self.tree_files.column("state", width=85, anchor=tk.CENTER)
        self.tree_files.column("mtime", width=95, anchor=tk.CENTER)
        self.tree_files.column("dir", width=300, anchor=tk.W)

        vsb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.tree_files.yview)
        self.tree_files.configure(yscrollcommand=vsb.set)
        self.tree_files.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        f_actions = tk.Frame(left, bg=Theme.BG_LIGHT)
        f_actions.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(f_actions, text="Open Containing Folder", style="Secondary.TButton", command=self._open_selected_file).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(f_actions, text="Copy Full Path", style="Secondary.TButton", command=self._copy_selected_file_path).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(f_actions, text="Move Selected Files to Recycle Bin", style="Danger.TButton", command=self._delete_selected_large_files).pack(side=tk.RIGHT)

        ext_box = ttk.LabelFrame(right, text="Usage by File Extension", style="Section.TLabelframe", padding=8)
        ext_box.pack(fill=tk.BOTH, expand=True)

        ecols = ("ext", "count", "disk")
        ewrap = tk.Frame(ext_box)
        ewrap.pack(fill=tk.BOTH, expand=True)
        self.tree_exts = ttk.Treeview(ewrap, columns=ecols, show="headings", selectmode="browse")
        self.tree_exts.heading("ext", text="Extension")
        self.tree_exts.heading("count", text="Files")
        self.tree_exts.heading("disk", text="Size on Disk")
        self.tree_exts.column("ext", width=95, anchor=tk.W)
        self.tree_exts.column("count", width=75, anchor=tk.E)
        self.tree_exts.column("disk", width=105, anchor=tk.E)

        evsb = ttk.Scrollbar(ewrap, orient=tk.VERTICAL, command=self.tree_exts.yview)
        self.tree_exts.configure(yscrollcommand=evsb.set)
        self.tree_exts.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        evsb.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_cleanup_tab(self) -> None:
        paned = ttk.PanedWindow(self.tab_cleanup, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        top = ttk.LabelFrame(
            paned,
            text="Select Temp / Cache Items to Clean Safely (Click any row to toggle selection)",
            style="Section.TLabelframe",
            padding=8,
        )
        paned.add(top, weight=3)

        cols = ("chk", "name", "safety", "size", "files", "note")
        cwrap = tk.Frame(top)
        cwrap.pack(fill=tk.BOTH, expand=True)
        self.tree_clean = ttk.Treeview(cwrap, columns=cols, show="headings", selectmode="browse")
        self.tree_clean.heading("chk", text="Select")
        self.tree_clean.heading("name", text="Cleanup Item")
        self.tree_clean.heading("safety", text="Safety")
        self.tree_clean.heading("size", text="Est. Reclaim")
        self.tree_clean.heading("files", text="Files")
        self.tree_clean.heading("note", text="Notes")

        self.tree_clean.column("chk", width=55, anchor=tk.CENTER)
        self.tree_clean.column("name", width=290, anchor=tk.W)
        self.tree_clean.column("safety", width=90, anchor=tk.CENTER)
        self.tree_clean.column("size", width=115, anchor=tk.E)
        self.tree_clean.column("files", width=80, anchor=tk.E)
        self.tree_clean.column("note", width=420, anchor=tk.W)

        self.tree_clean.tag_configure("safe", foreground=Theme.SUCCESS)
        self.tree_clean.tag_configure("review", foreground=Theme.WARNING)

        vsb = ttk.Scrollbar(cwrap, orient=tk.VERTICAL, command=self.tree_clean.yview)
        self.tree_clean.configure(yscrollcommand=vsb.set)
        self.tree_clean.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_clean.bind("<Button-1>", self._on_clean_tree_click)

        controls = tk.Frame(top, bg=Theme.BG_CARD)
        controls.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(controls, text="Select Safe Only", style="Secondary.TButton", command=self._select_safe_clean_items).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(controls, text="Select All", style="Secondary.TButton", command=self._select_all_clean_items).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(controls, text="Clear Selection", style="Secondary.TButton", command=self._clear_clean_selection).pack(side=tk.LEFT, padx=(0, 12))

        self.var_clean_recycle = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            controls,
            text="Send Temp/Cache items to Recycle Bin (slower, recoverable)",
            variable=self.var_clean_recycle,
        ).pack(side=tk.LEFT)

        self.btn_exec_clean = ttk.Button(controls, text="Execute Cleanup", style="Danger.TButton", command=lambda: self._run_cleanup(dry_run=False))
        self.btn_exec_clean.pack(side=tk.RIGHT)
        self.btn_dry_run = ttk.Button(controls, text="Preview (Dry-Run)", style="Primary.TButton", command=lambda: self._run_cleanup(dry_run=True))
        self.btn_dry_run.pack(side=tk.RIGHT, padx=(0, 8))

        log_frame = ttk.LabelFrame(paned, text="Cleanup Execution Log", style="Section.TLabelframe", padding=8)
        paned.add(log_frame, weight=2)

        self.txt_clean_log = scrolledtext.ScrolledText(
            log_frame,
            height=9,
            bg=Theme.LOG_BG,
            fg=Theme.LOG_TEXT,
            font=(Theme.FONT_MONO, 9),
            relief=tk.FLAT,
        )
        self.txt_clean_log.pack(fill=tk.BOTH, expand=True)
        self._append_clean_log("Ready. Run 'Preview (Dry-Run)' first to inspect exact reclaimable files and space.")

    def _build_footer(self) -> None:
        footer = tk.Frame(self, bg=Theme.MUTED_BG, padx=14, pady=5)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(
            footer,
            text="Note: NTFS Junctions/Symlinks are automatically skipped and OneDrive Cloud-Only files report 0 B on disk to ensure accurate space totals.",
            bg=Theme.MUTED_BG,
            fg=Theme.TEXT_MUTED,
            font=(Theme.FONT_FAMILY, 8),
        ).pack(side=tk.LEFT)

    # ------------------------------------------------------------------
    # Worker orchestration
    # ------------------------------------------------------------------

    def _default_scan_targets(self) -> List[str]:
        candidates = []
        sys_drive = os.environ.get("SystemDrive", "C:").rstrip("\\") + "\\"
        candidates.append(sys_drive)
        user_prof = os.environ.get("USERPROFILE")
        if user_prof:
            candidates.append(user_prof)
            candidates.append(os.path.join(user_prof, "Downloads"))
        candidates.append(os.path.join(sys_drive, "Users"))
        return [p for p in candidates if os.path.exists(p)]

    def _set_busy(self, busy: bool, status_text: str = "") -> None:
        self._worker_busy = busy
        if busy:
            self.btn_audit.state(["disabled"])
            self.btn_scan.state(["disabled"])
            self.btn_dry_run.state(["disabled"])
            self.btn_exec_clean.state(["disabled"])
            self.btn_cancel.state(["!disabled"])
            self.progress_bar.start(12)
        else:
            self.btn_audit.state(["!disabled"])
            self.btn_scan.state(["!disabled"])
            self.btn_dry_run.state(["!disabled"])
            self.btn_exec_clean.state(["!disabled"])
            self.btn_cancel.state(["disabled"])
            self.progress_bar.stop()
        if status_text:
            self.var_status.set(status_text)

    def _cancel_current_task(self) -> None:
        if self._cancel_event:
            self._cancel_event.set()
            self.var_status.set("Stopping current operation...")

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "status":
                    self.var_status.set(payload)
                elif kind == "audit_done":
                    self._on_audit_complete(payload)
                elif kind == "scan_done":
                    self._on_scan_complete(payload)
                elif kind == "clean_done":
                    self._on_clean_complete(payload)
                elif kind == "error":
                    self._set_busy(False, f"Error: {payload}")
                    messagebox.showerror("Execution Error", str(payload))
        except queue.Empty:
            pass
        self.after(80, self._drain_ui_queue)

    def start_diagnostic_audit(self) -> None:
        if self._worker_busy:
            return
        self._cancel_event = threading.Event()
        cancel_ev = self._cancel_event
        self._set_busy(True, "Auditing logical drives and common Windows space consumers...")

        def worker() -> None:
            try:
                engine = WindowsDiagnostics()
                summary = engine.run_audit(
                    cancel_event=cancel_ev,
                    progress_cb=lambda idx, total, name: self._ui_queue.put(
                        ("status", f"Checking ({idx}/{total}): {name}")
                    ),
                )
                self._ui_queue.put(("audit_done", summary))
            except Exception as exc:
                self._ui_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_audit_complete(self, summary: DiagnosticSummary) -> None:
        self._diag_summary = summary
        self._set_busy(
            False,
            f"Audit completed at {summary.generated_at} • Health Score: {summary.health_score}/100 • Safe Reclaimable: {format_bytes(summary.reclaimable_safe_bytes)}",
        )

        ready_roots = [d.root_path for d in summary.drives if d.is_ready]
        combo_vals = list(dict.fromkeys(ready_roots + self._default_scan_targets()))
        self.combo_scan_path["values"] = combo_vals

        self.drive_cards.update_drives(summary.drives)

        score_col = Theme.SUCCESS if summary.health_score >= 80 else (Theme.WARNING if summary.health_score >= 55 else Theme.CRITICAL)
        self.lbl_health_score.configure(text=f"{summary.health_score}/100", fg=score_col)
        self.lbl_reclaimable.configure(text=f"Safe to reclaim now: {format_bytes(summary.reclaimable_safe_bytes)}")

        self.txt_recs.configure(state=tk.NORMAL)
        self.txt_recs.delete("1.0", tk.END)
        for idx, rec in enumerate(summary.recommendations, start=1):
            self.txt_recs.insert(tk.END, f"{idx}. {rec}\n")
        self.txt_recs.configure(state=tk.DISABLED)

        self._refresh_diag_table()
        self._populate_cleanup_table(default_select_safe=True)

    def _scan_drive_and_switch(self, root_path: str) -> None:
        self.var_scan_path.set(root_path)
        self.notebook.select(self.tab_tree)
        self.start_folder_scan(root_path)

    def start_folder_scan(self, target_path: str) -> None:
        if self._worker_busy:
            return
        path = target_path.strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("Invalid Path", f"Path does not exist:\n{path}")
            return

        self._cancel_event = threading.Event()
        cancel_ev = self._cancel_event
        self._set_busy(True, f"Scanning {path}...")

        def worker() -> None:
            try:
                scanner = DiskScanner(top_n_files=300, min_top_file_bytes=1024 * 1024, max_tree_depth=6)
                res = scanner.scan(
                    path,
                    cancel_event=cancel_ev,
                    progress_cb=lambda f_cnt, d_cnt, b_cnt, cur: self._ui_queue.put(
                        (
                            "status",
                            f"Scanning: {f_cnt:,} files | {d_cnt:,} folders | {format_bytes(b_cnt)} — {truncate_middle(cur, 55)}",
                        )
                    ),
                )
                self._ui_queue.put(("scan_done", res))
            except Exception as exc:
                self._ui_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_complete(self, res: ScanResult) -> None:
        self._scan_result = res
        state_note = " (Cancelled early)" if res.cancelled else ""
        self._set_busy(
            False,
            f"Scanned '{res.target_path}' in {format_duration(res.duration_sec)}{state_note}: {format_bytes(res.total_disk_bytes)} ({res.total_files:,} files)",
        )
        self.lbl_scan_summary.configure(
            text=(
                f"Target: {res.target_path}  |  On Disk: {format_bytes(res.total_disk_bytes)}  |  "
                f"Logical: {format_bytes(res.total_logical_bytes)}  |  "
                f"{res.total_files:,} files, {res.total_dirs:,} folders  |  "
                f"Time: {format_duration(res.duration_sec)}"
            )
        )
        self._populate_folder_tree(res)
        self._refresh_files_table()
        self._populate_extensions_table(res)
        if res.root_node:
            self.treemap.set_node(res.root_node, push_history=False)

    # ------------------------------------------------------------------
    # Table rendering & interactive actions
    # ------------------------------------------------------------------

    def _refresh_diag_table(self) -> None:
        self.tree_diag.delete(*self.tree_diag.get_children())
        self._diag_by_iid.clear()
        if not self._diag_summary:
            return

        filt = self.var_diag_filter.get()
        hide_empty = self.var_hide_empty.get()

        for item in self._diag_summary.items:
            if filt != "all" and item.safety.value != filt:
                continue
            if hide_empty and not item.exists and item.size_on_disk_bytes == 0 and not item.error:
                continue
            safety_lbl = {"safe": "Safe", "review": "Review", "system": "System"}[item.safety.value]
            size_lbl = "Admin Req." if (item.error and item.size_on_disk_bytes == 0 and item.file_count == 0) else format_bytes(item.size_on_disk_bytes)
            iid = self.tree_diag.insert(
                "",
                tk.END,
                values=(
                    item.name,
                    item.category,
                    safety_lbl,
                    size_lbl,
                    f"{item.file_count:,}" if item.file_count else "-",
                    item.recommended_action,
                ),
                tags=(item.safety.value,),
            )
            self._diag_by_iid[iid] = item

    def _populate_folder_tree(self, scan: ScanResult) -> None:
        self.tree_folders.delete(*self.tree_folders.get_children())
        self._node_by_iid.clear()
        self._iid_by_path.clear()
        if not scan.root_node:
            return
        total = scan.total_disk_bytes or 1
        self._insert_folder_node("", scan.root_node, total, expand=True)

    def _insert_folder_node(self, parent_iid: str, node: FolderNode, total_bytes: int, expand: bool = False) -> str:
        pct = (node.disk_bytes / total_bytes) * 100.0 if total_bytes else 0.0
        iid = self.tree_folders.insert(
            parent_iid,
            tk.END,
            text=node.name,
            open=expand,
            values=(
                format_bytes(node.disk_bytes),
                format_bytes(node.logical_bytes),
                f"{pct:.1f}%",
                f"{node.file_count:,}",
                f"{node.dir_count:,}",
                format_timestamp(node.modified_ts),
            ),
        )
        self._node_by_iid[iid] = node
        self._iid_by_path[node.path] = iid

        if node.children:
            if expand:
                for child in node.children[:150]:
                    self._insert_folder_node(iid, child, total_bytes, expand=False)
            else:
                self.tree_folders.insert(iid, tk.END, text="__lazy__")
        return iid

    def _on_folder_expand(self, _event: tk.Event) -> None:
        iid = self.tree_folders.focus()
        if not iid:
            return
        children = self.tree_folders.get_children(iid)
        if len(children) == 1 and self.tree_folders.item(children[0], "text") == "__lazy__":
            self.tree_folders.delete(children[0])
            node = self._node_by_iid.get(iid)
            if node and self._scan_result:
                total = self._scan_result.total_disk_bytes or 1
                for child in node.children[:200]:
                    self._insert_folder_node(iid, child, total, expand=False)

    def _on_folder_select(self, _event: tk.Event) -> None:
        sel = self.tree_folders.selection()
        if not sel:
            return
        node = self._node_by_iid.get(sel[0])
        if node and node.children:
            self.treemap.set_node(node, push_history=False)

    def _on_folder_double_click(self, _event: tk.Event) -> None:
        sel = self.tree_folders.selection()
        if not sel:
            return
        node = self._node_by_iid.get(sel[0])
        if node:
            self.treemap.set_node(node, push_history=True)

    def _focus_tree_on_node(self, node: FolderNode) -> None:
        iid = self._iid_by_path.get(node.path)
        if iid and self.tree_folders.exists(iid):
            self.tree_folders.selection_set(iid)
            self.tree_folders.see(iid)

    def _refresh_files_table(self) -> None:
        self.tree_files.delete(*self.tree_files.get_children())
        self._file_by_iid.clear()
        if not self._scan_result:
            return

        query = self.var_file_search.get().strip().lower()
        try:
            min_bytes = float(self.var_min_mb.get()) * 1024 * 1024
        except ValueError:
            min_bytes = 0.0
        ext_allowed = _EXT_GROUPS.get(self.var_ext_group.get())
        age_str = self.var_age_days.get()
        cutoff_ts = 0.0
        if "days" in age_str:
            days = int(age_str.split()[0])
            cutoff_ts = time.time() - (days * 86400)

        for fe in self._scan_result.top_files:
            if max(fe.disk_bytes, fe.logical_bytes) < min_bytes:
                continue
            if ext_allowed is not None and fe.extension.lower() not in ext_allowed:
                continue
            if cutoff_ts > 0 and fe.modified_ts > cutoff_ts:
                continue
            if query and query not in fe.path.lower():
                continue

            iid = self.tree_files.insert(
                "",
                tk.END,
                values=(
                    fe.name,
                    fe.extension,
                    format_bytes(fe.disk_bytes),
                    format_bytes(fe.logical_bytes),
                    "Cloud Only" if fe.is_cloud_only else "Local",
                    format_timestamp(fe.modified_ts),
                    fe.parent_dir,
                ),
            )
            self._file_by_iid[iid] = fe

    def _populate_extensions_table(self, scan: ScanResult) -> None:
        self.tree_exts.delete(*self.tree_exts.get_children())
        for st in scan.extension_stats[:120]:
            self.tree_exts.insert(
                "",
                tk.END,
                values=(st.extension, f"{st.file_count:,}", format_bytes(st.disk_bytes)),
            )

    # ------------------------------------------------------------------
    # Cleanup Tab Actions
    # ------------------------------------------------------------------

    def _populate_cleanup_table(self, default_select_safe: bool = False) -> None:
        self.tree_clean.delete(*self.tree_clean.get_children())
        self._clean_by_iid.clear()
        if not self._diag_summary:
            return

        cleanable = [i for i in self._diag_summary.items if i.can_auto_clean and (i.exists or i.size_on_disk_bytes > 0)]
        if default_select_safe:
            self._clean_checked = {
                i.item_id for i in cleanable if i.safety == SafetyLevel.SAFE and i.size_on_disk_bytes > 0
            }

        for item in cleanable:
            checked = item.item_id in self._clean_checked
            safety_lbl = "Safe" if item.safety == SafetyLevel.SAFE else "Review"
            iid = self.tree_clean.insert(
                "",
                tk.END,
                values=(
                    "[x]" if checked else "[ ]",
                    item.name,
                    safety_lbl,
                    format_bytes(item.size_on_disk_bytes),
                    f"{item.file_count:,}",
                    item.recommended_action,
                ),
                tags=(item.safety.value,),
            )
            self._clean_by_iid[iid] = item

    def _on_clean_tree_click(self, event: tk.Event) -> None:
        row_id = self.tree_clean.identify_row(event.y)
        if not row_id:
            return
        item = self._clean_by_iid.get(row_id)
        if not item:
            return
        if item.item_id in self._clean_checked:
            self._clean_checked.remove(item.item_id)
        else:
            self._clean_checked.add(item.item_id)
        vals = list(self.tree_clean.item(row_id, "values"))
        vals[0] = "[x]" if item.item_id in self._clean_checked else "[ ]"
        self.tree_clean.item(row_id, values=vals)

    def _select_safe_clean_items(self) -> None:
        self._clean_checked = {
            item.item_id
            for item in self._clean_by_iid.values()
            if item.safety == SafetyLevel.SAFE
        }
        self._populate_cleanup_table(default_select_safe=False)

    def _select_all_clean_items(self) -> None:
        self._clean_checked = {item.item_id for item in self._clean_by_iid.values()}
        self._populate_cleanup_table(default_select_safe=False)

    def _clear_clean_selection(self) -> None:
        self._clean_checked.clear()
        self._populate_cleanup_table(default_select_safe=False)

    def _run_cleanup(self, dry_run: bool) -> None:
        if self._worker_busy:
            return
        selected = [i for i in self._clean_by_iid.values() if i.item_id in self._clean_checked]
        if not selected:
            messagebox.showinfo("No Selection", "Please select at least one item to clean.")
            return

        total_est = sum(i.size_on_disk_bytes for i in selected)
        if not dry_run:
            names = "\n".join(f"- {i.name} ({format_bytes(i.size_on_disk_bytes)})" for i in selected[:10])
            if len(selected) > 10:
                names += f"\n... and {len(selected) - 10} more items"
            ok = messagebox.askyesno(
                "Confirm Cleanup",
                f"Are you sure you want to clean {len(selected)} item(s) (estimated {format_bytes(total_est)})?\n\n{names}",
                icon=messagebox.WARNING,
            )
            if not ok:
                return

        use_rb = self.var_clean_recycle.get()
        self._set_busy(True, "Running cleanup dry-run preview..." if dry_run else "Cleaning selected items...")

        def worker() -> None:
            try:
                cleaner = SafeCleaner()
                summary = cleaner.clean_diagnostic_items(selected, dry_run=dry_run, use_recycle_bin=use_rb)
                self._ui_queue.put(("clean_done", summary))
            except Exception as exc:
                self._ui_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_clean_complete(self, summary: CleanupSummary) -> None:
        mode = "DRY-RUN (Simulation)" if summary.dry_run else "CLEANUP COMPLETED"
        self._set_busy(
            False,
            f"{mode}: Reclaimed {format_bytes(summary.total_freed_bytes)} ({summary.total_deleted_files:,} files) in {format_duration(summary.duration_sec)}",
        )
        self._append_clean_log("=" * 72)
        self._append_clean_log(f"[{summary.started_at}] {mode} ({format_duration(summary.duration_sec)})")
        for res in summary.items:
            self._append_clean_log(
                f"  * {res.label}: {format_bytes(res.freed_bytes)} | {res.deleted_files:,} deleted | {res.skipped_files:,} skipped/locked"
            )
            for err in res.errors[:3]:
                self._append_clean_log(f"      [Note] {err}")
        self._append_clean_log(
            f"TOTAL: {format_bytes(summary.total_freed_bytes)} | Files: {summary.total_deleted_files:,} | Skipped: {summary.total_skipped_files:,}"
        )

        if not summary.dry_run:
            self.start_diagnostic_audit()

    def _append_clean_log(self, text: str) -> None:
        self.txt_clean_log.insert(tk.END, text + "\n")
        self.txt_clean_log.see(tk.END)

    # ------------------------------------------------------------------
    # Helper UI commands
    # ------------------------------------------------------------------

    def _browse_scan_path(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.var_scan_path.get() or "C:\\")
        if chosen:
            self.var_scan_path.set(os.path.normpath(chosen))

    def _open_cleanmgr(self) -> None:
        ok, msg = launch_disk_cleanup("C")
        if not ok:
            messagebox.showinfo("Disk Cleanup", msg)

    def _open_selected_diag_path(self) -> None:
        sel = self.tree_diag.selection()
        if not sel:
            return
        item = self._diag_by_iid.get(sel[0])
        if not item or not item.paths:
            messagebox.showinfo("Info", "This item has no direct local folder path to open.")
            return
        open_in_explorer(item.paths[0])

    def _scan_selected_diag_path(self) -> None:
        sel = self.tree_diag.selection()
        if not sel:
            return
        item = self._diag_by_iid.get(sel[0])
        if not item or not item.paths:
            return
        target = item.paths[0]
        if os.path.isfile(target):
            target = os.path.dirname(target)
        if os.path.isdir(target):
            self._scan_drive_and_switch(target)

    def _copy_selected_diag_cmd(self) -> None:
        sel = self.tree_diag.selection()
        if not sel:
            return
        item = self._diag_by_iid.get(sel[0])
        if not item:
            return
        cmd = item.command_hint or (item.paths[0] if item.paths else item.name)
        self.clipboard_clear()
        self.clipboard_append(cmd)
        self.var_status.set(f"Copied: {cmd}")

    def _open_selected_tree_node(self) -> None:
        sel = self.tree_folders.selection()
        if not sel:
            return
        node = self._node_by_iid.get(sel[0])
        if node:
            open_in_explorer(node.path)

    def _copy_selected_tree_path(self) -> None:
        sel = self.tree_folders.selection()
        if not sel:
            return
        node = self._node_by_iid.get(sel[0])
        if node:
            self.clipboard_clear()
            self.clipboard_append(node.path)
            self.var_status.set(f"Copied path: {node.path}")

    def _open_selected_file(self) -> None:
        sel = self.tree_files.selection()
        if not sel:
            return
        fe = self._file_by_iid.get(sel[0])
        if fe:
            open_in_explorer(fe.path)

    def _copy_selected_file_path(self) -> None:
        sel = self.tree_files.selection()
        if not sel:
            return
        fe = self._file_by_iid.get(sel[0])
        if fe:
            self.clipboard_clear()
            self.clipboard_append(fe.path)
            self.var_status.set(f"Copied: {fe.path}")

    def _delete_selected_large_files(self) -> None:
        sel = self.tree_files.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select one or more files in the table first.")
            return
        files = [self._file_by_iid[iid] for iid in sel if iid in self._file_by_iid]
        total = sum(f.disk_bytes for f in files)
        preview = "\n".join(f"- {f.name} ({format_bytes(f.disk_bytes)})" for f in files[:8])
        if len(files) > 8:
            preview += f"\n... and {len(files) - 8} more files"

        if not messagebox.askyesno(
            "Move to Recycle Bin",
            f"Move {len(files)} file(s) ({format_bytes(total)}) to the Windows Recycle Bin?\n\n{preview}",
            icon=messagebox.WARNING,
        ):
            return

        cleaner = SafeCleaner()
        res = cleaner.delete_selected_files([f.path for f in files], dry_run=False, use_recycle_bin=True)
        messagebox.showinfo(
            "Result",
            f"Deleted: {res.total_deleted_files} file(s) ({format_bytes(res.total_freed_bytes)}).\n"
            f"Skipped/Errors: {res.total_skipped_files} file(s).",
        )
        if self._scan_result:
            deleted_set = {f.path for f in files if not os.path.exists(f.path)}
            self._scan_result.top_files = [f for f in self._scan_result.top_files if f.path not in deleted_set]
            self._refresh_files_table()
        self.start_diagnostic_audit()

    def _export_report_dialog(self) -> None:
        if not self._diag_summary and not self._scan_result:
            messagebox.showinfo("No Data", "Please run an audit or folder scan before exporting a report.")
            return
        out = filedialog.asksaveasfilename(
            title="Save Windows Disk Report",
            defaultextension=".html",
            initialfile="windows_disk_report.html",
            filetypes=[
                ("HTML Dashboard", "*.html"),
                ("Markdown Report", "*.md"),
                ("CSV (Excel)", "*.csv"),
                ("JSON Data", "*.json"),
            ],
        )
        if not out:
            return
        ext = os.path.splitext(out)[1].lower()
        if ext == ".json":
            saved = export_json(out, diagnostic=self._diag_summary, scan=self._scan_result)
        elif ext in (".md", ".markdown"):
            saved = export_markdown(out, diagnostic=self._diag_summary, scan=self._scan_result)
        elif ext == ".csv":
            saved = export_csv(out, diagnostic=self._diag_summary, scan=self._scan_result)
        else:
            saved = export_html(out, diagnostic=self._diag_summary, scan=self._scan_result)

        self.var_status.set(f"Report exported: {saved}")
        if messagebox.askyesno("Export Complete", f"Saved report to:\n{saved}\n\nOpen containing folder?"):
            open_in_explorer(saved)


def launch_gui() -> None:
    app = DiskAnalyzerWindow()
    app.mainloop()
