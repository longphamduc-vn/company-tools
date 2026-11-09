"""Main Application Window for Outlook Rule Companion."""
import tkinter as tk
from tkinter import ttk, messagebox
import os

from core.yaml_manager import YamlConfigManager
from core.outlook_client import get_outlook_client
from core.sync_engine import SyncEngine

from gui.triage_view import TriageView
from gui.rule_manager_view import RuleManagerView
from gui.rollover_view import RolloverView
from gui.dryrun_view import DryRunView


class MainWindow(tk.Tk):
    """Root Application Window."""

    def __init__(self, config_path: str):
        super().__init__()
        self.title("Outlook Rule Companion")
        self.geometry("1120x720")
        self.minsize(920, 620)

        # Initialize Core Layers
        self.yaml_mgr = YamlConfigManager(config_path)
        self.outlook = get_outlook_client()
        self.sync_engine = SyncEngine(self.yaml_mgr, self.outlook)

        self._apply_style()
        self._build_header()
        self._build_notebook()
        self._build_footer()

    def _apply_style(self):
        style = ttk.Style(self)
        available = style.theme_names()
        if "clam" in available:
            style.theme_use("clam")

        # Clean typography and padding
        style.configure("Accent.TButton", font=("", 9, "bold"))
        style.configure("Header.TLabel", font=("", 11, "bold"))

    def _build_header(self):
        header = ttk.Frame(self, padding=(12, 8))
        header.pack(fill=tk.X, side=tk.TOP)

        # Title & Status
        left_box = ttk.Frame(header)
        left_box.pack(side=tk.LEFT)

        ttk.Label(left_box, text="Outlook Rule Companion", style="Header.TLabel").pack(anchor=tk.W)

        mode_name = self.outlook.get_mode_name()
        mode_color = "#2e7d32" if "Classic" in mode_name else "#886600"
        self.lbl_mode = ttk.Label(left_box, text=f"Engine: {mode_name}", foreground=mode_color, font=("", 8))
        self.lbl_mode.pack(anchor=tk.W)

        # Quick Actions (Clean text labels, no broken emoji symbols)
        right_box = ttk.Frame(header)
        right_box.pack(side=tk.RIGHT)

        btn_reload = ttk.Button(right_box, text="Reload YAML", command=self._reload_yaml)
        btn_reload.pack(side=tk.LEFT, padx=4)

        btn_sync = ttk.Button(
            right_box,
            text="Sync to Outlook",
            style="Accent.TButton",
            command=self._sync_to_outlook
        )
        btn_sync.pack(side=tk.LEFT, padx=4)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X)

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Tab 1: Inbox Triage (Drag & Drop)
        self.tab_triage = TriageView(self.notebook, self.yaml_mgr, self.outlook, self.sync_engine)
        self.notebook.add(self.tab_triage, text=" Inbox Triage ")

        # Tab 2: Rules & Address Groups
        self.tab_rules = RuleManagerView(self.notebook, self.yaml_mgr, self.sync_engine)
        self.notebook.add(self.tab_rules, text=" Rules & Groups ")

        # Tab 3: PST Rollover
        self.tab_rollover = RolloverView(self.notebook, self.yaml_mgr, self.outlook, self.sync_engine)
        self.notebook.add(self.tab_rollover, text=" PST Rollover ")

        # Tab 4: Dry-Run Simulation
        self.tab_dryrun = DryRunView(self.notebook, self.yaml_mgr, self.outlook, self.sync_engine)
        self.notebook.add(self.tab_dryrun, text=" Dry-Run Simulation ")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _build_footer(self):
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X)
        footer = ttk.Frame(self, padding=(8, 4))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        active = self.yaml_mgr.stores.get("active_archive")
        store_txt = f"{active.name} ({active.file_path})" if active else "None"
        self.lbl_footer = ttk.Label(
            footer,
            text=f"Active Target Archive: {store_txt} | Config: rules.yaml",
            font=("", 8)
        )
        self.lbl_footer.pack(side=tk.LEFT)

    def _on_tab_change(self, event):
        current_idx = self.notebook.index("current")
        if current_idx == 0:
            self.tab_triage.refresh_inbox()
        elif current_idx == 1:
            self.tab_rules.refresh_all()
        elif current_idx == 2:
            self.tab_rollover.refresh_view()
        elif current_idx == 3:
            self.tab_dryrun.refresh_simulation()

    def _reload_yaml(self):
        self.yaml_mgr.load()
        self.tab_triage.refresh_inbox()
        self.tab_rules.refresh_all()
        self.tab_rollover.refresh_view()
        messagebox.showinfo("Reloaded", "Successfully reloaded configuration from rules.yaml.")

    def _sync_to_outlook(self):
        confirm = messagebox.askyesno(
            "Sync to Outlook",
            "This will apply all enabled rules and groups from rules.yaml directly into Outlook native rules.\n\n"
            "Proceed?",
            icon=messagebox.QUESTION
        )
        if not confirm:
            return

        success, msg = self.sync_engine.push_to_outlook()
        if success:
            messagebox.showinfo("Sync Success", msg)
        else:
            messagebox.showerror("Sync Failed", msg)
