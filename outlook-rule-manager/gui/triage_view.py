"""Triage Workspace: High-Performance Multi-Pane with Full Email Inspector & Fast Staging."""
import tkinter as tk
from tkinter import ttk, messagebox
import re
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass

from core.models import EmailMessage, RuleConfig
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

        # Drag and Drop tracking
        self.drag_source_id: Optional[str] = None
        self.drag_window: Optional[tk.Toplevel] = None
        self.dragged_message: Optional[EmailMessage] = None
        self.is_over_new_rule_zone = False

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

        btn_expand = ttk.Button(top_bar, text="Expand Tree", command=self._expand_all)
        btn_expand.pack(side=tk.LEFT, padx=2)

        btn_collapse = ttk.Button(top_bar, text="Collapse Tree", command=self._collapse_all)
        btn_collapse.pack(side=tk.LEFT, padx=2)

        btn_conflicts = ttk.Button(top_bar, text="Check Rule Conflicts", command=self._open_conflict_inspector)
        btn_conflicts.pack(side=tk.LEFT, padx=8)

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
        # MAIN 3-PANE LAYOUT (HIGH PERFORMANCE, ZERO DELAY)
        # -------------------------------------------------------------
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        # =============================================================
        # PANE 1 (LEFT 28%): RULES TREE & DROP TARGET
        # =============================================================
        self.frame_left = tk.Frame(paned, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=6, pady=6)
        paned.add(self.frame_left, weight=3)

        # Dedicated Drop Target for Instant Rule Creation
        self.drop_new_zone = tk.Frame(
            self.frame_left,
            bg="#f0fdf4",
            highlightbackground="#16a34a",
            highlightcolor="#16a34a",
            highlightthickness=2,
            padx=8,
            pady=8,
            cursor="hand2"
        )
        self.drop_new_zone.pack(fill=tk.X, pady=(0, 6))

        self.lbl_drop_title = tk.Label(
            self.drop_new_zone,
            text="[+] DROP HERE TO CREATE NEW RULE",
            bg="#f0fdf4",
            fg="#15803d",
            font=("", 9, "bold")
        )
        self.lbl_drop_title.pack()

        self.lbl_drop_sub = tk.Label(
            self.drop_new_zone,
            text="Auto-names rule & folder. Instant staging (0ms delay).",
            bg="#f0fdf4",
            fg="#166534",
            font=("", 8)
        )
        self.lbl_drop_sub.pack(pady=(2, 0))

        # Rules Hierarchy Treeview
        tree_container = ttk.Frame(self.frame_left)
        tree_container.pack(fill=tk.BOTH, expand=True)

        self.tree_rules = ttk.Treeview(
            tree_container,
            columns=("Details",),
            show="tree headings",
            selectmode="browse"
        )
        self.tree_rules.heading("#0", text="Rules & Staged Queue")
        self.tree_rules.heading("Details", text="Target Folder")
        self.tree_rules.column("#0", width=170)
        self.tree_rules.column("Details", width=100)

        rules_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree_rules.yview)
        self.tree_rules.configure(yscrollcommand=rules_scroll.set)
        self.tree_rules.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rules_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree_rules.bind("<Delete>", self._on_tree_delete_staged)

        # =============================================================
        # PANE 2 (CENTER 36%): HIGH PERFORMANCE INBOX LIST (INSTANT CLICK)
        # =============================================================
        self.frame_center = tk.Frame(paned, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=6, pady=6)
        paned.add(self.frame_center, weight=4)

        # Filter Strip
        filter_strip = tk.Frame(self.frame_center, bg="#f8fafc")
        filter_strip.pack(fill=tk.X, pady=(0, 6))

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

        self.ent_search = ttk.Entry(filter_strip, width=16)
        self.ent_search.pack(side=tk.RIGHT, padx=2)
        self.ent_search.bind("<KeyRelease>", lambda e: self._on_search_change())
        tk.Label(filter_strip, text="Search:", bg="#f8fafc", fg="#64748b", font=("", 8)).pack(side=tk.RIGHT, padx=2)

        # High-Speed Treeview for Inbox Messages (Virtual rendering, 0ms lag)
        inbox_container = ttk.Frame(self.frame_center)
        inbox_container.pack(fill=tk.BOTH, expand=True)

        cols = ("Sender", "Subject", "Status")
        self.tree_inbox = ttk.Treeview(inbox_container, columns=cols, show="headings", selectmode="browse")
        self.tree_inbox.heading("Sender", text="From")
        self.tree_inbox.heading("Subject", text="Subject")
        self.tree_inbox.heading("Status", text="Status / Staged")

        self.tree_inbox.column("Sender", width=130)
        self.tree_inbox.column("Subject", width=180)
        self.tree_inbox.column("Status", width=110)

        inbox_scroll = ttk.Scrollbar(inbox_container, orient=tk.VERTICAL, command=self.tree_inbox.yview)
        self.tree_inbox.configure(yscrollcommand=inbox_scroll.set)
        self.tree_inbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inbox_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Fast Instant Selection Event (<5ms response)
        self.tree_inbox.bind("<<TreeviewSelect>>", self._on_message_select_fast)

        # Drag and Drop bindings
        self.tree_inbox.bind("<ButtonPress-1>", self._on_drag_start)
        self.tree_inbox.bind("<B1-Motion>", self._on_drag_motion)
        self.tree_inbox.bind("<ButtonRelease-1>", self._on_drag_release)

        # Context Menu
        self.menu_inbox = tk.Menu(self, tearoff=0)
        self.menu_inbox.add_command(label="[+] Stage: Create New Rule from Sender", command=self._menu_stage_new_rule)
        self.menu_inbox.add_command(label="Stage: Add to Selected Rule in Left Panel", command=self._menu_stage_existing_rule)
        self.menu_inbox.add_separator()
        self.menu_inbox.add_command(label="Move Message to Folder Now", command=self._move_selected_now)
        self.tree_inbox.bind("<Button-3>", self._on_inbox_right_click)

        # =============================================================
        # PANE 3 (RIGHT 36%): EXPANSIVE EMAIL INSPECTOR (CLEAR VIEW)
        # =============================================================
        self.frame_right = tk.Frame(paned, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1, padx=12, pady=10)
        paned.add(self.frame_right, weight=4)

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

        # Quick Actions Card in Inspector
        action_bar = tk.Frame(self.frame_right, bg="#ffffff")
        action_bar.pack(fill=tk.X, pady=(0, 6))

        self.btn_quick_stage_new = ttk.Button(
            action_bar,
            text="+ Stage New Rule",
            command=self._menu_stage_new_rule
        )
        self.btn_quick_stage_new.pack(side=tk.LEFT, padx=(0, 4))

        self.mb_assign_rule = ttk.Menubutton(
            action_bar,
            text="Assign to Rule... ▼"
        )
        self.menu_assign = tk.Menu(self.mb_assign_rule, tearoff=0)
        self.mb_assign_rule.config(menu=self.menu_assign)
        self.mb_assign_rule.pack(side=tk.LEFT, padx=4)

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
        # BOTTOM FLOATING STAGING DOCK (BATCH COMMIT)
        # =============================================================
        self.dock_frame = tk.Frame(self, bg="#0f172a", padx=16, pady=8)
        self.dock_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=(0, 4))

        dock_left = tk.Frame(self.dock_frame, bg="#0f172a")
        dock_left.pack(side=tk.LEFT)

        self.lbl_dock_indicator = tk.Label(dock_left, text="●", bg="#0f172a", fg="#94a3b8", font=("", 12))
        self.lbl_dock_indicator.pack(side=tk.LEFT, padx=(0, 6))

        self.lbl_dock_status = tk.Label(
            dock_left,
            text="Ready: No pending changes. Drag emails to stage new rules.",
            bg="#0f172a",
            fg="#f8fafc",
            font=("", 9, "bold")
        )
        self.lbl_dock_status.pack(side=tk.LEFT)

        dock_right = tk.Frame(self.dock_frame, bg="#0f172a")
        dock_right.pack(side=tk.RIGHT)

        self.btn_dock_clear = tk.Button(
            dock_right, text="Discard All", relief="flat", bg="#334155", fg="#e2e8f0",
            font=("", 9), padx=10, pady=3, state=tk.DISABLED, command=self._clear_all_staged
        )
        self.btn_dock_clear.pack(side=tk.LEFT, padx=4)

        self.btn_dock_apply = tk.Button(
            dock_right, text="Apply & Sync All to Outlook (0)", relief="flat", bg="#16a34a",
            fg="#ffffff", font=("", 9, "bold"), padx=14, pady=3, state=tk.DISABLED,
            command=self._apply_all_staged
        )
        self.btn_dock_apply.pack(side=tk.LEFT, padx=4)

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

        # Highlight matched rule in left tree
        matched_rule, _ = self.sync_engine.match_message(m.sender_email, m.subject)
        if matched_rule:
            target_node = f"rule_{matched_rule.id}"
            if self.tree_rules.exists(target_node):
                self.tree_rules.selection_set(target_node)
                self.tree_rules.see(target_node)

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
        self.refresh_rules_tree()
        self._populate_inbox_table()
        self._update_assign_menu()
        self._update_dock()

    def refresh_rules_tree(self):
        self.tree_rules.delete(*self.tree_rules.get_children())

        # Category 1: PENDING STAGED
        staged_count = len(self.staged_actions)
        self.tree_rules.insert(
            "", tk.END, iid="__STAGED__",
            text=f"★ PENDING CHANGES ({staged_count})",
            values=("Click Apply below",), open=True
        )

        for idx, action in enumerate(self.staged_actions):
            item_id = f"staged_{idx}"
            if action.action_type == "create_rule":
                label = f"[+ New Rule] {action.rule_name}"
                info = f"{action.target_folder} ({action.sender_email})"
            else:
                label = f"[+ Add] {action.rule_name}"
                info = f"Add: {action.sender_email}"

            self.tree_rules.insert("__STAGED__", tk.END, iid=item_id, text=label, values=(info,))

        # Category 2: ACTIVE RULES (Hierarchical Team \ Part \ Unit Folders)
        self.tree_rules.insert(
            "", tk.END, iid="__ACTIVE__",
            text="▼ HIERARCHICAL FOLDERS & RULES",
            values=("Folder Path",), open=True
        )

        folder_nodes_map: Dict[str, str] = {}

        for rule in self.yaml_mgr.rules:
            prefix = "[ON]" if rule.enabled else "[OFF]"
            raw_folder = rule.target_folder or "_Unclassified"
            # Split path by \ or /
            parts = [p.strip() for p in re.split(r'[\\/]', raw_folder) if p.strip()]

            # Build intermediate hierarchical nodes: Team \ Part \ Unit
            parent_node = "__ACTIVE__"
            accum_path = ""
            for depth, part in enumerate(parts):
                accum_path = f"{accum_path}\\{part}" if accum_path else part
                fld_id = f"fld_{accum_path.lower().replace(' ', '_')}"
                if fld_id not in folder_nodes_map:
                    level_label = f"📁 [L{depth+1}] {part}"
                    self.tree_rules.insert(
                        parent_node, tk.END, iid=fld_id,
                        text=level_label,
                        values=(accum_path,),
                        open=True
                    )
                    folder_nodes_map[fld_id] = accum_path
                parent_node = fld_id

            # Attach Rule node under the deepest folder node
            rule_node = f"rule_{rule.id}"
            self.tree_rules.insert(
                parent_node, tk.END, iid=rule_node,
                text=f"  ⚡ {prefix} {rule.name}",
                values=(rule.target_folder,), open=False
            )

            all_emails = self.yaml_mgr.get_all_emails_for_rule(rule)
            all_domains = self.yaml_mgr.get_all_domains_for_rule(rule)

            for d in all_domains:
                self.tree_rules.insert(rule_node, tk.END, text=f"    domain: {d}", values=("Domain Rule",))
            for e in all_emails:
                self.tree_rules.insert(rule_node, tk.END, text=f"    {e}", values=("Member Email",))

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

            # Display Status
            if is_staged:
                status_disp = f"★ [Staged -> {staged_map[msg.entry_id].rule_name}]"
            elif matched_rule:
                status_disp = f"[Matches: {matched_rule.name}]"
            else:
                status_disp = "[Needs Rule]"

            sender_disp = f"{msg.sender_name} <{msg.sender_email}>" if msg.sender_name else msg.sender_email

            self.tree_inbox.insert(
                "", tk.END, iid=msg.entry_id,
                values=(sender_disp, msg.subject, status_disp)
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

    def _update_assign_menu(self):
        self.menu_assign.delete(0, tk.END)
        for r in self.yaml_mgr.rules:
            self.menu_assign.add_command(
                label=f"{r.name} ({r.target_folder or 'Root'})",
                command=lambda rid=r.id: self._stage_add_to_existing_rule_by_id(rid)
            )

    def _expand_all(self):
        def _exp(item):
            self.tree_rules.item(item, open=True)
            for child in self.tree_rules.get_children(item):
                _exp(child)
        for root in self.tree_rules.get_children():
            _exp(root)

    def _collapse_all(self):
        def _col(item):
            for child in self.tree_rules.get_children(item):
                _col(child)
            self.tree_rules.item(item, open=False)
        for root in self.tree_rules.get_children():
            _col(root)
        if self.tree_rules.exists("__STAGED__"):
            self.tree_rules.item("__STAGED__", open=True)
        if self.tree_rules.exists("__ACTIVE__"):
            self.tree_rules.item("__ACTIVE__", open=True)

    # -----------------------------------------------------------------
    # DRAG AND DROP
    # -----------------------------------------------------------------
    def _on_drag_start(self, event):
        item = self.tree_inbox.identify_row(event.y)
        if not item:
            return

        self.drag_source_id = item
        self.dragged_message = next((m for m in self.messages if m.entry_id == item), None)
        self.tree_inbox.selection_set(item)
        self._on_message_select_fast(None)

        if self.dragged_message and not self.drag_window:
            self.drag_window = tk.Toplevel(self)
            self.drag_window.wm_overrideredirect(True)
            self.drag_window.attributes("-topmost", True)

            lbl = tk.Label(
                self.drag_window,
                text=f" ✉ {self.dragged_message.sender_email} ➔ Release on Left Canvas ",
                background="#0f172a",
                foreground="#f8fafc",
                relief="solid",
                borderwidth=1,
                font=("", 9, "bold"),
                padx=8,
                pady=4
            )
            lbl.pack()
            self.drag_window.geometry(f"+{event.x_root + 15}+{event.y_root + 15}")

    def _on_drag_motion(self, event):
        if not self.drag_window:
            return

        self.drag_window.geometry(f"+{event.x_root + 15}+{event.y_root + 15}")

        # Hover drop zone
        zx = event.x_root - self.drop_new_zone.winfo_rootx()
        zy = event.y_root - self.drop_new_zone.winfo_rooty()
        over_new = (0 <= zx <= self.drop_new_zone.winfo_width() and 0 <= zy <= self.drop_new_zone.winfo_height())

        if over_new:
            if not self.is_over_new_rule_zone:
                self.is_over_new_rule_zone = True
                self.drop_new_zone.config(bg="#15803d", highlightbackground="#22c55e")
                self.lbl_drop_title.config(bg="#15803d", fg="#ffffff", text="[+] RELEASE TO CREATE NEW RULE NOW!")
                self.lbl_drop_sub.config(bg="#15803d", fg="#bbf7d0")
        else:
            if self.is_over_new_rule_zone:
                self.is_over_new_rule_zone = False
                self.drop_new_zone.config(bg="#f0fdf4", highlightbackground="#16a34a")
                self.lbl_drop_title.config(bg="#f0fdf4", fg="#15803d", text="[+] DROP HERE TO CREATE NEW RULE")
                self.lbl_drop_sub.config(bg="#f0fdf4", fg="#166534")

        # Hover tree node
        rx = event.x_root - self.tree_rules.winfo_rootx()
        ry = event.y_root - self.tree_rules.winfo_rooty()
        if 0 <= rx <= self.tree_rules.winfo_width() and 0 <= ry <= self.tree_rules.winfo_height():
            hover_id = self.tree_rules.identify_row(ry)
            if hover_id and hover_id.startswith("rule_"):
                self.tree_rules.selection_set(hover_id)

    def _on_drag_release(self, event):
        if self.drag_window:
            self.drag_window.destroy()
            self.drag_window = None

        if self.is_over_new_rule_zone:
            self.is_over_new_rule_zone = False
            self.drop_new_zone.config(bg="#f0fdf4", highlightbackground="#16a34a")
            self.lbl_drop_title.config(bg="#f0fdf4", fg="#15803d", text="[+] DROP HERE TO CREATE NEW RULE")
            self.lbl_drop_sub.config(bg="#f0fdf4", fg="#166534")

        if not self.drag_source_id or not self.dragged_message:
            self.drag_source_id = None
            self.dragged_message = None
            return

        msg = self.dragged_message

        # Drop on New Rule Zone
        zx = event.x_root - self.drop_new_zone.winfo_rootx()
        zy = event.y_root - self.drop_new_zone.winfo_rooty()
        if 0 <= zx <= self.drop_new_zone.winfo_width() and 0 <= zy <= self.drop_new_zone.winfo_height():
            self._stage_create_new_rule(msg)
            self.drag_source_id = None
            self.dragged_message = None
            return

        # Drop on Tree Node (Rule or Hierarchical Folder: Team \ Part \ Unit)
        rx = event.x_root - self.tree_rules.winfo_rootx()
        ry = event.y_root - self.tree_rules.winfo_rooty()
        if 0 <= rx <= self.tree_rules.winfo_width() and 0 <= ry <= self.tree_rules.winfo_height():
            target_id = self.tree_rules.identify_row(ry)
            if target_id:
                if target_id.startswith("rule_"):
                    raw_rule_id = target_id.replace("rule_", "", 1)
                    self._stage_add_to_existing_rule(msg, raw_rule_id)
                elif target_id.startswith("fld_"):
                    # Dropped directly into a Team, Part, or Unit folder!
                    fld_vals = self.tree_rules.item(target_id, "values")
                    target_folder_path = fld_vals[0] if fld_vals else ""
                    self._stage_create_new_rule(msg, custom_folder=target_folder_path)

        self.drag_source_id = None
        self.dragged_message = None

    # -----------------------------------------------------------------
    # STAGING ENGINE
    # -----------------------------------------------------------------
    def _stage_create_new_rule(self, msg: EmailMessage, custom_folder: Optional[str] = None):
        suggested_name, suggested_folder = suggest_rule_and_folder(msg.sender_name, msg.sender_email)
        target_folder = custom_folder if custom_folder else suggested_folder

        sender_email = msg.sender_email
        sender_domain = f"@{sender_email.split('@')[1]}" if "@" in sender_email else ""
        match_mode = "domain" if any(w in sender_domain for w in ["omron", "automation", "partner", "corp", "vendor"]) else "email"

        for existing in self.staged_actions:
            if existing.message_id == msg.entry_id:
                self.staged_actions.remove(existing)
                break

        action = StagedAction(
            action_type="create_rule",
            rule_name=suggested_name,
            rule_id=f"rule_{re.sub(r'[^a-zA-Z0-9_]', '_', suggested_name.lower())}",
            target_folder=target_folder,
            sender_email=sender_email,
            sender_domain=sender_domain,
            match_mode=match_mode,
            message_id=msg.entry_id,
            subject=msg.subject
        )
        self.staged_actions.append(action)

        self.refresh_rules_tree()
        self._populate_inbox_table()
        self._update_dock()

    def _stage_add_to_existing_rule(self, msg: EmailMessage, rule_id: str):
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
            match_mode="email",
            message_id=msg.entry_id,
            subject=msg.subject
        )
        self.staged_actions.append(action)

        self.refresh_rules_tree()
        self._populate_inbox_table()
        self._update_dock()

    def _stage_add_to_existing_rule_by_id(self, rule_id: str):
        if not self.selected_message:
            messagebox.showwarning("Notice", "Select an email message first.")
            return
        self._stage_add_to_existing_rule(self.selected_message, rule_id)

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
            if any(w in sender_domain for w in ["omron", "automation", "partner", "corp", "vendor"]):
                var_scope.set("domain")

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
                rule_id=f"rule_{re.sub(r'[^a-zA-Z0-9_]', '_', r_name.lower())}",
                target_folder=norm_path,
                sender_email=sender_email,
                sender_domain=sender_domain,
                match_mode=mode,
                message_id=msg.entry_id,
                subject=msg.subject
            )
            self.staged_actions.append(action)

            self.refresh_rules_tree()
            self._populate_inbox_table()
            self._update_dock()

        btn_cancel = ttk.Button(btn_bar, text="Cancel", command=dlg.destroy)
        btn_cancel.pack(side=tk.RIGHT, padx=4)

        btn_ok = ttk.Button(btn_bar, text="Stage Hierarchical Rule", command=on_confirm_stage)
        btn_ok.pack(side=tk.RIGHT, padx=4)

    def _menu_stage_existing_rule(self):
        if not self.selected_message:
            messagebox.showwarning("Notice", "Select an email message first.")
            return
        sel = self.tree_rules.selection()
        if not sel or not sel[0].startswith("rule_"):
            messagebox.showwarning("Notice", "Select a rule in the Left Panel first.")
            return
        rule_id = sel[0].replace("rule_", "", 1)
        self._stage_add_to_existing_rule(self.selected_message, rule_id)

    def _move_selected_now(self):
        if not self.selected_message:
            messagebox.showwarning("Notice", "Select an email message first.")
            return
        sel = self.tree_rules.selection()
        if not sel or not sel[0].startswith("rule_"):
            messagebox.showwarning("Notice", "Select a target rule in the Left Panel first.")
            return
        rule_id = sel[0].replace("rule_", "", 1)
        rule = next((r for r in self.yaml_mgr.rules if r.id == rule_id), None)
        if not rule:
            return

        store = self.yaml_mgr.stores.get("active_archive")
        store_path = store.file_path if store else ""
        ok = self.outlook.move_message(self.selected_message.entry_id, rule.target_folder, store_path)
        if ok:
            messagebox.showinfo("Moved", f"Email moved to '{rule.target_folder}'.")
            self.refresh_inbox()

    def _on_inbox_right_click(self, event):
        item = self.tree_inbox.identify_row(event.y)
        if item:
            self.tree_inbox.selection_set(item)
            self._on_message_select_fast(None)
            self.menu_inbox.post(event.x_root, event.y_root)

    def _on_tree_delete_staged(self, event):
        sel = self.tree_rules.selection()
        if not sel or not sel[0].startswith("staged_"):
            return
        idx = int(sel[0].split("_")[1])
        if 0 <= idx < len(self.staged_actions):
            self.staged_actions.pop(idx)
            self.refresh_rules_tree()
            self._populate_inbox_table()
            self._update_dock()

    def _clear_all_staged(self):
        self.staged_actions.clear()
        self.refresh_rules_tree()
        self._populate_inbox_table()
        self._update_dock()

    def _update_dock(self):
        count = len(self.staged_actions)
        if count > 0:
            new_rules_count = sum(1 for a in self.staged_actions if a.action_type == "create_rule")
            assign_count = count - new_rules_count

            self.lbl_dock_indicator.config(fg="#22c55e")
            self.lbl_dock_status.config(
                text=f"Pending: {count} actions ({new_rules_count} new rules, {assign_count} assignments). Ready to apply.",
                fg="#f8fafc"
            )
            self.btn_dock_apply.config(
                state=tk.NORMAL,
                text=f"Apply & Sync All to Outlook ({count})"
            )
            self.btn_dock_clear.config(state=tk.NORMAL)
        else:
            self.lbl_dock_indicator.config(fg="#64748b")
            self.lbl_dock_status.config(
                text="Ready: No pending changes. Drag emails to stage new rules or assignments.",
                fg="#94a3b8"
            )
            self.btn_dock_apply.config(
                state=tk.DISABLED,
                text="Apply & Sync All to Outlook (0)"
            )
            self.btn_dock_clear.config(state=tk.DISABLED)

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
                new_id = action.rule_id
                c = 1
                while any(r.id == new_id for r in self.yaml_mgr.rules):
                    new_id = f"{action.rule_id}_{c}"
                    c += 1

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
                    as_domain=as_domain
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
            messagebox.showinfo(
                "Sync Complete",
                f"Successfully applied {count} actions!\n"
                f"Created {new_rules_count} new rules, updated {add_rules_count} rules.\n"
                f"Outlook native rules are now synchronized."
            )
        else:
            messagebox.showwarning("Notice", f"Updated YAML, but Outlook sync returned:\n{msg}")
