"""Triage Workspace: High-Performance Multi-Pane with Full Email Inspector & Fast Staging."""
import tkinter as tk
from tkinter import ttk, messagebox
import re
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field

from core.models import EmailMessage, RuleConfig, pluralize_count
from core.yaml_manager import YamlConfigManager
from core.outlook_client import BaseOutlookClient
from core.sync_engine import SyncEngine
from core.conflict_detector import ConflictDetector
from gui.conflict_dialog import ConflictDialog
from gui.quick_rule_dialog import QuickRuleDialog


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
    moved_from: List[str] = field(default_factory=list)   # rules that will lose this sender
    merge_same_name: bool = False   # new flows: reuse a rule with the same name in the same folder

    @property
    def sender_value(self) -> str:
        return self.sender_domain if self.match_mode == "domain" else self.sender_email


class TriageView(ttk.Frame):
    """High-Performance Workspace: Instant Click Response, Spacious Email Inspector & Conflict Resolver."""

    def __init__(
        self,
        parent,
        yaml_mgr: YamlConfigManager,
        outlook: BaseOutlookClient,
        sync_engine: SyncEngine,
        inbox_host: Optional[tk.Misc] = None,
        reader_host: Optional[tk.Misc] = None,
        bottom_host: Optional[tk.Misc] = None,
    ):
        super().__init__(parent)
        # Integrated (single-screen) mode: the main window owns the panes; mails are dropped on the
        # main rules tree (see attach_drop_tree) instead of this view's own drop panel.
        self.inbox_host = inbox_host
        self.reader_host = reader_host
        self.bottom_host = bottom_host
        self.integrated = inbox_host is not None and reader_host is not None and bottom_host is not None
        self.on_message_activated = None   # integrated mode: user picked a mail -> show the reader
        self.on_rules_changed = None       # integrated mode: rules.yaml changed by Apply -> refresh tree
        self.status_sink = None            # integrated mode: where short feedback messages go
        self.yaml_mgr = yaml_mgr
        self.outlook = outlook
        self.sync_engine = sync_engine
        self.conflict_detector = ConflictDetector(self.yaml_mgr, self.outlook)

        self.messages: List[EmailMessage] = []
        self.selected_message: Optional[EmailMessage] = None
        self.staged_actions: List[StagedAction] = []
        self.active_filter: str = "ALL"
        self.search_query: str = ""
        self.last_apply_mismatches: List[str] = []
        self.last_status_message: str = ""
        self.on_undo_request = None  # set by MainWindow
        self._last_used_folder: str = ""

        # Drag & drop state (mail list -> rules drop panel)
        self._drag_start: Optional[Tuple[int, int]] = None
        self._drag_pressed_selection: Tuple[str, ...] = ()
        self._drag_active: bool = False
        self._drag_ghost: Optional[tk.Toplevel] = None
        self._drag_hover_iid: Optional[str] = None

        self._build_ui()
        self.refresh_inbox()

    def _build_ui(self):
        # -------------------------------------------------------------
        # MAIN 2-PANE LAYOUT: INBOX LIST (LEFT) | READING & ACTIONS (RIGHT)
        # -------------------------------------------------------------
        if self.integrated:
            self.paned = None
            self.frame_left = tk.Frame(self.inbox_host, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=6, pady=6)
            self.frame_left.pack(fill=tk.BOTH, expand=True)
        else:
            self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
            self.paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

            # =========================================================
            # PANE 1 (LEFT, WIDE): INBOX LIST WITH "WILL GO TO" COLUMN
            # =========================================================
            self.frame_left = tk.Frame(self.paned, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=6, pady=6)
            self.paned.add(self.frame_left, weight=6)

        # Filter Strip
        filter_strip = tk.Frame(self.frame_left, bg="#f8fafc")
        filter_strip.pack(fill=tk.X, pady=(0, 4))

        self.var_filter = tk.StringVar(value=self.active_filter)
        self.btn_f_all = ttk.Radiobutton(
            filter_strip, text="All", value="ALL", variable=self.var_filter,
            style="Filter.Toolbutton", command=lambda: self._set_filter("ALL")
        )
        self.btn_f_all.pack(side=tk.LEFT, padx=1)

        self.btn_f_untracked = ttk.Radiobutton(
            filter_strip, text="Needs Rule", value="UNTRACKED", variable=self.var_filter,
            style="Filter.Toolbutton", command=lambda: self._set_filter("UNTRACKED")
        )
        self.btn_f_untracked.pack(side=tk.LEFT, padx=1)

        self.btn_f_staged = ttk.Radiobutton(
            filter_strip, text="Staged", value="STAGED", variable=self.var_filter,
            style="Filter.Toolbutton", command=lambda: self._set_filter("STAGED")
        )
        self.btn_f_staged.pack(side=tk.LEFT, padx=1)

        self.btn_refresh = ttk.Button(filter_strip, text="Refresh Inbox", command=self.refresh_inbox)
        self.btn_refresh.pack(side=tk.RIGHT)

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
        self.tree_inbox = ttk.Treeview(inbox_container, columns=cols, show="headings", selectmode="extended")
        self.tree_inbox.heading("Sender", text="From")
        self.tree_inbox.heading("Subject", text="Subject")
        self.tree_inbox.heading("WillGoTo", text="Will go to")

        self.tree_inbox.column("Sender", width=120, minwidth=80, stretch=True)
        self.tree_inbox.column("Subject", width=150, minwidth=100, stretch=True)
        self.tree_inbox.column("WillGoTo", width=120, minwidth=80, stretch=True)

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

        # Drag mail(s) onto the Rules drop panel (selection behaviour is kept intact)
        self.tree_inbox.bind("<ButtonPress-1>", self._on_drag_press, add="+")
        self.tree_inbox.bind("<B1-Motion>", self._on_drag_motion, add="+")
        self.tree_inbox.bind("<ButtonRelease-1>", self._on_drag_release, add="+")
        self.tree_inbox.bind("<Escape>", lambda e: self._cancel_drag())

        # Clicking / arrowing through the mail list shows the mail in the (shared) right pane
        self.tree_inbox.bind("<ButtonRelease-1>", self._notify_message_activated, add="+")
        self.tree_inbox.bind("<KeyRelease-Up>", self._notify_message_activated, add="+")
        self.tree_inbox.bind("<KeyRelease-Down>", self._notify_message_activated, add="+")

        # =============================================================
        # PANE 3 (RIGHT): EMAIL INSPECTOR & ACTIONS
        # =============================================================
        if self.integrated:
            self.frame_right = tk.Frame(self.reader_host, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1, padx=12, pady=10)
            self.frame_right.pack(fill=tk.BOTH, expand=True)
        else:
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
            wraplength=300,
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
            width=36,  # small requested width; the pane still expands with the window
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
            self.bottom_host if self.integrated else self,
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
    # DROP TARGET: mails are dropped on the main Rules navigator (see attach_drop_tree)
    # -----------------------------------------------------------------
    def _request_undo(self):
        if callable(self.on_undo_request):
            self.on_undo_request()

    # --- drop target abstraction ----
    def attach_drop_tree(self, tree: ttk.Treeview, resolver):
        """Use another tree (the main Rules navigator) as the drop target for mails."""
        self.tree_rules_drop = tree
        self._external_resolver = resolver
        tree.tag_configure("drop_hover", background="#bae6fd")

    def _resolve_drop(self, iid: Optional[str]):
        """('rule', id) / ('folder', path) / ('new', None) / None for a drop-target item."""
        if not iid:
            return None
        resolver = getattr(self, "_external_resolver", None)
        return resolver(iid) if resolver is not None else None

    def _notify_message_activated(self, event=None):
        if callable(self.on_message_activated) and self.tree_inbox.selection() and not self._drag_active:
            self.after_idle(self.on_message_activated)

    def refresh_undo_button(self):
        """Undo lives in the Rules navigator; nothing to refresh here."""

    def show_panel_status(self, message: str, error: bool = False):
        """Short feedback for the user (shown in the navigator status bar via status_sink)."""
        if callable(self.status_sink):
            self.status_sink(message, error)
        self.last_status_message = message

    def _rule_name_for(self, msg: EmailMessage, whole_domain: bool) -> str:
        """Readable rule name: the sender's display name, or the company for a whole-domain rule."""
        email = msg.sender_email or ""
        domain = email.split("@", 1)[1].lower() if "@" in email else ""
        if whole_domain and domain:
            return domain.split(".")[0].replace("-", " ").replace("_", " ").title()
        name = re.sub(r"[\(\[\{].*?[\)\]\}]", "", msg.sender_name or "").strip()
        name = re.sub(r"<.*?>", "", name).strip().strip('"')
        if name:
            return name
        local = email.split("@")[0] if email else "New Rule"
        return local.replace(".", " ").replace("_", " ").title() or "New Rule"

    def _default_folder_for(self, msg: EmailMessage) -> str:
        """Folder of a rule already handling this sender's domain, else the last folder used."""
        email = (msg.sender_email or "").lower()
        domain = "@" + email.split("@", 1)[1] if "@" in email else ""
        if domain:
            for rule in self.yaml_mgr.rules:
                if self.yaml_mgr.is_inside_unclassified(rule.target_folder or ""):
                    continue
                if domain in self.yaml_mgr.get_all_domains_for_rule(rule) or any(
                    e.endswith(domain) for e in self.yaml_mgr.get_all_emails_for_rule(rule)
                ):
                    return rule.target_folder
        return self._last_used_folder

    def _stage_new_rule_in_folder(self, msg: EmailMessage, name: str, folder: str, whole_domain: bool = False):
        """Stage 'sender -> rule <name> in <folder>'; reuses an existing rule of that name in that folder."""
        self._last_used_folder = folder
        existing = next(
            (r for r in self.yaml_mgr.rules
             if r.name.strip().lower() == name.strip().lower() and (r.target_folder or "").lower() == folder.lower()),
            None,
        )
        mode = "domain" if whole_domain else "email"
        if existing:
            self._stage_add_to_existing_rule(msg, existing.id, match_mode=mode, refresh=False)
            return
        sender_email = msg.sender_email
        for prev in list(self.staged_actions):
            if prev.message_id == msg.entry_id:
                self.staged_actions.remove(prev)
        self._append_staged(StagedAction(
            action_type="create_rule",
            rule_name=name,
            rule_id="",
            target_folder=folder,
            sender_email=sender_email,
            sender_domain=f"@{sender_email.split('@')[1]}" if "@" in sender_email else "",
            match_mode=mode,
            message_id=msg.entry_id,
            subject=msg.subject,
            merge_same_name=True,
        ))

    def _selected_messages(self) -> List[EmailMessage]:
        ids = set(self.tree_inbox.selection())
        return [m for m in self.messages if m.entry_id in ids]

    def drop_messages_on_target(self, target_iid: Optional[str], messages: List[EmailMessage],
                                whole_domain: bool = False) -> int:
        """Apply a drop of messages onto a drop-panel item. Returns number of staged actions."""
        if not messages or not target_iid:
            return 0
        target = self._resolve_drop(target_iid)
        if target is None:
            return 0
        kind, value = target
        if kind == "new":
            self._open_create_hierarchical_rule_dialog(messages[0])
            return 0
        if kind == "folder":
            folder = value
            if not folder or self.yaml_mgr.is_inside_unclassified(folder):
                self.show_panel_status("New rules cannot be created in this folder.", error=True)
                return 0
            for msg in messages:
                self._stage_new_rule_in_folder(msg, self._rule_name_for(msg, whole_domain), folder, whole_domain)
            self._populate_inbox_table()
            self._update_pending_bar()
            self.show_panel_status(f"Staged {pluralize_count(len(messages), 'email')} into '{folder}'.")
            return len(messages)
        rule_id = value
        mode = "domain" if whole_domain else "email"
        count = 0
        for msg in messages:
            if self._stage_add_to_existing_rule(msg, rule_id, match_mode=mode, refresh=False):
                count += 1
        if count:
            self._populate_inbox_table()
            self._update_pending_bar()
            rule = next((r for r in self.yaml_mgr.rules if r.id == rule_id), None)
            if rule is not None:
                self.show_panel_status(f"Staged {pluralize_count(count, 'email')} for rule '{rule.name}'.")
        return count

    # --- drag mechanics ------------------------------------------------
    def _on_drag_press(self, event):
        row = self.tree_inbox.identify_row(event.y)
        if not row:
            self._drag_start = None
            return
        self._drag_start = (event.x_root, event.y_root)
        current = self.tree_inbox.selection()
        # Pressing on an already-selected row of a multi-selection keeps the whole selection for dragging
        no_modifiers = not (event.state & 0x0001 or event.state & 0x0004)
        self._drag_pressed_selection = current if (row in current and no_modifiers and len(current) > 1) else ()

    def _on_drag_motion(self, event):
        if self._drag_start is None:
            return
        if not self._drag_active:
            dx = abs(event.x_root - self._drag_start[0])
            dy = abs(event.y_root - self._drag_start[1])
            if max(dx, dy) < 6:
                return
            self._begin_drag()
        self._move_ghost(event.x_root, event.y_root)
        self._set_drop_hover(self._drop_target_at(event.x_root, event.y_root))

    def _on_drag_release(self, event):
        if not self._drag_active:
            self._drag_start = None
            return
        target = self._drop_target_at(event.x_root, event.y_root)
        messages = self._selected_messages()
        whole_domain = bool(event.state & 0x0004)
        self._cancel_drag()
        if target:
            self.drop_messages_on_target(target, messages, whole_domain=whole_domain)

    def _begin_drag(self):
        self._drag_active = True
        if self._drag_pressed_selection:
            self.tree_inbox.selection_set(self._drag_pressed_selection)
        n = len(self.tree_inbox.selection())
        ghost = tk.Toplevel(self)
        ghost.overrideredirect(True)
        try:
            ghost.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(
            ghost, text=f"{pluralize_count(n, 'email')} → drop on a rule", bg="#0284c7", fg="#ffffff",
            font=("", 9, "bold"), padx=8, pady=3,
        ).pack()
        self._drag_ghost = ghost
        self.tree_inbox.configure(cursor="hand2")

    def _move_ghost(self, x_root: int, y_root: int):
        if self._drag_ghost is not None:
            self._drag_ghost.geometry(f"+{x_root + 14}+{y_root + 10}")

    def _drop_target_at(self, x_root: int, y_root: int) -> Optional[str]:
        """Return the drop-target item iid under the pointer (rules, folders, '+ New rule…')."""
        tree = getattr(self, "tree_rules_drop", None)
        if tree is None or not tree.winfo_ismapped():
            return None
        x = x_root - tree.winfo_rootx()
        y = y_root - tree.winfo_rooty()
        if not (0 <= x < tree.winfo_width() and 0 <= y < tree.winfo_height()):
            return None
        iid = tree.identify_row(y)
        return iid if self._resolve_drop(iid) is not None else None

    def _set_drop_hover(self, iid: Optional[str]):
        if iid == self._drag_hover_iid:
            return
        tree = getattr(self, "tree_rules_drop", None)
        if tree is None:
            return
        if self._drag_hover_iid and tree.exists(self._drag_hover_iid):
            tags = [t for t in tree.item(self._drag_hover_iid, "tags") if t != "drop_hover"]
            tree.item(self._drag_hover_iid, tags=tags)
        if iid and tree.exists(iid):
            tree.item(iid, tags=list(tree.item(iid, "tags")) + ["drop_hover"])
            tree.see(iid)
        self._drag_hover_iid = iid

    def _cancel_drag(self):
        self._set_drop_hover(None)
        if self._drag_ghost is not None:
            self._drag_ghost.destroy()
            self._drag_ghost = None
        self._drag_active = False
        self._drag_start = None
        self._drag_pressed_selection = ()
        self.tree_inbox.configure(cursor="")

    # -----------------------------------------------------------------
    # FILTER & SEARCH
    # -----------------------------------------------------------------
    def _set_filter(self, filter_name: str):
        self.active_filter = filter_name
        if self.var_filter.get() != filter_name:
            self.var_filter.set(filter_name)
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
        previous_selection = tuple(self.tree_inbox.selection())
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
                if action.moved_from:
                    will_go_to += f"  (from {', '.join(action.moved_from)})"
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

        # Keep the user's selection across refreshes (e.g. after a drop); otherwise select the first row
        children = self.tree_inbox.get_children()
        kept = [iid for iid in previous_selection if self.tree_inbox.exists(iid)]
        if kept:
            self.tree_inbox.selection_set(kept)
        elif children and not self.tree_inbox.selection():
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
        self._append_staged(action)

        self._populate_inbox_table()
        self._update_pending_bar()

    def _append_staged(self, action: "StagedAction"):
        """Queue an action, recording which rules would lose this sender (shown as 'from …')."""
        action.moved_from = self.yaml_mgr.preview_sender_move(
            action.sender_value, action.rule_id or None, as_domain=(action.match_mode == "domain")
        )["from_rules"]
        self.staged_actions.append(action)

    def _stage_add_to_existing_rule(
        self, msg: EmailMessage, rule_id: str, match_mode: str = "email", refresh: bool = True
    ) -> bool:
        rule = next((r for r in self.yaml_mgr.rules if r.id == rule_id), None)
        if not rule:
            return False

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
        self._append_staged(action)

        if refresh:
            self._populate_inbox_table()
            self._update_pending_bar()
        return True

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

    def _ask_quick_rule(self, **kwargs):
        """Open the Quick New Rule dialog (separate method so tests can patch it)."""
        return QuickRuleDialog.ask(self, **kwargs)

    def _open_create_hierarchical_rule_dialog(self, msg: EmailMessage):
        """'+ New rule…' / 'New Rule...': name + folder only, then stage the new rule."""
        sender_email = msg.sender_email
        sender_domain = f"@{sender_email.split('@')[1]}" if "@" in sender_email else ""
        folders = [f for f in self.yaml_mgr.get_all_folders() if not self.yaml_mgr.is_inside_unclassified(f)]
        result = self._ask_quick_rule(
            folders=folders,
            default_name=self._rule_name_for(msg, whole_domain=False),
            default_folder=self._default_folder_for(msg),
            sender_email=sender_email,
            sender_domain=sender_domain,
            blocked_folder=self.yaml_mgr.unclassified_folder(),
            title="New Rule",
        )
        if not result:
            return
        name, folder, scope = result
        self._stage_new_rule_in_folder(msg, name, folder, whole_domain=(scope == "domain"))
        self._populate_inbox_table()
        self._update_pending_bar()


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
                if self.integrated:
                    self.pending_bar.pack(fill=tk.X, padx=4, pady=(0, 4))
                else:
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
                if act.action_type == "create_rule":
                    action_lbl = "New Rule"
                elif act.moved_from:
                    action_lbl = f"Move from {', '.join(act.moved_from)}"
                else:
                    action_lbl = "Add to Rule"
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

        # One confirmation only. Conflicts with legacy Outlook rules are reviewed on demand via
        # "Check Rule Conflicts" in the header instead of interrupting every Apply.
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

        # Senders that also sit in address groups shared by several rules: ask once for the whole batch
        shared_lines = []
        for action in self.staged_actions:
            preview = self.yaml_mgr.preview_sender_move(
                action.sender_value, action.rule_id or None, as_domain=(action.match_mode == "domain")
            )
            for grp_name, users in preview["shared_groups"]:
                shared_lines.append(f"• {action.sender_value} — group '{grp_name}' (used by {', '.join(users)})")
        remove_from_shared = False
        if shared_lines:
            remove_from_shared = bool(messagebox.askyesno(
                "Shared Address Groups",
                "These senders are also in groups shared by several rules:\n\n"
                + "\n".join(shared_lines)
                + "\n\nRemove them from those groups too?\n"
                "(No = keep them there; they may keep going to the old rule.)",
            ))

        # 1. Update YAML (one Undo step for the whole batch)
        self.yaml_mgr.next_change_label = f"Apply {pluralize_count(count, 'inbox change')}"
        for action in self.staged_actions:
            if action.action_type == "create_rule" and action.merge_same_name:
                # Several emails dropped on the same folder/name -> one rule, not duplicates
                same = next(
                    (r for r in self.yaml_mgr.rules
                     if r.name.strip().lower() == action.rule_name.strip().lower()
                     and (r.target_folder or "").lower() == (action.target_folder or "").lower()),
                    None,
                )
                if same is not None:
                    self.yaml_mgr.assign_sender(
                        action.sender_value, same.id, as_domain=(action.match_mode == "domain"),
                        remove_from_shared_groups=remove_from_shared, save=False,
                    )
                    if action.message_id and action.target_folder:
                        self.outlook.move_message(action.message_id, action.target_folder, store_path)
                    continue

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
                # A sender lives in one rule: take it out of the rules that held it before
                self.yaml_mgr.detach_sender(
                    action.sender_value,
                    as_domain=(action.match_mode == "domain"),
                    except_rule_id=new_id,
                    remove_from_shared_groups=remove_from_shared,
                )
                if action.sender_email in self.yaml_mgr.unclassified_pool:
                    self.yaml_mgr.unclassified_pool.remove(action.sender_email)

            elif action.action_type == "add_to_rule":
                self.yaml_mgr.assign_sender(
                    action.sender_value,
                    action.rule_id,
                    as_domain=(action.match_mode == "domain"),
                    remove_from_shared_groups=remove_from_shared,
                    save=False,
                )

            # Move message in Outlook
            if action.message_id and action.target_folder:
                self.outlook.move_message(action.message_id, action.target_folder, store_path)

        self.yaml_mgr.save()

        # 2. Sync to Outlook COM
        success, msg = self.sync_engine.push_to_outlook()

        # Honesty check: report staged emails whose sender still resolves to another folder
        mismatches = []
        for action in self.staged_actions:
            matched, _ = self.sync_engine.match_message(action.sender_email, action.subject)
            got = matched.target_folder if matched else "Inbox"
            if got != action.target_folder:
                mismatches.append(f"• {action.sender_email} still goes to '{got}'")
        mismatch_txt = ("\n\nNot moved as expected:\n" + "\n".join(mismatches)) if mismatches else ""
        self.last_apply_mismatches = mismatches

        # 3. Clear queue & refresh
        self.staged_actions.clear()
        self.refresh_inbox()
        if callable(self.on_rules_changed):
            self.on_rules_changed()

        if success:
            sim_prefix = "[SIMULATION] No changes were made to Outlook.\n\n" if self.outlook.is_simulated() else ""
            messagebox.showinfo(
                "Sync Complete",
                f"{sim_prefix}"
                f"Successfully applied {count} actions!\n"
                f"Created {new_rules_count} new rules, updated {add_rules_count} rules.\n"
                f"Outlook native rules are now synchronized."
                f"{mismatch_txt}"
            )
        else:
            messagebox.showwarning("Notice", f"Updated YAML, but Outlook sync returned:\n{msg}{mismatch_txt}")
