"""Main Application Window for Outlook Rule Companion."""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Tuple

from core.yaml_manager import YamlConfigManager
from core.outlook_client import BaseOutlookClient, get_outlook_client
from core.sync_engine import SyncEngine
from core.models import pluralize_count

from gui import styles
from gui.triage_view import TriageView
from gui.rule_manager_view import RuleManagerView
from gui.rollover_view import RolloverView


class MainWindow(tk.Tk):
    """Root Application Window."""

    def __init__(self, config_path: str, outlook_client: Optional[BaseOutlookClient] = None):
        super().__init__()
        self.title("Outlook Rule Companion")
        self.geometry("1120x720")
        self.minsize(960, 620)

        # Initialize Core Layers
        self.yaml_mgr = YamlConfigManager(config_path)
        self.outlook = outlook_client if outlook_client is not None else get_outlook_client()
        self.sync_engine = SyncEngine(self.yaml_mgr, self.outlook)

        self._current_tab_index: int = 0
        self._restoring_tab: bool = False

        self._apply_style()
        self._build_header()
        self._build_simulation_banner()
        self._build_footer()
        self._build_notebook()

        self.yaml_mgr.add_change_listener(self._on_yaml_state_changed)
        self._update_simulation_banner()
        self._update_sync_status()
        self._refresh_footer()
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

    def _apply_style(self):
        styles.apply_styles(self)

    def _build_header(self):
        header = ttk.Frame(self, padding=(12, 4))
        header.pack(fill=tk.X, side=tk.TOP)

        # Title + engine/account on a single line
        left_box = ttk.Frame(header)
        left_box.pack(side=tk.LEFT)

        ttk.Label(left_box, text="Outlook Rule Companion", style="Header.TLabel").pack(side=tk.LEFT)

        self.lbl_mode = ttk.Label(left_box, text="", font=("", 8))
        self.lbl_mode.pack(side=tk.LEFT, padx=(10, 0))

        right_box = ttk.Frame(header)
        right_box.pack(side=tk.RIGHT)

        btn_reload = ttk.Button(right_box, text="Reload YAML", command=self._reload_yaml)
        btn_reload.pack(side=tk.LEFT, padx=3)

        self.btn_conflicts = ttk.Button(
            right_box,
            text="Check Rule Conflicts",
            command=self._open_conflict_inspector,
        )
        self.btn_conflicts.pack(side=tk.LEFT, padx=3)

        self.btn_rollover = ttk.Button(
            right_box,
            text="Yearly Rollover...",
            command=self._open_rollover_dialog,
        )
        self.btn_rollover.pack(side=tk.LEFT, padx=3)

        self.lbl_sync_status = ttk.Label(
            right_box,
            text="Not synced this session",
            foreground=styles.TEXT_MUTED,
            font=("", 8, "bold"),
        )
        self.lbl_sync_status.pack(side=tk.LEFT, padx=(8, 4))

        self.btn_sync = ttk.Button(
            right_box,
            text="Sync to Outlook",
            style="Accent.TButton",
            command=self._sync_to_outlook
        )
        self.btn_sync.pack(side=tk.LEFT, padx=3)

        self._header_sep = ttk.Separator(self, orient=tk.HORIZONTAL)
        self._header_sep.pack(fill=tk.X, side=tk.TOP)

    def _build_simulation_banner(self):
        # Single compact line: message on the left, Retry on the right
        self.sim_banner = tk.Frame(
            self,
            bg=styles.BANNER_BG,
            highlightbackground=styles.BANNER_BORDER,
            highlightthickness=1,
            padx=12,
            pady=2,
        )
        self.lbl_sim_banner = tk.Label(
            self.sim_banner,
            text="SIMULATION MODE — Outlook is not connected. Sync, Move and Rollover do NOT change Outlook.",
            bg=styles.BANNER_BG,
            fg=styles.BANNER_FG,
            font=("", 9, "bold"),
        )
        self.lbl_sim_banner.pack(side=tk.LEFT)

        self.btn_retry_conn = ttk.Button(
            self.sim_banner,
            text="Retry",
            style="Banner.TButton",
            command=self._retry_outlook_connection,
        )
        self.btn_retry_conn.pack(side=tk.RIGHT)

    def _update_simulation_banner(self):
        mode_name = self.outlook.get_mode_name()
        simulated = self.outlook.is_simulated()
        mode_color = styles.DANGER if simulated else styles.OK
        # Short label keeps the one-line header within the window width; full name in the footer
        self.lbl_mode.config(text="Simulated" if simulated else "Outlook Classic", foreground=mode_color)

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
            self.lbl_sync_status.config(
                text=f"● {pluralize_count(count, 'unsynced change')}", foreground=styles.WARN
            )
            self.btn_sync.config(style="SyncPending.TButton")
        elif self.yaml_mgr.has_synced:
            self.lbl_sync_status.config(text="✓ Outlook in sync", foreground=styles.OK)
            self.btn_sync.config(style="Accent.TButton")
        else:
            self.lbl_sync_status.config(text="Not synced this session", foreground=styles.TEXT_MUTED)
            self.btn_sync.config(style="Accent.TButton")

    def _on_yaml_state_changed(self):
        self._update_sync_status()
        self._refresh_footer()

    def _retry_outlook_connection(self):
        new_client = get_outlook_client()
        if not new_client.is_simulated() and new_client.is_connected():
            self.outlook = new_client
            self.sync_engine.outlook = new_client
            self.tab_triage.outlook = new_client
            self.tab_triage.conflict_detector.outlook = new_client

            self._update_simulation_banner()
            self._refresh_footer()
            self.tab_triage.refresh_inbox()
            messagebox.showinfo("Connected", f"Connected to {new_client.get_mode_name()}.")
        else:
            messagebox.showerror(
                "Connection Failed",
                "Could not connect to Outlook Classic. Make sure Outlook is installed and running.",
            )

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=(2, 2))

        # Tab 1: Inbox
        self.tab_triage = TriageView(self.notebook, self.yaml_mgr, self.outlook, self.sync_engine)
        self.notebook.add(self.tab_triage, text="Inbox")

        # Tab 2: Rules & Address Groups
        self.tab_rules = RuleManagerView(self.notebook, self.yaml_mgr, self.sync_engine)
        self.notebook.add(self.tab_rules, text="Rules")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _build_footer(self):
        self.footer = ttk.Frame(self, padding=(8, 2))
        self.footer.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_footer = ttk.Label(
            self.footer,
            text="",
            font=("", 8)
        )
        self.lbl_footer.pack(side=tk.LEFT)

        self.lbl_footer_status = ttk.Label(
            self.footer,
            text="",
            font=("", 8, "bold")
        )
        self.lbl_footer_status.pack(side=tk.LEFT)

        self.lbl_footer_cfg = ttk.Label(
            self.footer,
            text=" | Config: rules.yaml",
            font=("", 8)
        )
        self.lbl_footer_cfg.pack(side=tk.LEFT)
        self._refresh_footer()

    def _refresh_footer(self):
        if not self.winfo_exists():
            return
        active = self.yaml_mgr.stores.get("active_archive")
        if active:
            store_id = active.file_path or active.name
            exists = self.outlook.store_exists(store_id) if store_id else False
            prefix = f"Active archive: {active.name} ({active.file_path}) — "
        else:
            exists = False
            prefix = "Active archive: None — "

        try:
            account = self.outlook.get_current_user_account()
        except Exception:
            account = ""
        engine = f"{self.outlook.get_mode_name()}" + (f" ({account})" if account else "")
        self.lbl_footer.config(text=f"{engine} | {prefix}")
        if exists:
            self.lbl_footer_status.config(text="found in Outlook", foreground=styles.OK)
        else:
            self.lbl_footer_status.config(text="NOT found in Outlook", foreground=styles.DANGER)

    def _on_tab_change(self, event):
        if self._restoring_tab:
            return
        current_idx = self.notebook.index("current")
        if self._current_tab_index == 1 and current_idx != 1:
            if not self.tab_rules.confirm_pending_changes(reset_if_discard=True):
                self._restoring_tab = True
                try:
                    self.notebook.select(1)
                    self._current_tab_index = 1
                finally:
                    self.update_idletasks()
                    self._restoring_tab = False
                return

        self._current_tab_index = current_idx
        if current_idx == 0:
            self.tab_triage.refresh_inbox()
        elif current_idx == 1:
            self.tab_rules.refresh_all()

    def _open_conflict_inspector(self):
        if not self.tab_rules.confirm_pending_changes(reset_if_discard=True):
            return
        self.tab_triage._open_conflict_inspector()
        self.tab_rules.refresh_all()

    def _build_rollover_dialog(self) -> Tuple[tk.Toplevel, RolloverView]:
        """Construct the modal Yearly Rollover dialog using the current Outlook client."""
        dlg = tk.Toplevel(self)
        dlg.title("Yearly PST Rollover")
        dlg.geometry("920x580")
        dlg.minsize(780, 480)
        dlg.transient(self)
        dlg.grab_set()

        def _on_complete():
            if dlg.winfo_exists():
                dlg.destroy()
            self._refresh_footer()
            self._update_sync_status()

        # Close bar packed first so it always stays visible at the bottom
        close_bar = ttk.Frame(dlg, padding=(14, 0, 14, 10))
        close_bar.pack(fill=tk.X, side=tk.BOTTOM)
        dlg.btn_close = ttk.Button(close_bar, text="Close", command=dlg.destroy)
        dlg.btn_close.pack(side=tk.RIGHT)

        view = RolloverView(
            dlg,
            self.yaml_mgr,
            self.outlook,
            self.sync_engine,
            on_rollover_complete=_on_complete,
        )
        view.pack(fill=tk.BOTH, expand=True)
        return dlg, view

    def _open_rollover_dialog(self):
        if not self.tab_rules.confirm_pending_changes(reset_if_discard=True):
            return
        dlg, _view = self._build_rollover_dialog()
        self.wait_window(dlg)
        self._refresh_footer()
        self._update_sync_status()

    def _on_close_window(self):
        if not self.tab_rules.confirm_pending_changes(reset_if_discard=False):
            return
        self.destroy()

    def _reload_yaml(self):
        if not self.tab_rules.confirm_pending_changes(reset_if_discard=True):
            return
        self.yaml_mgr.load()
        self._refresh_footer()
        self.tab_triage.refresh_inbox()
        self.tab_rules.refresh_all()
        messagebox.showinfo("Reloaded", "Successfully reloaded configuration from rules.yaml.")

    def _sync_to_outlook(self):
        if not self.tab_rules.confirm_pending_changes(reset_if_discard=True):
            return
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
