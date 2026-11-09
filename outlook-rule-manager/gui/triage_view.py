"""Triage Workspace: Dual Canvas Studio (Concept 1).

A modern, highly visual 2-canvas workspace:
- Left Canvas (40%): Expand/Collapse Rules & Stores Tree, Dedicated Drop Zone, Staged Changes Queue.
- Right Canvas (60%): Modern Card Deck with Avatars, Status Badges, Inline Preview Accordion, and 1-Click Staging.
- Bottom Floating Staging Dock: Real-time counter and 1-Click batch apply to Outlook.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import re
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass

from core.models import EmailMessage, RuleConfig
from core.yaml_manager import YamlConfigManager
from core.outlook_client import BaseOutlookClient
from core.sync_engine import SyncEngine


AVATAR_COLORS = ["#0284c7", "#16a34a", "#7c3aed", "#d97706", "#dc2626", "#0d9488", "#475569"]


def get_avatar_info(name: str, email: str) -> Tuple[str, str]:
    """Return initials (2 uppercase chars) and a deterministic theme color."""
    clean_name = re.sub(r'[\(\[\{].*?[\)\]\}]', '', name).strip()
    parts = clean_name.split() if clean_name else []
    if len(parts) >= 2:
        initials = (parts[0][0] + parts[-1][0]).upper()
    elif len(parts) == 1 and len(parts[0]) >= 2:
        initials = parts[0][:2].upper()
    elif email:
        initials = email[:2].upper()
    else:
        initials = "??"
    color = AVATAR_COLORS[abs(hash(email.lower())) % len(AVATAR_COLORS)]
    return initials, color


def suggest_rule_and_folder(sender_name: str, sender_email: str) -> Tuple[str, str]:
    """Smartly suggest rule name and target folder based on sender metadata."""
    generic_domains = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "company.com", "mail.com"}
    domain = sender_email.split("@")[1].lower() if "@" in sender_email else ""

    # Corporate domain (e.g. omron.com -> Omron, sato-automation.jp -> Sato Automation)
    if domain and domain not in generic_domains:
        core_domain = domain.split(".")[0]
        clean_domain = core_domain.replace("-", " ").replace("_", " ").title()
        folder_name = clean_domain.replace(" ", "_")
        return clean_domain, folder_name

    # Sender display name
    if sender_name:
        clean_name = re.sub(r'[\(\[\{].*?[\)\]\}]', '', sender_name).strip()
        if clean_name:
            clean_name = clean_name.title()
            folder_name = clean_name.replace(" ", "_")
            return clean_name, folder_name

    # Fallback to local part of email
    local = sender_email.split("@")[0].replace(".", " ").replace("_", " ").title()
    return local, local.replace(" ", "_")


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
    """Dual Canvas Studio: Modern Card Deck + Hierarchical Rule Tree + Staging Dock."""

    def __init__(self, parent, yaml_mgr: YamlConfigManager, outlook: BaseOutlookClient, sync_engine: SyncEngine):
        super().__init__(parent)
        self.yaml_mgr = yaml_mgr
        self.outlook = outlook
        self.sync_engine = sync_engine

        self.messages: List[EmailMessage] = []
        self.staged_actions: List[StagedAction] = []
        self.active_filter: str = "ALL"  # 'ALL', 'UNTRACKED', 'STAGED'
        self.search_query: str = ""

        # Drag and Drop tracking
        self.drag_source_msg: Optional[EmailMessage] = None
        self.drag_window: Optional[tk.Toplevel] = None
        self.is_over_new_rule_zone = False

        # Card widgets map: entry_id -> { 'card_frame', 'body_frame', 'is_expanded' }
        self.card_widgets: Dict[str, Dict[str, Any]] = {}

        self._build_ui()
        self.refresh_inbox()

    def _build_ui(self):
        # -------------------------------------------------------------
        # TOP APP STRIP
        # -------------------------------------------------------------
        top_bar = tk.Frame(self, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=12, pady=8)
        top_bar.pack(fill=tk.X, side=tk.TOP)

        btn_refresh = ttk.Button(top_bar, text="Refresh Inbox", command=self.refresh_inbox)
        btn_refresh.pack(side=tk.LEFT, padx=(0, 8))

        btn_expand = ttk.Button(top_bar, text="Expand Tree", command=self._expand_all)
        btn_expand.pack(side=tk.LEFT, padx=2)

        btn_collapse = ttk.Button(top_bar, text="Collapse Tree", command=self._collapse_all)
        btn_collapse.pack(side=tk.LEFT, padx=2)

        self.lbl_stats = tk.Label(top_bar, text="Loading...", bg="#ffffff", fg="#475569", font=("", 9))
        self.lbl_stats.pack(side=tk.LEFT, padx=12)

        lbl_hint = tk.Label(
            top_bar,
            text="Dual Canvas: Drag any card to the Left Panel, or click [+ Quick Rule] to stage instantly.",
            bg="#ffffff",
            fg="#2563eb",
            font=("", 9, "italic")
        )
        lbl_hint.pack(side=tk.RIGHT)

        # -------------------------------------------------------------
        # MAIN PANED CONTAINER (2 CANVASES)
        # -------------------------------------------------------------
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # =============================================================
        # CANVAS 1 (LEFT 40%): RULES, STAGED QUEUE & DROP ZONES
        # =============================================================
        self.frame_left = tk.Frame(paned, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=8)
        paned.add(self.frame_left, weight=4)

        # 1. Dedicated Drop Target Banner (High Visual Affordance)
        self.drop_new_zone = tk.Frame(
            self.frame_left,
            bg="#f0fdf4",
            highlightbackground="#16a34a",
            highlightcolor="#16a34a",
            highlightthickness=2,
            padx=10,
            pady=10,
            cursor="hand2"
        )
        self.drop_new_zone.pack(fill=tk.X, pady=(0, 8))

        self.lbl_drop_title = tk.Label(
            self.drop_new_zone,
            text="[+] DROP HERE TO CREATE NEW RULE",
            bg="#f0fdf4",
            fg="#15803d",
            font=("", 10, "bold")
        )
        self.lbl_drop_title.pack()

        self.lbl_drop_sub = tk.Label(
            self.drop_new_zone,
            text="Auto-suggests rule & folder name. Instant staging (no popups).",
            bg="#f0fdf4",
            fg="#166534",
            font=("", 8)
        )
        self.lbl_drop_sub.pack(pady=(2, 0))

        # 2. Section Header
        lbl_rules_hdr = tk.Label(
            self.frame_left,
            text="Rules & Stores Hierarchy (Drop target):",
            bg="#f8fafc",
            fg="#334155",
            font=("", 9, "bold")
        )
        lbl_rules_hdr.pack(anchor=tk.W, pady=(4, 2))

        # 3. Hierarchy Treeview
        tree_container = ttk.Frame(self.frame_left)
        tree_container.pack(fill=tk.BOTH, expand=True)

        self.tree_rules = ttk.Treeview(
            tree_container,
            columns=("Details",),
            show="tree headings",
            selectmode="browse"
        )
        self.tree_rules.heading("#0", text="Rules & Staged Changes")
        self.tree_rules.heading("Details", text="Target Folder")
        self.tree_rules.column("#0", width=220)
        self.tree_rules.column("Details", width=110)

        rules_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree_rules.yview)
        self.tree_rules.configure(yscrollcommand=rules_scroll.set)
        self.tree_rules.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rules_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree_rules.bind("<Delete>", self._on_tree_delete_staged)

        # =============================================================
        # CANVAS 2 (RIGHT 60%): SMART INBOX CARD DECK
        # =============================================================
        self.frame_right = tk.Frame(paned, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=8)
        paned.add(self.frame_right, weight=6)

        # Filter & Search Strip
        filter_strip = tk.Frame(self.frame_right, bg="#f8fafc")
        filter_strip.pack(fill=tk.X, pady=(0, 6))

        # Filter Buttons
        self.btn_filter_all = tk.Button(
            filter_strip,
            text="All (0)",
            relief="flat",
            bg="#0284c7",
            fg="#ffffff",
            font=("", 8, "bold"),
            padx=8,
            pady=2,
            command=lambda: self._set_filter("ALL")
        )
        self.btn_filter_all.pack(side=tk.LEFT, padx=2)

        self.btn_filter_untracked = tk.Button(
            filter_strip,
            text="Need Rules (0)",
            relief="flat",
            bg="#e2e8f0",
            fg="#334155",
            font=("", 8, "bold"),
            padx=8,
            pady=2,
            command=lambda: self._set_filter("UNTRACKED")
        )
        self.btn_filter_untracked.pack(side=tk.LEFT, padx=2)

        self.btn_filter_staged = tk.Button(
            filter_strip,
            text="Staged (0)",
            relief="flat",
            bg="#e2e8f0",
            fg="#334155",
            font=("", 8, "bold"),
            padx=8,
            pady=2,
            command=lambda: self._set_filter("STAGED")
        )
        self.btn_filter_staged.pack(side=tk.LEFT, padx=2)

        # Search box
        self.ent_search = ttk.Entry(filter_strip, width=22)
        self.ent_search.pack(side=tk.RIGHT, padx=2)
        self.ent_search.bind("<KeyRelease>", self._on_search_change)
        tk.Label(filter_strip, text="Search:", bg="#f8fafc", fg="#64748b", font=("", 8)).pack(side=tk.RIGHT, padx=2)

        # Scrollable Cards Canvas
        cards_outer = tk.Frame(self.frame_right, bg="#f1f5f9", highlightbackground="#cbd5e1", highlightthickness=1)
        cards_outer.pack(fill=tk.BOTH, expand=True)

        self.canvas_cards = tk.Canvas(cards_outer, bg="#f8fafc", highlightthickness=0)
        self.scroll_cards = ttk.Scrollbar(cards_outer, orient=tk.VERTICAL, command=self.canvas_cards.yview)
        self.canvas_cards.configure(yscrollcommand=self.scroll_cards.set)

        self.cards_inner = tk.Frame(self.canvas_cards, bg="#f8fafc")
        self.cards_window = self.canvas_cards.create_window((0, 0), window=self.cards_inner, anchor="nw")

        self.canvas_cards.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scroll_cards.pack(side=tk.RIGHT, fill=tk.Y)

        self.cards_inner.bind("<Configure>", lambda e: self.canvas_cards.configure(scrollregion=self.canvas_cards.bbox("all")))
        self.canvas_cards.bind("<Configure>", lambda e: self.canvas_cards.itemconfig(self.cards_window, width=e.width))

        # Mousewheel binding
        self.canvas_cards.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas_cards.bind_all("<Button-4>", lambda e: self.canvas_cards.yview_scroll(-1, "units"))
        self.canvas_cards.bind_all("<Button-5>", lambda e: self.canvas_cards.yview_scroll(1, "units"))

        # =============================================================
        # BOTTOM FLOATING STAGING DOCK (HIGH CONTRAST BATCH ACTION BAR)
        # =============================================================
        self.dock_frame = tk.Frame(
            self,
            bg="#0f172a",
            highlightbackground="#334155",
            highlightthickness=1,
            padx=16,
            pady=10
        )
        self.dock_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 6))

        # Left status of dock
        dock_left = tk.Frame(self.dock_frame, bg="#0f172a")
        dock_left.pack(side=tk.LEFT)

        self.lbl_dock_indicator = tk.Label(
            dock_left,
            text="●",
            bg="#0f172a",
            fg="#94a3b8",
            font=("", 12)
        )
        self.lbl_dock_indicator.pack(side=tk.LEFT, padx=(0, 6))

        self.lbl_dock_status = tk.Label(
            dock_left,
            text="Ready: No pending changes. Drag cards to stage new rules or assignments.",
            bg="#0f172a",
            fg="#f8fafc",
            font=("", 9, "bold")
        )
        self.lbl_dock_status.pack(side=tk.LEFT)

        # Right actions of dock
        dock_right = tk.Frame(self.dock_frame, bg="#0f172a")
        dock_right.pack(side=tk.RIGHT)

        self.btn_dock_clear = tk.Button(
            dock_right,
            text="Discard All",
            relief="flat",
            bg="#334155",
            fg="#e2e8f0",
            activebackground="#475569",
            activeforeground="#ffffff",
            font=("", 9),
            padx=10,
            pady=4,
            state=tk.DISABLED,
            command=self._clear_all_staged
        )
        self.btn_dock_clear.pack(side=tk.LEFT, padx=4)

        self.btn_dock_apply = tk.Button(
            dock_right,
            text="Apply & Sync All to Outlook (0)",
            relief="flat",
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            activeforeground="#ffffff",
            font=("", 9, "bold"),
            padx=14,
            pady=4,
            state=tk.DISABLED,
            command=self._apply_all_staged
        )
        self.btn_dock_apply.pack(side=tk.LEFT, padx=4)

    def _on_mousewheel(self, event):
        # Support Windows mousewheel
        if event.delta:
            self.canvas_cards.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # -----------------------------------------------------------------
    # FILTER & SEARCH
    # -----------------------------------------------------------------
    def _set_filter(self, filter_name: str):
        self.active_filter = filter_name

        # Update button colors
        for name, btn in [
            ("ALL", self.btn_filter_all),
            ("UNTRACKED", self.btn_filter_untracked),
            ("STAGED", self.btn_filter_staged)
        ]:
            if name == filter_name:
                btn.config(bg="#0284c7", fg="#ffffff")
            else:
                btn.config(bg="#e2e8f0", fg="#334155")

        self._render_cards()

    def _on_search_change(self, event):
        self.search_query = self.ent_search.get().strip().lower()
        self._render_cards()

    # -----------------------------------------------------------------
    # REFRESH & DATA POPULATION
    # -----------------------------------------------------------------
    def refresh_inbox(self):
        """Fetch latest messages from Outlook and re-render both canvases."""
        self.messages = self.outlook.get_inbox_messages(limit=50)
        self.refresh_rules_tree()
        self._render_cards()
        self._update_dock()

    def refresh_rules_tree(self):
        """Populate hierarchical rule tree with Expand/Collapse support."""
        self.tree_rules.delete(*self.tree_rules.get_children())

        # Category 1: PENDING STAGED CHANGES
        staged_count = len(self.staged_actions)
        staged_title = f"★ PENDING CHANGES ({staged_count} to confirm)"
        self.tree_rules.insert(
            "",
            tk.END,
            iid="__STAGED__",
            text=staged_title,
            values=("Batch review below",),
            open=True
        )

        for idx, action in enumerate(self.staged_actions):
            item_id = f"staged_{idx}"
            if action.action_type == "create_rule":
                label = f"[+ New Rule] {action.rule_name}"
                info = f"{action.target_folder} ({action.sender_email})"
            else:
                label = f"[+ Add] {action.rule_name}"
                info = f"Add: {action.sender_email}"

            self.tree_rules.insert(
                "__STAGED__",
                tk.END,
                iid=item_id,
                text=label,
                values=(info,)
            )

        # Category 2: ACTIVE RULES (WITH EXPANDABLE MEMBERS)
        self.tree_rules.insert(
            "",
            tk.END,
            iid="__ACTIVE__",
            text="▼ ACTIVE RULES IN OUTLOOK",
            values=("Target Folder",),
            open=True
        )

        for rule in self.yaml_mgr.rules:
            prefix = "[ON]" if rule.enabled else "[OFF]"
            rule_node = f"rule_{rule.id}"
            folder_info = rule.target_folder or "(Root)"

            self.tree_rules.insert(
                "__ACTIVE__",
                tk.END,
                iid=rule_node,
                text=f"{prefix} {rule.name}",
                values=(folder_info,),
                open=False  # Collapsed by default for clean look
            )

            all_emails = self.yaml_mgr.get_all_emails_for_rule(rule)
            all_domains = self.yaml_mgr.get_all_domains_for_rule(rule)

            for d in all_domains:
                self.tree_rules.insert(rule_node, tk.END, text=f"  domain: {d}", values=("Domain Rule",))
            for e in all_emails:
                self.tree_rules.insert(rule_node, tk.END, text=f"  {e}", values=("Member Email",))

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
    # RENDER EMAIL CARDS (INBOX CANVAS)
    # -----------------------------------------------------------------
    def _render_cards(self):
        """Dynamically render email cards based on active filter and search query."""
        # Clear existing cards
        for widget in self.cards_inner.winfo_children():
            widget.destroy()
        self.card_widgets.clear()

        staged_map = {a.message_id: a for a in self.staged_actions}

        # Filter messages
        filtered_msgs: List[EmailMessage] = []
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

            # Match search query
            if self.search_query:
                q = self.search_query
                in_sender = q in msg.sender_name.lower() or q in msg.sender_email.lower()
                in_subj = q in msg.subject.lower()
                if not (in_sender or in_subj):
                    continue

            # Match category filter
            if self.active_filter == "UNTRACKED" and not is_untracked:
                continue
            if self.active_filter == "STAGED" and not is_staged:
                continue

            filtered_msgs.append(msg)

        # Update Filter Button Counts
        self.btn_filter_all.config(text=f"All ({len(self.messages)})")
        self.btn_filter_untracked.config(text=f"Need Rules ({untracked_count})")
        self.btn_filter_staged.config(text=f"Staged ({staged_count})")

        self.lbl_stats.config(
            text=f"Showing {len(filtered_msgs)} of {len(self.messages)} emails"
        )

        if not filtered_msgs:
            no_card = tk.Label(
                self.cards_inner,
                text="No emails match the current filter or search.",
                bg="#f8fafc",
                fg="#94a3b8",
                font=("", 10, "italic"),
                pady=40
            )
            no_card.pack()
            return

        # Render each email card
        for msg in filtered_msgs:
            self._create_email_card(msg, staged_map.get(msg.entry_id))

    def _create_email_card(self, msg: EmailMessage, staged_action: Optional[StagedAction]):
        """Build an interactive, modern email card widget."""
        is_staged = staged_action is not None
        matched_rule, _ = self.sync_engine.match_message(msg.sender_email, msg.subject)

        # Border color & badge based on status
        if is_staged:
            card_border = "#f59e0b"   # Amber
            status_text = f"★ Staged -> {staged_action.rule_name}"
            status_bg = "#fef3c7"
            status_fg = "#92400e"
        elif matched_rule:
            card_border = "#e2e8f0"
            status_text = f"Matches: {matched_rule.name}"
            status_bg = "#dcfce7"
            status_fg = "#166534"
        else:
            card_border = "#f87171"   # Reddish
            status_text = "Needs Rule"
            status_bg = "#fee2e2"
            status_fg = "#991b1b"

        # Outer Card Container
        card = tk.Frame(
            self.cards_inner,
            bg="#ffffff",
            highlightbackground=card_border,
            highlightthickness=2 if is_staged else 1,
            padx=10,
            pady=8,
            cursor="hand2"
        )
        card.pack(fill=tk.X, padx=6, pady=4)

        # Row 1: Avatar + Sender Name + Email + Time + Status Badge
        row1 = tk.Frame(card, bg="#ffffff")
        row1.pack(fill=tk.X)

        initials, avatar_bg = get_avatar_info(msg.sender_name, msg.sender_email)
        lbl_avatar = tk.Label(
            row1,
            text=initials,
            bg=avatar_bg,
            fg="#ffffff",
            font=("", 9, "bold"),
            width=3,
            pady=2
        )
        lbl_avatar.pack(side=tk.LEFT, padx=(0, 8))

        sender_disp = msg.sender_name if msg.sender_name else msg.sender_email
        lbl_sender = tk.Label(
            row1,
            text=sender_disp,
            bg="#ffffff",
            fg="#0f172a",
            font=("", 9, "bold")
        )
        lbl_sender.pack(side=tk.LEFT)

        if msg.sender_name and msg.sender_email:
            lbl_email = tk.Label(
                row1,
                text=f"<{msg.sender_email}>",
                bg="#ffffff",
                fg="#64748b",
                font=("", 8)
            )
            lbl_email.pack(side=tk.LEFT, padx=(4, 0))

        # Right side of Row 1: Time & Badge
        lbl_status = tk.Label(
            row1,
            text=f" {status_text} ",
            bg=status_bg,
            fg=status_fg,
            font=("", 8, "bold"),
            padx=4,
            pady=1
        )
        lbl_status.pack(side=tk.RIGHT, padx=(6, 0))

        time_str = msg.received_time.strftime("%m-%d %H:%M")
        lbl_time = tk.Label(
            row1,
            text=time_str,
            bg="#ffffff",
            fg="#94a3b8",
            font=("", 8)
        )
        lbl_time.pack(side=tk.RIGHT)

        # Row 2: Subject Line
        subj_disp = msg.subject if msg.subject else "(No Subject)"
        lbl_subj = tk.Label(
            card,
            text=subj_disp,
            bg="#ffffff",
            fg="#1e293b",
            font=("", 9),
            anchor=tk.W,
            justify=tk.LEFT
        )
        lbl_subj.pack(fill=tk.X, pady=(4, 6))

        # Row 3: Action Buttons & Expand Preview Toggle
        row3 = tk.Frame(card, bg="#ffffff")
        row3.pack(fill=tk.X)

        btn_toggle_preview = tk.Button(
            row3,
            text="View Content ▼",
            relief="flat",
            bg="#f1f5f9",
            fg="#475569",
            font=("", 8),
            padx=6,
            pady=2,
            command=lambda m=msg: self._toggle_card_preview(m.entry_id)
        )
        btn_toggle_preview.pack(side=tk.LEFT, padx=(0, 4))

        # 1-Click Quick Action: Stage New Rule
        btn_quick_new = tk.Button(
            row3,
            text="+ Quick New Rule",
            relief="flat",
            bg="#ecfdf5",
            fg="#047857",
            activebackground="#d1fae5",
            font=("", 8, "bold"),
            padx=6,
            pady=2,
            command=lambda m=msg: self._stage_create_new_rule(m)
        )
        btn_quick_new.pack(side=tk.LEFT, padx=4)

        # 1-Click Quick Action: Assign to Existing Rule Menu
        mb_assign = tk.Menubutton(
            row3,
            text="Assign to Rule... ▼",
            relief="flat",
            bg="#eff6ff",
            fg="#1d4ed8",
            activebackground="#dbeafe",
            font=("", 8),
            padx=6,
            pady=2
        )
        menu_rules = tk.Menu(mb_assign, tearoff=0)
        for r in self.yaml_mgr.rules:
            menu_rules.add_command(
                label=f"{r.name} ({r.target_folder or 'Root'})",
                command=lambda m=msg, rid=r.id: self._stage_add_to_existing_rule(m, rid)
            )
        mb_assign.config(menu=menu_rules)
        mb_assign.pack(side=tk.LEFT, padx=4)

        # Collapsible Body Preview Frame inside the Card
        frame_body = tk.Frame(card, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=6)
        txt_body = tk.Text(frame_body, wrap=tk.WORD, height=4, font=("Consolas", 8), bg="#f8fafc", relief="flat")
        txt_body.insert(tk.END, msg.body if msg.body else "(Empty email body)")
        txt_body.config(state=tk.DISABLED)
        txt_body.pack(fill=tk.BOTH, expand=True)

        # Store widgets reference
        self.card_widgets[msg.entry_id] = {
            "card": card,
            "body_frame": frame_body,
            "btn_toggle": btn_toggle_preview,
            "is_expanded": False
        }

        # Bind Drag events to Card and its labels
        for widget in [card, row1, lbl_avatar, lbl_sender, lbl_subj]:
            widget.bind("<ButtonPress-1>", lambda e, m=msg: self._on_card_drag_start(e, m))
            widget.bind("<B1-Motion>", self._on_card_drag_motion)
            widget.bind("<ButtonRelease-1>", self._on_card_drag_release)

    def _toggle_card_preview(self, entry_id: str):
        """Smoothly expand or collapse the email body inside the card."""
        info = self.card_widgets.get(entry_id)
        if not info:
            return

        if info["is_expanded"]:
            info["body_frame"].pack_forget()
            info["btn_toggle"].config(text="View Content ▼")
            info["is_expanded"] = False
        else:
            info["body_frame"].pack(fill=tk.BOTH, expand=True, pady=(6, 2))
            info["btn_toggle"].config(text="Hide Content ▲")
            info["is_expanded"] = True

    # -----------------------------------------------------------------
    # FAST CARD DRAG & DROP LOGIC
    # -----------------------------------------------------------------
    def _on_card_drag_start(self, event, msg: EmailMessage):
        self.drag_source_msg = msg

        if not self.drag_window:
            self.drag_window = tk.Toplevel(self)
            self.drag_window.wm_overrideredirect(True)
            self.drag_window.attributes("-topmost", True)

            lbl = tk.Label(
                self.drag_window,
                text=f" ✉ {msg.sender_email} ➔ Release on Left Canvas ",
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

    def _on_card_drag_motion(self, event):
        if not self.drag_window:
            return

        self.drag_window.geometry(f"+{event.x_root + 15}+{event.y_root + 15}")

        # Check hover over "DROP HERE TO CREATE NEW RULE" zone
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

        # Highlight tree node if hovering over existing rule
        rx = event.x_root - self.tree_rules.winfo_rootx()
        ry = event.y_root - self.tree_rules.winfo_rooty()
        if 0 <= rx <= self.tree_rules.winfo_width() and 0 <= ry <= self.tree_rules.winfo_height():
            hover_id = self.tree_rules.identify_row(ry)
            if hover_id and hover_id.startswith("rule_"):
                self.tree_rules.selection_set(hover_id)

    def _on_card_drag_release(self, event):
        if self.drag_window:
            self.drag_window.destroy()
            self.drag_window = None

        if self.is_over_new_rule_zone:
            self.is_over_new_rule_zone = False
            self.drop_new_zone.config(bg="#f0fdf4", highlightbackground="#16a34a")
            self.lbl_drop_title.config(bg="#f0fdf4", fg="#15803d", text="[+] DROP HERE TO CREATE NEW RULE")
            self.lbl_drop_sub.config(bg="#f0fdf4", fg="#166534")

        if not self.drag_source_msg:
            return

        msg = self.drag_source_msg

        # Drop Target 1: "CREATE NEW RULE" Drop Zone
        zx = event.x_root - self.drop_new_zone.winfo_rootx()
        zy = event.y_root - self.drop_new_zone.winfo_rooty()
        if 0 <= zx <= self.drop_new_zone.winfo_width() and 0 <= zy <= self.drop_new_zone.winfo_height():
            self._stage_create_new_rule(msg)
            self.drag_source_msg = None
            return

        # Drop Target 2: Existing Rule in Treeview
        rx = event.x_root - self.tree_rules.winfo_rootx()
        ry = event.y_root - self.tree_rules.winfo_rooty()
        if 0 <= rx <= self.tree_rules.winfo_width() and 0 <= ry <= self.tree_rules.winfo_height():
            target_id = self.tree_rules.identify_row(ry)
            if target_id and target_id.startswith("rule_"):
                raw_rule_id = target_id.replace("rule_", "", 1)
                self._stage_add_to_existing_rule(msg, raw_rule_id)

        self.drag_source_msg = None

    # -----------------------------------------------------------------
    # STAGING ENGINE (FAST, ZERO POPUPS)
    # -----------------------------------------------------------------
    def _stage_create_new_rule(self, msg: EmailMessage):
        suggested_name, suggested_folder = suggest_rule_and_folder(msg.sender_name, msg.sender_email)
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
            target_folder=suggested_folder,
            sender_email=sender_email,
            sender_domain=sender_domain,
            match_mode=match_mode,
            message_id=msg.entry_id,
            subject=msg.subject
        )
        self.staged_actions.append(action)

        self.refresh_rules_tree()
        self._render_cards()
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
        self._render_cards()
        self._update_dock()

    def _on_tree_delete_staged(self, event):
        sel = self.tree_rules.selection()
        if not sel or not sel[0].startswith("staged_"):
            return
        idx = int(sel[0].split("_")[1])
        if 0 <= idx < len(self.staged_actions):
            self.staged_actions.pop(idx)
            self.refresh_rules_tree()
            self._render_cards()
            self._update_dock()

    def _clear_all_staged(self):
        self.staged_actions.clear()
        self.refresh_rules_tree()
        self._render_cards()
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
                text="Ready: No pending changes. Drag cards to stage new rules or assignments.",
                fg="#94a3b8"
            )
            self.btn_dock_apply.config(
                state=tk.DISABLED,
                text="Apply & Sync All to Outlook (0)"
            )
            self.btn_dock_clear.config(state=tk.DISABLED)

    # -----------------------------------------------------------------
    # BATCH APPLY TO OUTLOOK
    # -----------------------------------------------------------------
    def _apply_all_staged(self):
        if not self.staged_actions:
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
