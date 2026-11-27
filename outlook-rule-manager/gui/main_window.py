"""Main Application Window for Outlook Rule Companion."""
import os
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox, filedialog
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
        self.geometry("1280x760")
        self.minsize(1040, 620)

        # Initialize Core Layers
        self.yaml_mgr = YamlConfigManager(config_path)
        self.outlook = outlook_client if outlook_client is not None else get_outlook_client()
        self.sync_engine = SyncEngine(self.yaml_mgr, self.outlook)


        self._apply_style()
        self._build_header()
        self._build_simulation_banner()
        self._build_footer()
        self._build_workspace()

        self.yaml_mgr.add_change_listener(self._on_yaml_state_changed)
        self._update_simulation_banner()
        self._update_sync_status()
        self._refresh_footer()
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

        # Undo: Ctrl+Z anywhere (text boxes keep their own Ctrl+Z) + Undo buttons in the tabs
        self.tab_rules.on_undo_request = self.undo_last
        self.tab_triage.on_undo_request = self.undo_last
        self.bind_all("<Control-z>", self._on_ctrl_z, add="+")
        self.bind_all("<Control-Z>", self._on_ctrl_z, add="+")
        self._refresh_undo_buttons()

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

        # File: reload + share rules with colleagues (export / import)
        self.mb_file = ttk.Menubutton(right_box, text="File")
        self.menu_file = tk.Menu(self.mb_file, tearoff=0)
        self.menu_file.add_command(label="Export rules for sharing...", command=self._export_rules)
        self.menu_file.add_command(label="Import rules...", command=self._import_rules)
        self.menu_file.add_separator()
        self.menu_file.add_command(label="Reload rules.yaml", command=self._reload_yaml)
        self.mb_file.config(menu=self.menu_file)
        self.mb_file.pack(side=tk.LEFT, padx=3)

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
        self._refresh_undo_buttons()
        # Keep the "Will go to" column truthful after any rule change
        if hasattr(self, "tab_triage"):
            self.tab_triage._populate_inbox_table()

    def _refresh_undo_buttons(self):
        for tab in (getattr(self, "tab_rules", None), getattr(self, "tab_triage", None)):
            if tab is not None and hasattr(tab, "refresh_undo_button"):
                tab.refresh_undo_button()

    def _on_ctrl_z(self, event):
        # Let text/entry widgets handle their own undo
        if isinstance(event.widget, (tk.Text, tk.Entry, ttk.Entry, ttk.Combobox)):
            return None
        self.undo_last()
        return "break"

    def undo_last(self) -> Optional[str]:
        """Undo the last saved change to rules.yaml (rules, folders, groups, pool)."""
        if not self.yaml_mgr.can_undo():
            self.tab_rules._show_toast("Nothing to undo.")
            return None
        if not self.tab_rules.confirm_pending_changes(reset_if_discard=True):
            return None
        label = self.yaml_mgr.undo()
        self.tab_rules.reset_selection_after_undo()
        self.tab_rules.refresh_all()
        self.tab_triage.refresh_inbox()
        note = " (rules only — emails already moved in Outlook stay where they are)" if label.startswith("Apply") else ""
        message = f"Undone: {label}{note}"
        self.tab_rules._show_toast(message)
        if hasattr(self.tab_triage, "show_panel_status"):
            self.tab_triage.show_panel_status(message)
        self._refresh_undo_buttons()
        return label

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

    def _build_workspace(self):
        """Single screen: Rules navigator | Mail list | Details (mail reader OR rule/folder/group editor)."""
        self.workspace = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.workspace.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 0))

        self.nav_host = ttk.Frame(self.workspace)
        self.inbox_host = ttk.Frame(self.workspace)
        self.details_host = ttk.Frame(self.workspace)
        self.workspace.add(self.nav_host, weight=3)
        self.workspace.add(self.inbox_host, weight=4)
        self.workspace.add(self.details_host, weight=4)

        # The right pane stacks the mail reader and the rule inspector; one is shown at a time
        self.reader_host = ttk.Frame(self.details_host)
        self.inspector_host = ttk.Frame(self.details_host)
        self.bottom_host = ttk.Frame(self)
        self.bottom_host.pack(fill=tk.X, side=tk.BOTTOM, before=self.workspace)

        # The view objects stay hidden; their widgets live in the hosts above
        self.tab_triage = TriageView(
            self, self.yaml_mgr, self.outlook, self.sync_engine,
            inbox_host=self.inbox_host, reader_host=self.reader_host, bottom_host=self.bottom_host,
        )
        self.tab_rules = RuleManagerView(
            self, self.yaml_mgr, self.sync_engine,
            nav_host=self.nav_host, inspector_host=self.inspector_host,
        )

        # Mails are dropped straight onto the rules tree
        self.tab_triage.attach_drop_tree(self.tab_rules.tree, self.tab_rules.resolve_drop_iid)
        self.tab_triage.status_sink = lambda msg, error=False: self.tab_rules._show_toast(msg, error=error)
        self.tab_triage.on_message_activated = self.show_mail_details
        self.tab_triage.on_rules_changed = self.tab_rules.refresh_all
        self.tab_rules.on_item_activated = self.show_rule_details
        # Mails listed under their rule in the tree
        self.tab_rules.mail_provider = self.tab_triage.mails_by_rule
        self.tab_rules.pending_provider = self.tab_triage.pending_new_rules
        self.tab_rules.on_mail_selected = self._on_tree_mail_selected
        self.tab_rules.on_mail_dropped = self._on_tree_mail_dropped
        self.tab_triage.on_inbox_changed = self.tab_rules.refresh_mail_nodes
        self.tab_rules.refresh_mail_nodes()

        self.details_mode = ""
        self.show_mail_details()
        self._sashes_placed = False
        self.workspace.bind("<Configure>", self._place_sashes, add="+")

    def _on_tree_mail_selected(self, entry_id: str):
        if self.tab_triage.focus_message(entry_id):
            self.show_mail_details()

    def _on_tree_mail_dropped(self, entry_id: str, target_iid: str, whole_domain: bool = False):
        msgs = [m for m in self.tab_triage.messages if m.entry_id == entry_id]
        self.tab_triage.drop_messages_on_target(target_iid, msgs, whole_domain=whole_domain)

    def _place_sashes(self, event=None):
        """Initial split (once, when the window first gets its real size): 24% | 34% | 42%."""
        if self._sashes_placed:
            return
        width = self.workspace.winfo_width()
        if width < 600:
            return
        try:
            self.workspace.sashpos(0, int(width * 0.24))
            self.workspace.sashpos(1, int(width * 0.58))
            self._sashes_placed = True
        except tk.TclError:
            pass

    def show_mail_details(self):
        """Right pane: the selected mail (asks first if a rule/group form has unsaved edits)."""
        if self.details_mode == "mail":
            return
        if self.details_mode == "rule" and not self.tab_rules.confirm_pending_changes(reset_if_discard=True):
            return
        self.inspector_host.pack_forget()
        self.reader_host.pack(fill=tk.BOTH, expand=True)
        self.details_mode = "mail"

    def show_rule_details(self):
        """Right pane: the editor for the rule/folder/group selected in the navigator."""
        if self.details_mode == "rule":
            return
        self.reader_host.pack_forget()
        self.inspector_host.pack(fill=tk.BOTH, expand=True)
        self.details_mode = "rule"

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

    # --- sharing --------------------------------------------------------
    def _ask_export_path(self) -> str:
        return filedialog.asksaveasfilename(
            parent=self,
            title="Export rules for sharing",
            defaultextension=".yaml",
            initialfile=f"rules_shared_{datetime.now():%Y%m%d}.yaml",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
        )

    def _ask_import_path(self) -> str:
        return filedialog.askopenfilename(
            parent=self,
            title="Import rules",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
        )

    def _ask_import_mode(self, filename: str, preview: dict) -> str:
        """'merge' / 'replace' / '' (cancel)."""
        dlg = tk.Toplevel(self)
        dlg.title("Import rules")
        dlg.transient(self)
        dlg.resizable(False, False)
        choice = {"mode": ""}
        frm = ttk.Frame(dlg, padding=14)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frm,
            text=(f"'{filename}' has {pluralize_count(len(preview['rules']), 'rule')} and "
                  f"{pluralize_count(len(preview['groups']), 'group')}.\n\n"
                  "Merge: add its rules and senders to yours (same name + folder = merged).\n"
                  "Replace: your rules, groups and folders become exactly the file's.\n\n"
                  "Your PST paths are kept either way. Undo (Ctrl+Z) reverts the import."),
            justify=tk.LEFT,
        ).pack(anchor=tk.W)
        btns = ttk.Frame(frm)
        btns.pack(fill=tk.X, pady=(12, 0))

        def _pick(mode):
            choice["mode"] = mode
            dlg.destroy()

        ttk.Button(btns, text="Cancel", command=lambda: _pick("")).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Replace all", style="Danger.TButton", command=lambda: _pick("replace")).pack(
            side=tk.RIGHT, padx=(0, 6))
        ttk.Button(btns, text="Merge", style="Accent.TButton", command=lambda: _pick("merge")).pack(
            side=tk.RIGHT, padx=(0, 6))
        dlg.bind("<Escape>", lambda e: _pick(""))
        dlg.protocol("WM_DELETE_WINDOW", lambda: _pick(""))
        try:
            dlg.grab_set()
        except tk.TclError:
            pass
        self.wait_window(dlg)
        return choice["mode"]

    def _export_rules(self):
        if not self.tab_rules.confirm_pending_changes(reset_if_discard=True):
            return
        path = self._ask_export_path()
        if not path:
            return
        try:
            info = self.yaml_mgr.export_config(path)
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)
            return
        self.tab_rules._show_toast(
            f"Exported {pluralize_count(info['rules'], 'rule')} to '{os.path.basename(path)}' "
            "(PST paths left out)."
        )

    def _import_rules(self):
        if not self.tab_rules.confirm_pending_changes(reset_if_discard=True):
            return
        path = self._ask_import_path()
        if not path:
            return
        try:
            preview = self.yaml_mgr.read_shared_file(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Import failed", str(exc), parent=self)
            return
        mode = self._ask_import_mode(os.path.basename(path), preview)
        if not mode:
            return
        summary = self.yaml_mgr.import_config(path, mode=mode)
        self.tab_rules.reset_selection_after_undo()
        self.tab_rules.refresh_all()
        self.tab_triage.refresh_inbox()
        text = (f"Imported ({mode}): {summary['rules_added']} rules added, "
                f"{summary['rules_merged']} merged.")
        if summary["duplicate_senders"]:
            text += f" {pluralize_count(summary['duplicate_senders'], 'sender')} in more than one rule - see Check Rule Conflicts."
        self.tab_rules._show_toast(text, error=bool(summary["duplicate_senders"]))

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
