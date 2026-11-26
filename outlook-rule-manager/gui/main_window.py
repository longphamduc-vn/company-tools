"""Main Application Window for Outlook Rule Companion."""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from core.yaml_manager import YamlConfigManager
from core.outlook_client import BaseOutlookClient, get_outlook_client
from core.sync_engine import SyncEngine

from gui.triage_view import TriageView
from gui.rule_manager_view import RuleManagerView
from gui.rollover_view import RolloverView
from gui.dryrun_view import DryRunView


class MainWindow(tk.Tk):
    """Root Application Window."""

    def __init__(self, config_path: str, outlook_client: Optional[BaseOutlookClient] = None):
        super().__init__()
        self.title("Outlook Rule Companion")
        self.geometry("1120x720")
        self.minsize(920, 620)

        # Initialize Core Layers
        self.yaml_mgr = YamlConfigManager(config_path)
        self.outlook = outlook_client if outlook_client is not None else get_outlook_client()
        self.sync_engine = SyncEngine(self.yaml_mgr, self.outlook)

        self._apply_style()
        self._build_header()
        self._build_simulation_banner()
        self._build_notebook()
        self._build_footer()

        self.yaml_mgr.add_change_listener(self._update_sync_status)
        self._update_simulation_banner()
        self._update_sync_status()

    def _apply_style(self):
        style = ttk.Style(self)
        available = style.theme_names()
        if "clam" in available:
            style.theme_use("clam")

        # Clean typography and padding
        style.configure("Accent.TButton", font=("", 9, "bold"))
        style.configure(
            "SyncPending.TButton",
            font=("", 9, "bold"),
            background="#0284c7",
            foreground="#ffffff",
        )
        style.map(
            "SyncPending.TButton",
            background=[("active", "#0369a1")],
            foreground=[("active", "#ffffff")],
        )
        style.configure("Header.TLabel", font=("", 11, "bold"))

    def _build_header(self):
        header = ttk.Frame(self, padding=(12, 8))
        header.pack(fill=tk.X, side=tk.TOP)

        # Title & Status
        left_box = ttk.Frame(header)
        left_box.pack(side=tk.LEFT)

        ttk.Label(left_box, text="Outlook Rule Companion", style="Header.TLabel").pack(anchor=tk.W)

        mode_name = self.outlook.get_mode_name()
        mode_color = "#b91c1c" if self.outlook.is_simulated() else "#2e7d32"
        self.lbl_mode = ttk.Label(left_box, text=f"Engine: {mode_name}", foreground=mode_color, font=("", 8))
        self.lbl_mode.pack(anchor=tk.W)

        # Quick Actions (Clean text labels, no broken emoji symbols)
        right_box = ttk.Frame(header)
        right_box.pack(side=tk.RIGHT)

        btn_reload = ttk.Button(right_box, text="Reload YAML", command=self._reload_yaml)
        btn_reload.pack(side=tk.LEFT, padx=4)

        self.lbl_sync_status = ttk.Label(
            right_box,
            text="Not synced this session",
            foreground="#64748b",
            font=("", 8, "bold"),
        )
        self.lbl_sync_status.pack(side=tk.LEFT, padx=(8, 4))

        self.btn_sync = ttk.Button(
            right_box,
            text="Sync to Outlook",
            style="Accent.TButton",
            command=self._sync_to_outlook
        )
        self.btn_sync.pack(side=tk.LEFT, padx=4)

        self._header_sep = ttk.Separator(self, orient=tk.HORIZONTAL)
        self._header_sep.pack(fill=tk.X, side=tk.TOP)

    def _build_simulation_banner(self):
        self.sim_banner = tk.Frame(
            self,
            bg="#fee2e2",
            highlightbackground="#fca5a5",
            highlightthickness=1,
            padx=12,
            pady=6,
        )
        self.lbl_sim_banner = tk.Label(
            self.sim_banner,
            text="SIMULATION MODE — Outlook is not connected. Sync, Move and Rollover do NOT change Outlook.",
            bg="#fee2e2",
            fg="#991b1b",
            font=("", 9, "bold"),
        )
        self.lbl_sim_banner.pack(side=tk.LEFT)

        self.btn_retry_conn = ttk.Button(
            self.sim_banner,
            text="Retry Connection",
            command=self._retry_outlook_connection,
        )
        self.btn_retry_conn.pack(side=tk.RIGHT)

    def _update_simulation_banner(self):
        mode_name = self.outlook.get_mode_name()
        simulated = self.outlook.is_simulated()
        mode_color = "#b91c1c" if simulated else "#2e7d32"
        self.lbl_mode.config(text=f"Engine: {mode_name}", foreground=mode_color)

        if simulated:
            self.btn_sync.config(text="Sync (Simulated)")
            if not self.sim_banner.winfo_manager():
                self.sim_banner.pack(fill=tk.X, side=tk.TOP, after=self._header_sep)
        else:
            self.btn_sync.config(text="Sync to Outlook")
            if self.sim_banner.winfo_manager():
                self.sim_banner.pack_forget()

    def _update_sync_status(self):
        if not self.winfo_exists():
            return
        count = self.yaml_mgr.unsynced_changes
        if count > 0:
            self.lbl_sync_status.config(text=f"● {count} unsynced change(s)", foreground="#ea580c")
            self.btn_sync.config(style="SyncPending.TButton")
        elif self.yaml_mgr.has_synced:
            self.lbl_sync_status.config(text="✓ Outlook in sync", foreground="#16a34a")
            self.btn_sync.config(style="Accent.TButton")
        else:
            self.lbl_sync_status.config(text="Not synced this session", foreground="#64748b")
            self.btn_sync.config(style="Accent.TButton")

    def _retry_outlook_connection(self):
        new_client = get_outlook_client()
        if not new_client.is_simulated() and new_client.is_connected():
            self.outlook = new_client
            self.sync_engine.outlook = new_client
            self.tab_triage.outlook = new_client
            self.tab_triage.conflict_detector.outlook = new_client
            self.tab_rollover.outlook = new_client
            self.tab_dryrun.outlook = new_client

            self._update_simulation_banner()
            self.tab_triage.refresh_inbox()
            self.tab_rollover.lbl_acc_badge.config(
                text=f"Active Account: {new_client.get_current_user_account()}"
            )
            self.tab_rollover.refresh_view()
            self.tab_dryrun.refresh_simulation()
            messagebox.showinfo("Connected", f"Connected to {new_client.get_mode_name()}.")
        else:
            messagebox.showerror(
                "Connection Failed",
                "Could not connect to Outlook Classic. Make sure Outlook is installed and running.",
            )

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
            "This will apply all rules and groups from rules.yaml directly into Outlook native rules.\n\n"
            "Proceed?",
            icon=messagebox.QUESTION
        )
        if not confirm:
            return

        remove_legacy = False
        legacy_rules = self.sync_engine.find_legacy_rules()
        if legacy_rules:
            listed = "\n".join(f"• {name}" for name in legacy_rules)
            remove_legacy = messagebox.askyesno(
                "Legacy Outlook Rules Found",
                "The following legacy Outlook rules (without [Companion] prefix) match rules in rules.yaml:\n\n"
                f"{listed}\n\n"
                "Do you want to remove these legacy rules after syncing?",
                icon=messagebox.QUESTION
            )

        success, msg = self.sync_engine.push_to_outlook(remove_legacy=remove_legacy)
        if success:
            if self.outlook.is_simulated():
                msg = f"[SIMULATION] No changes were made to Outlook.\n\n{msg}"
            messagebox.showinfo("Sync Success", msg)
        else:
            messagebox.showerror("Sync Failed", msg)
