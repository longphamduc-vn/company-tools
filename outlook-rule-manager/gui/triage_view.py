"""Triage Workspace: High-Performance Multi-Pane with Full Email Inspector & Fast Staging."""
import tkinter as tk
from tkinter import ttk, messagebox
import re
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass

from core.models import EmailMessage, RuleConfig, pluralize_count
from core.yaml_manager import YamlConfigManager
from core.outlook_client import BaseOutlookClient
from core.sync_engine import SyncEngine
from core.conflict_detector import ConflictDetector
from gui.conflict_dialog import ConflictDialog


def suggest_rule_and_folder(sender_name: str, sender_email: str) -> Tuple[str, str]:
    r"""Smartly suggest rule name and hierarchical Team\Part\Unit folder."""
    generic_domains = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "company.com", "mail.com"}
    domain = sender_email.split("@")[1].lower() if "@" in sender_email else ""

    # Corporate domain (e.g. omron.com -> Omron, sato-automation.jp -> Sato Automation)
    if domain and domain not in generic_domains:
        core_domain = domain.split(".")[0]
        clean_domain = core_domain.replace("-", " ").replace("_", " ").title()
        folder_unit = clean_domain.replace(" ", "_")
        folder_path = f"Vendor_Team\\Suppliers_Part\\{folder_unit}_Unit"
        return clean_domain, folder_path

    # Sender display name
    if sender_name:
        clean_name = re.sub(r'[\(\[\{].*?[\)\]\}]', '', sender_name).strip()
        if clean_name:
            clean_name = clean_name.title()
            folder_unit = clean_name.replace(" ", "_")
            if "scada" in sender_name.lower() or "plc" in sender_name.lower():
                folder_path = f"Engineering_Team\\SCADA_Part\\{folder_unit}"
            else:
                folder_path = f"Internal_Team\\Members_Part\\{folder_unit}"
            return clean_name, folder_path

    # Fallback to local part of email
    local = sender_email.split("@")[0].replace(".", " ").replace("_", " ").title()
    folder_path = f"General_Team\\Inbox_Part\\{local.replace(' ', '_')}"
    return local, folder_path


@dataclass
class StagedAction:
    """Represents a queued rule action pending user batch confirmation."""
    action_type: str            # 'create_rule' or 'add_to_rule'
    rule_name: str
    rule_id: str
    target_folder: str
    sender_email: str
    sender_domain: str
    match_mode: str             # 'email' or 'domain'
    message_id: str
    subject: str


class TriageView(ttk.Frame):
    """High-Performance Workspace: Instant Click Response, Spacious Email Inspector & Conflict Resolver."""

    def __init__(self, parent, yaml_mgr: YamlConfigManager, outlook: BaseOutlookClient, sync_engine: SyncEngine):
        super().__init__(parent)
        self.yaml_mgr = yaml_mgr
        self.outlook = outlook
        self.sync_engine = sync_engine
        self.conflict_detector = ConflictDetector(self.yaml_mgr, self.outlook)

        self.messages: List[EmailMessage] = []
        self.selected_message: Optional[EmailMessage] = None
        self.staged_actions: List[StagedAction] = []
        self.active_filter: str = "ALL"
        self.search_query: str = ""

        self._build_ui()
        self.refresh_inbox()

    def _build_ui(self):
        # -------------------------------------------------------------
        # TOP APP HEADER STRIP
        # -------------------------------------------------------------
        top_bar = tk.Frame(self, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=12, pady=6)
        top_bar.pack(fill=tk.X, side=tk.TOP)

        btn_refresh = ttk.Button(top_bar, text="Refresh Inbox", command=self.refresh_inbox)
        btn_refresh.pack(side=tk.LEFT, padx=(0, 6))

        account_name = self.outlook.get_current_user_account()
        self.lbl_account = tk.Label(
            top_bar,
            text=f"Account: {account_name}",
            bg="#ffffff",
            fg="#0284c7",
            font=("", 9, "bold")
        )
        self.lbl_account.pack(side=tk.RIGHT, padx=6)

        # -------------------------------------------------------------
        # MAIN 2-PANE LAYOUT: INBOX LIST (LEFT) | READING & ACTIONS (RIGHT)
        # -------------------------------------------------------------
        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        # =============================================================
        # PANE 1 (LEFT, WIDE): INBOX LIST WITH "WILL GO TO" COLUMN
        # =============================================================
        self.frame_left = tk.Frame(self.paned, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=6, pady=6)
        self.paned.add(self.frame_left, weight=6)

        # Filter Strip
        filter_strip = tk.Frame(self.frame_left, bg="#f8fafc")
        filter_strip.pack(fill=tk.X, pady=(0, 4))

        self.btn_f_all = tk.Button(
            filter_strip, text="All", relief="flat", bg="#0284c7", fg="#ffffff",
            font=("", 8, "bold"), padx=6, pady=1, command=lambda: self._set_filter("ALL")
        )
        self.btn_f_all.pack(side=tk.LEFT, padx=1)

        self.btn_f_untracked = tk.Button(
            filter_strip, text="Needs Rule", relief="flat", bg="#e2e8f0", fg="#334155",
            font=("", 8, "bold"), padx=6, pady=1, command=lambda: self._set_filter("UNTRACKED")
        )
        self.btn_f_untracked.pack(side=tk.LEFT, padx=1)

        self.btn_f_staged = tk.Button(
            filter_strip, text="Staged", relief="flat", bg="#e2e8f0", fg="#334155",
            font=("", 8, "bold"), padx=6, pady=1, command=lambda: self._set_filter("STAGED")
        )
        self.btn_f_staged.pack(side=tk.LEFT, padx=1)

        # Dedicated Search row so "Search:" label & input remain clearly visible
        search_strip = tk.Frame(self.frame_left, bg="#f8fafc")
        search_strip.pack(fill=tk.X, pady=(0, 6))
        tk.Label(search_strip, text="Search:", bg="#f8fafc", fg="#475569", font=("", 8, "bold")).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        self.ent_search = ttk.Entry(search_strip, width=20)
        self.ent_search.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ent_search.bind("<KeyRelease>", lambda e: self._on_search_change())

        inbox_container = ttk.Frame(self.frame_left)
        inbox_container.pack(fill=tk.BOTH, expand=True)

        cols = ("Sender", "Subject", "WillGoTo")
        self.tree_inbox = ttk.Treeview(inbox_container, columns=cols, show="headings", selectmode="browse")
        self.tree_inbox.heading("Sender", text="From")
        self.tree_inbox.heading("Subject", text="Subject")
        self.tree_inbox.heading("WillGoTo", text="Will go to")

        self.tree_inbox.column("Sender", width=140, minwidth=85, stretch=True)
        self.tree_inbox.column("Subject", width=190, minwidth=110, stretch=True)
        self.tree_inbox.column("WillGoTo", width=135, minwidth=90, stretch=True)

        inbox_scroll = ttk.Scrollbar(inbox_container, orient=tk.VERTICAL, command=self.tree_inbox.yview)
        self.tree_inbox.configure(yscrollcommand=inbox_scroll.set)
        self.tree_inbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inbox_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree_inbox.bind("<<TreeviewSelect>>", self._on_message_select_fast)

        # Context Menu (mirrors inspector actions)
        self.menu_inbox = tk.Menu(self, tearoff=0)
        self.menu_inbox.add_command(label="Add to Rule...", command=self._menu_add_to_rule)
        self.menu_inbox.add_command(label="New Rule...", command=self._menu_stage_new_rule)
        self.menu_inbox.add_separator()
        self.menu_inbox.add_command(label="Move Now", command=self._move_selected_now)
        self.tree_inbox.bind("<Button-3>", self._on_inbox_right_click)

        # =============================================================
        # PANE 2 (RIGHT): EMAIL INSPECTOR & ACTIONS
        # =============================================================
        self.frame_right = tk.Frame(self.paned, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1, padx=12, pady=10)
        self.paned.add(self.frame_right, weight=4)

        # Top Header of Inspector
        top_meta = tk.Frame(self.frame_right, bg="#ffffff")
        top_meta.pack(fill=tk.X, pady=(0, 6))

        self.lbl_inspector_sender = tk.Label(
            top_meta,
            text="Select an email to view full content",
            bg="#ffffff",
            fg="#0f172a",
            font=("", 11, "bold"),
            anchor=tk.W
        )
        self.lbl_inspector_sender.pack(fill=tk.X)

        self.lbl_inspector_email = tk.Label(
            top_meta,
            text="",
            bg="#ffffff",
            fg="#0284c7",
            font=("", 9),
            anchor=tk.W
        )
        self.lbl_inspector_email.pack(fill=tk.X)

        self.lbl_inspector_date = tk.Label(
            top_meta,
            text="",
            bg="#ffffff",
            fg="#64748b",
            font=("", 8),
            anchor=tk.W
        )
        self.lbl_inspector_date.pack(fill=tk.X, pady=(2, 0))

        # Subject Banner
        self.lbl_inspector_subject = tk.Label(
            self.frame_right,
            text="",
            bg="#f8fafc",
            fg="#1e293b",
            font=("", 10, "bold"),
            anchor=tk.W,
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=6,
            wraplength=380,
            justify=tk.LEFT
        )
        self.lbl_inspector_subject.pack(fill=tk.X, pady=(4, 6))

        # Single-flow Action Strip
        action_bar = tk.Frame(self.frame_right, bg="#ffffff")
        action_bar.pack(fill=tk.X, pady=(0, 6))

        self.btn_add_to_rule = ttk.Button(
            action_bar,
            text="Add to Rule...",
            command=self._menu_add_to_rule,
        )
        self.btn_add_to_rule.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_new_rule = ttk.Button(
            action_bar,
            text="New Rule...",
            command=self._menu_stage_new_rule,
        )
        self.btn_new_rule.pack(side=tk.LEFT, padx=4)

        self.btn_move_now = ttk.Button(
            action_bar,
            text="Move Now",
            command=self._move_selected_now,
        )
        self.btn_move_now.pack(side=tk.LEFT, padx=4)

        # Full Spacious Text Body Reader
        tk.Label(self.frame_right, text="Email Content:", bg="#ffffff", fg="#475569", font=("", 9, "bold")).pack(anchor=tk.W, pady=(4, 2))

        body_container = tk.Frame(self.frame_right, bg="#ffffff")
        body_container.pack(fill=tk.BOTH, expand=True)

        self.txt_inspector_body = tk.Text(
            body_container,
            wrap=tk.WORD,
            font=("Segoe UI", 10),
            bg="#f8fafc",
            fg="#0f172a",
            padx=10,
            pady=10,
            relief="solid",
            borderwidth=1
        )
        body_scroll = ttk.Scrollbar(body_container, orient=tk.VERTICAL, command=self.txt_inspector_body.yview)
        self.txt_inspector_body.configure(yscrollcommand=body_scroll.set)
        self.txt_inspector_body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        body_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # =============================================================
        # SLIM PENDING STAGED BAR (SHOWN ONLY WHEN N > 0)
        # =============================================================
        self.pending_bar = tk.Frame(
            self,
            bg="#eff6ff",
            highlightbackground="#bfdbfe",
            highlightthickness=1,
            padx=10,
            pady=4,
        )

        self.lbl_pending_status = tk.Label(
            self.pending_bar,
            text="",
            bg="#eff6ff",
            fg="#1e3a8a",
            font=("", 9, "bold"),
        )
        self.lbl_pending_status.pack(side=tk.LEFT)

        pending_right = tk.Frame(self.pending_bar, bg="#eff6ff")
        pending_right.pack(side=tk.RIGHT)

        self.btn_pending_review = ttk.Button(
            pending_right, text="Review", command=self._open_review_staged_dialog
        )
        self.btn_pending_review.pack(side=tk.LEFT, padx=2)

        self.btn_pending_clear = ttk.Button(
            pending_right, text="Clear", command=self._clear_all_staged
        )
        self.btn_pending_clear.pack(side=tk.LEFT, padx=2)

        self.btn_pending_apply = ttk.Button(
            pending_right, text="Apply", style="Accent.TButton", command=self._apply_all_staged
        )
        self.btn_pending_apply.pack(side=tk.LEFT, padx=(4, 0))

    # -----------------------------------------------------------------
    # INSTANT SELECTION (0ms DELAY) & SPACIOUS INSPECTOR
    # -----------------------------------------------------------------
    def _on_message_select_fast(self, event):
        sel = self.tree_inbox.selection()
        if not sel:
            return
        entry_id = sel[0]
        self.selected_message = next((m for m in self.messages if m.entry_id == entry_id), None)
        if not self.selected_message:
            return

        m = self.selected_message

        # Instant Inspector update (<5ms)
        self.lbl_inspector_sender.config(text=m.sender_name if m.sender_name else m.sender_email)
        self.lbl_inspector_email.config(text=f"SMTP: {m.sender_email}")
        self.lbl_inspector_date.config(text=f"Received: {m.received_time.strftime('%A, %d %B %Y %H:%M:%S')}")
        self.lbl_inspector_subject.config(text=f"Subject: {m.subject}")

        self.txt_inspector_body.config(state=tk.NORMAL)
        self.txt_inspector_body.delete("1.0", tk.END)
        self.txt_inspector_body.insert(tk.END, m.body if m.body else "(Empty email content)")
        self.txt_inspector_body.config(state=tk.DISABLED)

    # -----------------------------------------------------------------
    # FILTER & SEARCH
    # -----------------------------------------------------------------
    def _set_filter(self, filter_name: str):
        self.active_filter = filter_name
        for name, btn in [("ALL", self.btn_f_all), ("UNTRACKED", self.btn_f_untracked), ("STAGED", self.btn_f_staged)]:
            if name == filter_name:
                btn.config(bg="#0284c7", fg="#ffffff")
            else:
                btn.config(bg="#e2e8f0", fg="#334155")
        self._populate_inbox_table()

    def _on_search_change(self):
        self.search_query = self.ent_search.get().strip().lower()
        self._populate_inbox_table()

    # -----------------------------------------------------------------
    # DATA REFRESH & POPULATION
    # -----------------------------------------------------------------
    def refresh_inbox(self):
        self.messages = self.outlook.get_inbox_messages(limit=50)
        self._populate_inbox_table()
        self._update_pending_bar()

    def _populate_inbox_table(self):
        """High-performance virtual rendering for Inbox items (<2ms)."""
        self.tree_inbox.delete(*self.tree_inbox.get_children())
        staged_map = {a.message_id: a for a in self.staged_actions}

        untracked_count = 0
        staged_count = 0

        for msg in self.messages:
            is_staged = msg.entry_id in staged_map
            matched_rule, _ = self.sync_engine.match_message(msg.sender_email, msg.subject)
            is_untracked = (not is_staged) and (matched_rule is None)

            if is_untracked:
                untracked_count += 1
            if is_staged:
                staged_count += 1

            # Filter Search
            if self.search_query:
                q = self.search_query
                in_sender = q in msg.sender_name.lower() or q in msg.sender_email.lower()
                in_subj = q in msg.subject.lower()
                if not (in_sender or in_subj):
                    continue

            # Filter Category
            if self.active_filter == "UNTRACKED" and not is_untracked:
                continue
            if self.active_filter == "STAGED" and not is_staged:
                continue

            # "Will go to" destination preview
            if is_staged:
                action = staged_map[msg.entry_id]
                will_go_to = f"* {action.target_folder or 'Inbox'}"
            elif matched_rule:
                will_go_to = matched_rule.target_folder or "Inbox (no rule)"
            else:
                will_go_to = "Inbox (no rule)"

            sender_disp = f"{msg.sender_name} <{msg.sender_email}>" if msg.sender_name else msg.sender_email

            self.tree_inbox.insert(
                "", tk.END, iid=msg.entry_id,
                values=(sender_disp, msg.subject, will_go_to)
            )

        # Update Filter Buttons
        self.btn_f_all.config(text=f"All ({len(self.messages)})")
        self.btn_f_untracked.config(text=f"Needs Rule ({untracked_count})")
        self.btn_f_staged.config(text=f"Staged ({staged_count})")

        # Select first message automatically if nothing is selected
        children = self.tree_inbox.get_children()
        if children and not self.tree_inbox.selection():
            self.tree_inbox.selection_set(children[0])
            self._on_message_select_fast(None)

    # -----------------------------------------------------------------
    # STAGING ENGINE & RULE SELECTION DIALOGS
    # -----------------------------------------------------------------
    def _stage_create_new_rule(self, msg: EmailMessage, custom_folder: Optional[str] = None):
        suggested_name, suggested_folder = suggest_rule_and_folder(msg.sender_name, msg.sender_email)
        target_folder = custom_folder if custom_folder else suggested_folder

        sender_email = msg.sender_email
        sender_domain = f"@{sender_email.split('@')[1]}" if "@" in sender_email else ""
        match_mode = "email"

        for existing in self.staged_actions:
            if existing.message_id == msg.entry_id:
                self.staged_actions.remove(existing)
                break

        action = StagedAction(
            action_type="create_rule",
            rule_name=suggested_name,
            rule_id="",
            target_folder=target_folder,
            sender_email=sender_email,
            sender_domain=sender_domain,
            match_mode=match_mode,
            message_id=msg.entry_id,
            subject=msg.subject
        )
        self.staged_actions.append(action)

        self._populate_inbox_table()
        self._update_pending_bar()

    def _stage_add_to_existing_rule(self, msg: EmailMessage, rule_id: str, match_mode: str = "email"):
        rule = next((r for r in self.yaml_mgr.rules if r.id == rule_id), None)
        if not rule:
            return

        sender_email = msg.sender_email
        sender_domain = f"@{sender_email.split('@')[1]}" if "@" in sender_email else ""

        for existing in self.staged_actions:
            if existing.message_id == msg.entry_id:
                self.staged_actions.remove(existing)
                break

        action = StagedAction(
            action_type="add_to_rule",
            rule_name=rule.name,
            rule_id=rule.id,
            target_folder=rule.target_folder,
            sender_email=sender_email,
            sender_domain=sender_domain,
            match_mode=match_mode,
            message_id=msg.entry_id,
            subject=msg.subject
        )
        self.staged_actions.append(action)

        self._populate_inbox_table()
        self._update_pending_bar()

    def _build_rule_picker_dialog(
        self,
        msg: EmailMessage,
        allow_scope: bool = True,
        title: str = "Add Sender to Rule",
        confirm_text: str = "OK",
    ):
        """Construct the rule picker Toplevel dialog and return (dlg, controls, read_result)."""
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.geometry("460x420" if allow_scope else "460x350")
        dlg.minsize(400, 320)
        dlg.transient(self)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frm,
            text=f"From: {msg.sender_name} <{msg.sender_email}>",
            font=("", 9, "bold"),
        ).pack(anchor=tk.W, pady=(0, 6))

        filter_row = ttk.Frame(frm)
        filter_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(filter_row, text="Filter:").pack(side=tk.LEFT, padx=(0, 4))
        var_filter = tk.StringVar()
        ent_filter = ttk.Entry(filter_row, textvariable=var_filter)
        ent_filter.pack(side=tk.LEFT, fill=tk.X, expand=True)

        list_wrap = ttk.Frame(frm)
        list_wrap.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        lst_rules = tk.Listbox(list_wrap, font=("Consolas", 9), exportselection=False)
        scroll = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL, command=lst_rules.yview)
        lst_rules.configure(yscrollcommand=scroll.set)
        lst_rules.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        filtered_rules: List[RuleConfig] = []

        def _populate_rules(*_args):
            q = var_filter.get().strip().lower()
            lst_rules.delete(0, tk.END)
            filtered_rules.clear()
            for r in self.yaml_mgr.rules:
                folder_txt = r.target_folder or "Root"
                if q and (q not in r.name.lower() and q not in folder_txt.lower()):
                    continue
                filtered_rules.append(r)
                lst_rules.insert(tk.END, f"{r.name}  ({folder_txt})")
            if filtered_rules:
                lst_rules.selection_set(0)

        var_filter.trace_add("write", _populate_rules)
        _populate_rules()

        var_scope = tk.StringVar(value="email")
        sender_domain = f"@{msg.sender_email.split('@', 1)[1]}" if "@" in msg.sender_email else ""
        if allow_scope:
            box_scope = ttk.LabelFrame(frm, text="Match Scope", padding=8)
            box_scope.pack(fill=tk.X, pady=(0, 8))
            ttk.Radiobutton(
                box_scope,
                text=f"This sender ({msg.sender_email})",
                variable=var_scope,
                value="email",
            ).pack(anchor=tk.W, pady=1)
            if sender_domain:
                ttk.Radiobutton(
                    box_scope,
                    text=f"Whole domain ({sender_domain})",
                    variable=var_scope,
                    value="domain",
                ).pack(anchor=tk.W, pady=1)

        chosen: Dict[str, Any] = {"result": None}

        def _on_ok():
            sel = lst_rules.curselection()
            if not sel:
                messagebox.showwarning("Notice", "Select a rule from the list.", parent=dlg)
                return
            chosen["result"] = (filtered_rules[sel[0]], var_scope.get())
            dlg.destroy()

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X, side=tk.BOTTOM)
        btn_ok = ttk.Button(btn_row, text=confirm_text, style="Accent.TButton", command=_on_ok)
        btn_ok.pack(side=tk.RIGHT, padx=(4, 0))
        btn_cancel = ttk.Button(btn_row, text="Cancel", command=dlg.destroy)
        btn_cancel.pack(side=tk.RIGHT, padx=4)

        lst_rules.bind("<Double-Button-1>", lambda _e: _on_ok())
        ent_filter.focus_set()

        controls = {
            "filter_var": var_filter,
            "filter_entry": ent_filter,
            "listbox": lst_rules,
            "filtered_rules": filtered_rules,
            "scope_var": var_scope,
            "ok_button": btn_ok,
            "cancel_button": btn_cancel,
        }
        return dlg, controls, lambda: chosen["result"]

    def _prompt_rule_selection(
        self,
        msg: EmailMessage,
        allow_scope: bool = True,
        title: str = "Add Sender to Rule",
        confirm_text: str = "OK",
    ) -> Optional[Tuple[RuleConfig, str]]:
        """Open modal rule selection dialog and return (RuleConfig, match_mode) or None."""
        dlg, _controls, get_result = self._build_rule_picker_dialog(
            msg, allow_scope=allow_scope, title=title, confirm_text=confirm_text
        )
        self.wait_window(dlg)
        return get_result()

    def _menu_add_to_rule(self):
        if not self.selected_message:
            messagebox.showwarning("Notice", "Select an email message first.")
            return
        if not self.yaml_mgr.rules:
            messagebox.showwarning("Notice", "No rules available. Create a rule first.")
            return
        choice = self._prompt_rule_selection(
            self.selected_message,
            allow_scope=True,
            title="Add to Rule",
            confirm_text="Add to Queue",
        )
        if not choice:
            return
        rule, match_mode = choice
        self._stage_add_to_existing_rule(self.selected_message, rule.id, match_mode=match_mode)

    def _menu_stage_new_rule(self):
        if not self.selected_message:
            messagebox.showwarning("Notice", "Select an email message first.")
            return
        self._open_create_hierarchical_rule_dialog(self.selected_message)

    def _open_create_hierarchical_rule_dialog(self, msg: EmailMessage):
        r"""Open modal dialog to configure Team \ Part \ Unit hierarchy for new rule."""
        suggested_name, suggested_folder = suggest_rule_and_folder(msg.sender_name, msg.sender_email)
        sender_email = msg.sender_email
        sender_domain = f"@{sender_email.split('@')[1]}" if "@" in sender_email else ""

        # Parse suggested segments
        segs = [s.strip() for s in re.split(r'[\\/]', suggested_folder) if s.strip()]
        sug_team = segs[0] if len(segs) >= 1 else "Engineering_Team"
        sug_part = segs[1] if len(segs) >= 2 else "General_Part"
        sug_unit = segs[2] if len(segs) >= 3 else f"{suggested_name.replace(' ', '_')}_Unit"

        dlg = tk.Toplevel(self)
        dlg.title("Create Hierarchical Rule (Team \\ Part \\ Unit)")
        dlg.geometry("520x460")
        dlg.minsize(480, 420)
        dlg.transient(self)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=16)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Create Rule (Team \\ Part \\ Unit)", font=("", 12, "bold"), foreground="#15803d").pack(anchor=tk.W, pady=(0, 4))
        ttk.Label(frm, text=f"Source: {msg.sender_name} <{sender_email}>", font=("", 9, "bold")).pack(anchor=tk.W, pady=(0, 8))

        # Form
        box_form = ttk.LabelFrame(frm, text="Rule & Folder Hierarchy", padding=10)
        box_form.pack(fill=tk.X, pady=(0, 8))

        grid = ttk.Frame(box_form)
        grid.pack(fill=tk.X)

        ttk.Label(grid, text="Rule Name:").grid(row=0, column=0, sticky=tk.W, pady=3)
        ent_name = ttk.Entry(grid, width=32)
        ent_name.grid(row=0, column=1, sticky=tk.EW, padx=6, pady=3)
        ent_name.insert(0, suggested_name)

        teams, parts, units = self.yaml_mgr.get_existing_hierarchy()

        ttk.Label(grid, text="Team (Level 1):").grid(row=1, column=0, sticky=tk.W, pady=3)
        cbo_t = ttk.Combobox(grid, width=28, values=teams)
        cbo_t.grid(row=1, column=1, sticky=tk.EW, padx=6, pady=3)
        cbo_t.set(sug_team)

        ttk.Label(grid, text="Part (Level 2):").grid(row=2, column=0, sticky=tk.W, pady=3)
        cbo_p = ttk.Combobox(grid, width=28, values=parts)
        cbo_p.grid(row=2, column=1, sticky=tk.EW, padx=6, pady=3)
        cbo_p.set(sug_part)

        ttk.Label(grid, text="Unit (Level 3):").grid(row=3, column=0, sticky=tk.W, pady=3)
        cbo_u = ttk.Combobox(grid, width=28, values=units)
        cbo_u.grid(row=3, column=1, sticky=tk.EW, padx=6, pady=3)
        cbo_u.set(sug_unit)

        ttk.Label(grid, text="Folder Path (L1\\L2\\L3...):", font=("", 9, "bold")).grid(row=4, column=0, sticky=tk.W, pady=4)
        ent_full = ttk.Entry(grid, width=32)
        ent_full.grid(row=4, column=1, sticky=tk.EW, padx=6, pady=4)
        ent_full.insert(0, f"{sug_team}\\{sug_part}\\{sug_unit}")

        def _sync_full_path(*args):
            t = cbo_t.get().strip()
            p = cbo_p.get().strip()
            u = cbo_u.get().strip()
            res = "\\".join([s for s in [t, p, u] if s])
            ent_full.delete(0, tk.END)
            ent_full.insert(0, res)

        cbo_t.bind("<<ComboboxSelected>>", _sync_full_path)
        cbo_t.bind("<KeyRelease>", _sync_full_path)
        cbo_p.bind("<<ComboboxSelected>>", _sync_full_path)
        cbo_p.bind("<KeyRelease>", _sync_full_path)
        cbo_u.bind("<<ComboboxSelected>>", _sync_full_path)
        cbo_u.bind("<KeyRelease>", _sync_full_path)

        # Match Scope Options
        box_scope = ttk.LabelFrame(frm, text="Match Condition", padding=8)
        box_scope.pack(fill=tk.X, pady=(0, 10))

        var_scope = tk.StringVar(value="email")
        rb_email = ttk.Radiobutton(box_scope, text=f"Match exact email: {sender_email}", variable=var_scope, value="email")
        rb_email.pack(anchor=tk.W, pady=2)

        if sender_domain:
            rb_domain = ttk.Radiobutton(
                box_scope,
                text=f"Match entire domain: *{sender_domain} (Recommended for vendors/teams)",
                variable=var_scope,
                value="domain"
            )
            rb_domain.pack(anchor=tk.W, pady=2)

        # Buttons
        btn_bar = ttk.Frame(frm)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        def on_confirm_stage():
            r_name = ent_name.get().strip()
            r_path = ent_full.get().strip()
            if not r_name or not r_path:
                messagebox.showwarning("Notice", "Specify both Rule Name and Target Folder.")
                return

            dlg.destroy()

            # Clean path to Team\Part\Unit format
            norm_path = "\\".join([s.strip() for s in re.split(r'[\\/]', r_path) if s.strip()])
            mode = var_scope.get()

            # Remove previous staged for this message
            for existing in self.staged_actions:
                if existing.message_id == msg.entry_id:
                    self.staged_actions.remove(existing)
                    break

            action = StagedAction(
                action_type="create_rule",
                rule_name=r_name,
                rule_id="",
                target_folder=norm_path,
                sender_email=sender_email,
                sender_domain=sender_domain,
                match_mode=mode,
                message_id=msg.entry_id,
                subject=msg.subject
            )
            self.staged_actions.append(action)

            self._populate_inbox_table()
            self._update_pending_bar()

        btn_cancel = ttk.Button(btn_bar, text="Cancel", command=dlg.destroy)
        btn_cancel.pack(side=tk.RIGHT, padx=4)

        btn_ok = ttk.Button(btn_bar, text="Stage Hierarchical Rule", command=on_confirm_stage)
        btn_ok.pack(side=tk.RIGHT, padx=4)

    def _move_selected_now(self):
        if not self.selected_message:
            messagebox.showwarning("Notice", "Select an email message first.")
            return
        if not self.yaml_mgr.rules:
            messagebox.showwarning("Notice", "No rules available to determine target folder.")
            return

        choice = self._prompt_rule_selection(
            self.selected_message,
            allow_scope=False,
            title="Move Message Now",
            confirm_text="Move Now",
        )
        if not choice:
            return
        rule, _ = choice

        store = self.yaml_mgr.stores.get("active_archive")
        store_path = store.file_path if store else ""
        ok = self.outlook.move_message(self.selected_message.entry_id, rule.target_folder, store_path)
        if ok:
            move_msg = f"Email moved to '{rule.target_folder}'."
            if self.outlook.is_simulated():
                move_msg = f"[SIMULATION] No changes were made to Outlook.\n\n{move_msg}"
            messagebox.showinfo("Moved", move_msg)
            self.refresh_inbox()

    def _on_inbox_right_click(self, event):
        item = self.tree_inbox.identify_row(event.y)
        if item:
            self.tree_inbox.selection_set(item)
            self._on_message_select_fast(None)
            self.menu_inbox.post(event.x_root, event.y_root)

    def _clear_all_staged(self):
        self.staged_actions.clear()
        self._populate_inbox_table()
        self._update_pending_bar()

    def _update_pending_bar(self):
        count = len(self.staged_actions)
        if count > 0:
            self.lbl_pending_status.config(text=pluralize_count(count, "pending change"))
            if not self.pending_bar.winfo_manager():
                self.pending_bar.pack(fill=tk.X, side=tk.BOTTOM, before=self.paned, padx=6, pady=(0, 4))
        else:
            if self.pending_bar.winfo_manager():
                self.pending_bar.pack_forget()

    def _build_review_staged_dialog(self):
        """Build Review Pending Changes modal dialog and return (dlg, tree)."""
        dlg = tk.Toplevel(self)
        dlg.title("Review Pending Staged Changes")
        dlg.geometry("760x360")
        dlg.minsize(640, 280)
        dlg.transient(self)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        btn_bar = ttk.Frame(frm)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        list_wrap = ttk.Frame(frm)
        list_wrap.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        cols = ("Email", "Action", "Rule", "Scope", "Target Folder")
        tree = ttk.Treeview(list_wrap, columns=cols, show="headings", selectmode="browse")
        tree.heading("Email", text="Email")
        tree.heading("Action", text="Action")
        tree.heading("Rule", text="Rule")
        tree.heading("Scope", text="Scope")
        tree.heading("Target Folder", text="Target Folder")

        tree.column("Email", width=210)
        tree.column("Action", width=95)
        tree.column("Rule", width=130)
        tree.column("Scope", width=150)
        tree.column("Target Folder", width=140)

        scroll = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        def _populate():
            tree.delete(*tree.get_children())
            for idx, act in enumerate(self.staged_actions):
                action_lbl = "New Rule" if act.action_type == "create_rule" else "Add to Rule"
                scope_lbl = (
                    f"Whole domain ({act.sender_domain})"
                    if act.match_mode == "domain"
                    else f"This sender ({act.sender_email})"
                )
                mail_lbl = f"{act.subject} <{act.sender_email}>"
                tree.insert(
                    "",
                    tk.END,
                    iid=f"rev_{idx}",
                    values=(mail_lbl, action_lbl, act.rule_name, scope_lbl, act.target_folder),
                )

        def _remove_selected():
            sel = tree.selection()
            if not sel:
                return
            idx = int(sel[0].split("_")[1])
            if 0 <= idx < len(self.staged_actions):
                self.staged_actions.pop(idx)
                self._populate_inbox_table()
                self._update_pending_bar()
                if not self.staged_actions:
                    dlg.destroy()
                    return
                _populate()

        _populate()

        ttk.Button(btn_bar, text="Remove Selected", command=_remove_selected).pack(side=tk.LEFT)
        ttk.Button(btn_bar, text="Close", command=dlg.destroy).pack(side=tk.RIGHT)
        return dlg, tree

    def _open_review_staged_dialog(self):
        """Open modal dialog listing staged actions with per-row removal."""
        if not self.staged_actions:
            return
        dlg, _ = self._build_review_staged_dialog()
        self.wait_window(dlg)

    # -----------------------------------------------------------------
    # CONFLICT INSPECTOR & BATCH APPLY
    # -----------------------------------------------------------------
    def _open_conflict_inspector(self):
        """Open the interactive Conflict Inspector modal."""
        ConflictDialog(self, self.conflict_detector, self.sync_engine)
        self.refresh_inbox()

    def _apply_all_staged(self):
        if not self.staged_actions:
            return

        # Check for conflicts first
        conflicts = self.conflict_detector.detect_conflicts()
        if conflicts:
            resp = messagebox.askyesno(
                "Rule Conflicts Detected",
                f"Warning: {len(conflicts)} potential conflicts detected between YAML and Outlook rules.\n\n"
                "Do you want to open the Conflict Inspector to review them before syncing?\n"
                "(Choose 'No' to proceed with YAML as Master Overwrite)",
                icon=messagebox.WARNING
            )
            if resp:
                self._open_conflict_inspector()
                return

        count = len(self.staged_actions)
        new_rules_count = sum(1 for a in self.staged_actions if a.action_type == "create_rule")
        add_rules_count = count - new_rules_count

        confirm = messagebox.askyesno(
            "Apply Batch Changes",
            f"Apply all {count} staged actions?\n\n"
            f"• Create {new_rules_count} new rules\n"
            f"• Assign {add_rules_count} emails to existing rules\n"
            f"• Move corresponding emails to target folders in Outlook\n\n"
            "This will update rules.yaml and synchronize with Outlook."
        )
        if not confirm:
            return

        store = self.yaml_mgr.stores.get("active_archive")
        store_path = store.file_path if store else ""

        # 1. Update YAML
        for action in self.staged_actions:
            if action.action_type == "create_rule":
                new_id = self.yaml_mgr.generate_rule_id(action.rule_name)

                emails = [action.sender_email] if action.match_mode == "email" else []
                domains = [action.sender_domain] if action.match_mode == "domain" else []

                new_r = RuleConfig(
                    id=new_id,
                    name=action.rule_name,
                    enabled=True,
                    groups=[],
                    emails=emails,
                    domains=domains,
                    subject_keywords=[],
                    target_store="active_archive",
                    target_folder=action.target_folder
                )
                self.yaml_mgr.rules.append(new_r)

                if action.sender_email in self.yaml_mgr.unclassified_pool:
                    self.yaml_mgr.unclassified_pool.remove(action.sender_email)

            elif action.action_type == "add_to_rule":
                as_domain = (action.match_mode == "domain")
                self.yaml_mgr.add_sender_to_rule_or_group(
                    action.sender_email,
                    action.rule_id,
                    as_domain=as_domain,
                    save=False,
                )

            # Move message in Outlook
            if action.message_id and action.target_folder:
                self.outlook.move_message(action.message_id, action.target_folder, store_path)

        self.yaml_mgr.save()

        # 2. Sync to Outlook COM
        success, msg = self.sync_engine.push_to_outlook()

        # 3. Clear queue & refresh
        self.staged_actions.clear()
        self.refresh_inbox()

        if success:
            sim_prefix = "[SIMULATION] No changes were made to Outlook.\n\n" if self.outlook.is_simulated() else ""
            messagebox.showinfo(
                "Sync Complete",
                f"{sim_prefix}"
                f"Successfully applied {count} actions!\n"
                f"Created {new_rules_count} new rules, updated {add_rules_count} rules.\n"
                f"Outlook native rules are now synchronized."
            )
        else:
            messagebox.showwarning("Notice", f"Updated YAML, but Outlook sync returned:\n{msg}")
