r"""Rule and Folder Management View with Dynamic Arbitrary Folder Hierarchy & Drag-and-Drop Reorganization."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os
import re
from typing import Optional, List, Tuple, Dict, Any

from gui.quick_rule_dialog import rule_name_from_folder
from core.models import RuleConfig, pluralize_count, MANAGED_PREFIX
from core.yaml_manager import YamlConfigManager
from core.sync_engine import SyncEngine


class RuleManagerView(ttk.Frame):
    r"""Intuitive Studio for Outlook Rules and Dynamic Folders (arbitrary levels) with Drag-and-Drop."""

    def __init__(
        self,
        parent,
        yaml_mgr: YamlConfigManager,
        sync_engine: SyncEngine,
        nav_host: Optional[tk.Misc] = None,
        inspector_host: Optional[tk.Misc] = None,
    ):
        super().__init__(parent)
        self.yaml_mgr = yaml_mgr
        self.sync_engine = sync_engine
        # Integrated (single-screen) mode: the navigator and the inspector are built into
        # containers owned by the main window instead of this frame's own 2-pane layout.
        self.nav_host = nav_host
        self.inspector_host = inspector_host
        self.integrated = nav_host is not None and inspector_host is not None
        self.on_item_activated = None  # integrated mode: called when the user picks a tree item

        # Selection state
        self.selected_rule: Optional[RuleConfig] = None
        self.selected_folder_path: Optional[str] = None
        self.selected_pool_item: Optional[str] = None

        # Dirty-tracking & programmatic tree refresh guards
        self.var_rule_enabled = tk.BooleanVar(value=True)
        self._populating_inspector: bool = False
        self._in_tree_transition: bool = False
        self._current_selected_iid: Optional[str] = None

        # Button styles (Accent / DirtySave / Danger) are defined centrally in gui/styles.py

        # Drag-and-drop state
        self.drag_source_id: Optional[str] = None
        self.drag_start_x: int = 0
        self.drag_start_y: int = 0
        self.is_dragging: bool = False
        self.drag_window: Optional[tk.Toplevel] = None

        # Search filter
        self.search_query: str = ""

        # Mapping of tree iid to folder path / rule id
        self.folder_nodes_map: Dict[str, str] = {}
        self.rule_nodes_map: Dict[str, str] = {}  # iid -> rule_id
        # Mails (inbox) shown under the rule they go to. Wired by MainWindow.
        self.mail_provider = None      # () -> {rule_id: [(EmailMessage, staged: bool), ...]}
        self.on_mail_selected = None   # (entry_id) -> None
        self.on_mail_dropped = None    # (entry_id, target_iid, whole_domain) -> None
        self._mail_node_ids: List[str] = []
        self._pending_nodes: Dict[str, str] = {}  # "pending::<folder>" -> folder path (new rule awaiting Apply)
        self.pending_provider = None   # () -> {folder: (rule_name, [EmailMessage, ...])}
        self._drop_hover_iid: Optional[str] = None
        self._drop_ctrl: bool = False

        # Scrollable inspector canvases + single shared mousewheel handler
        self._scrollable_canvases: List[tk.Canvas] = []
        self._mousewheel_bound: bool = False
        self._toast_after_id: Optional[str] = None

        self._build_ui()
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.var_rule_enabled.trace_add("write", lambda *_: self._refresh_dirty_state())
        self.refresh_all()

    # =================================================================
    # UI CONSTRUCTION
    # =================================================================
    def _build_ui(self):
        # -------------------------------------------------------------
        # TOP TOOLBAR: Dynamic Actions, Search, & Drag Hint
        # -------------------------------------------------------------
        host = self.nav_host if self.integrated else self
        toolbar = tk.Frame(host, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=10, pady=6)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        # Merged creation menu + tree controls
        self.mb_new = ttk.Menubutton(toolbar, text="New")
        self.menu_new = tk.Menu(self.mb_new, tearoff=0)
        self.menu_new.add_command(label="Rule", command=self._add_rule_in_selected_folder)
        self.menu_new.add_command(label="Folder", command=self._add_root_folder)
        self.menu_new.add_command(label="Subfolder", command=self._add_subfolder)
        self.mb_new.config(menu=self.menu_new)
        self.mb_new.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)

        ttk.Button(toolbar, text="Expand", command=self._expand_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Collapse", command=self._collapse_all).pack(side=tk.LEFT, padx=2)

        # Search filter entry (own row in the narrow integrated navigator)
        filter_parent = toolbar
        if self.integrated:
            filter_parent = tk.Frame(host, bg="#ffffff", padx=10, pady=4)
            filter_parent.pack(fill=tk.X, side=tk.TOP)
        self.ent_search = ttk.Entry(filter_parent, width=22)
        self.ent_search.pack(side=tk.RIGHT, padx=4, fill=tk.X, expand=self.integrated)
        self.ent_search.bind("<KeyRelease>", lambda e: self._on_search_change())
        tk.Label(filter_parent, text="Filter:", bg="#ffffff", fg="#475569", font=("", 9, "bold")).pack(side=tk.RIGHT, padx=2)

        # Bottom tip / status bar packed BEFORE paned so text is never clipped at 1120x720
        self._default_tip_text = (
            "Tip: drag rules or folders to reorganize. Right-click for more actions."
        )
        tip_bar = tk.Frame(host, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=4)
        tip_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=(0, 6))
        # Undo lives next to the status text so the "Moved …" message and its Undo sit together
        self.btn_undo = ttk.Button(tip_bar, text="Undo (Ctrl+Z)", state=tk.DISABLED, command=self._request_undo)
        self.btn_undo.pack(side=tk.RIGHT, padx=(8, 0))
        self.on_undo_request = None  # set by MainWindow
        self.lbl_toast = tk.Label(
            tip_bar,
            text=self._default_tip_text,
            bg="#f8fafc",
            fg="#475569",
            font=("", 8, "italic"),
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=200 if self.integrated else 1080,
        )
        self.lbl_toast.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tip_bar.bind("<Configure>", lambda e: self.lbl_toast.config(wraplength=max(200, e.width - 140)))

        # -------------------------------------------------------------
        # MAIN 2-PANE WORKSPACE: Tree (Left) + Studio Inspector (Right)
        # -------------------------------------------------------------
        if self.integrated:
            paned = None
            self.frame_left = tk.Frame(host, bg="#f8fafc", highlightbackground="#cbd5e1", highlightthickness=1)
            self.frame_left.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        else:
            paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
            paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

            # Left Pane: Visual Dynamic Folder & Rule Tree
            self.frame_left = tk.Frame(paned, bg="#f8fafc", highlightbackground="#cbd5e1", highlightthickness=1)
            paned.add(self.frame_left, weight=4)

        # Left header banner
        tree_header = tk.Frame(self.frame_left, bg="#f1f5f9", padx=8, pady=6)
        tree_header.pack(fill=tk.X)
        tk.Label(
            tree_header,
            text="Navigator",
            bg="#f1f5f9",
            fg="#334155",
            font=("", 9, "bold")
        ).pack(side=tk.LEFT)

        # Treeview widget with Scrollbar
        tree_container = ttk.Frame(self.frame_left)
        tree_container.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.tree = ttk.Treeview(
            tree_container,
            columns=("Details",),
            show="tree headings",
            selectmode="browse"
        )
        self.tree.tag_configure("rule_enabled", foreground="#0f172a")
        self.tree.tag_configure("rule_disabled", foreground="#94a3b8", font=("", 9, "italic"))
        self.tree.tag_configure("mail", foreground="#475569")
        self.tree.tag_configure("mail_staged", foreground="#0284c7", font=("", 9, "italic"))
        self.tree.tag_configure("drop_hover", background="#bae6fd")
        self.tree.heading("#0", text="Folder Hierarchy")
        self.tree.heading("Details", text="Level / Senders")
        self.tree.column("#0", width=260)
        self.tree.column("Details", width=120)

        tree_scroll_y = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # Treeview event bindings
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<ButtonPress-1>", self._on_drag_start)
        self.tree.bind("<B1-Motion>", self._on_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_drag_release)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Double-Button-1>", self._on_tree_double_click)
        self.tree.bind("<Delete>", lambda e: self._on_delete_key())
        self.tree.bind("<F2>", lambda e: self._on_rename_key())
        # Integrated mode: clicking/keying through the tree shows the inspector in the shared right pane
        self.tree.bind("<ButtonRelease-1>", self._notify_item_activated, add="+")
        self.tree.bind("<KeyRelease-Up>", self._notify_item_activated, add="+")
        self.tree.bind("<KeyRelease-Down>", self._notify_item_activated, add="+")
        if self.integrated:
            # Names need the room (folder (rule: …) > mail); Info only holds a short count/date
            self.tree.column("#0", width=230, stretch=True)
            self.tree.column("Details", width=128, minwidth=50, stretch=False)
            self.tree.heading("#0", text="Folders & Rules")
            self.tree.heading("Details", text="Info")

        # -------------------------------------------------------------
        # Right Pane: Studio Inspector Card
        # -------------------------------------------------------------
        if self.integrated:
            self.frame_right = tk.Frame(self.inspector_host, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1)
            self.frame_right.pack(fill=tk.BOTH, expand=True)
        else:
            self.frame_right = tk.Frame(paned, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1)
            paned.add(self.frame_right, weight=6)

        self.inspector_container = tk.Frame(self.frame_right, bg="#ffffff")
        self.inspector_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)

        # Sub-inspectors
        self.frame_empty = tk.Frame(self.inspector_container, bg="#ffffff")
        self.frame_rule = tk.Frame(self.inspector_container, bg="#ffffff")
        self.frame_folder = tk.Frame(self.inspector_container, bg="#ffffff")
        self.frame_pool = tk.Frame(self.inspector_container, bg="#ffffff")

        self._build_empty_inspector()
        self._build_rule_inspector()
        self._build_folder_inspector()
        self._build_pool_inspector()

        # Show empty inspector initially
        self._show_inspector(self.frame_empty)

    # -----------------------------------------------------------------
    # SUB-INSPECTOR BUILDERS
    # -----------------------------------------------------------------
    def _build_empty_inspector(self):
        box = tk.Frame(self.frame_empty, bg="#ffffff")
        box.pack(expand=True)
        tk.Label(box, text="Select a Folder or Rule", font=("", 12, "bold"), fg="#64748b", bg="#ffffff").pack(pady=4)
        tk.Label(
            box,
            text="Use the visual navigator on the left to browse and edit hierarchy.\n"
                 "Flexible levels: Drag any folder to Root for Level 1, or drop into any folder for Level 2, 3, 4...",
            font=("", 9), fg="#94a3b8", bg="#ffffff", justify=tk.CENTER
        ).pack(pady=4)

    def _create_scrollable_section(self, parent: tk.Misc, bg: str = "#ffffff") -> Tuple[tk.Canvas, tk.Frame]:
        """Build a vertically scrollable Canvas+Scrollbar container and return (canvas, inner_frame)."""
        canvas = tk.Canvas(parent, bg=bg, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = tk.Frame(canvas, bg=bg)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfigure(window_id, width=event.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        self._scrollable_canvases.append(canvas)
        if not self._mousewheel_bound:
            self.bind_all("<MouseWheel>", self._on_scrollable_mousewheel, add="+")
            self._mousewheel_bound = True
        return canvas, inner

    def _on_scrollable_mousewheel(self, event):
        """Scroll whichever mapped inspector canvas contains the pointer."""
        if not self.winfo_exists():
            return
        widget = event.widget
        if not isinstance(widget, tk.Misc):
            try:
                widget = self.winfo_containing(event.x_root, event.y_root)
            except Exception:
                return
        if widget is None:
            return

        target_canvas = None
        curr = widget
        while curr is not None:
            if curr in self._scrollable_canvases and curr.winfo_exists() and curr.winfo_ismapped():
                target_canvas = curr
                break
            curr = getattr(curr, "master", None)
        if target_canvas is None:
            return

        if isinstance(widget, (tk.Text, tk.Listbox)):
            try:
                first, last = widget.yview()
                if not (first <= 0.0 and last >= 1.0):
                    return
            except Exception:
                pass

        first, last = target_canvas.yview()
        if first <= 0.0 and last >= 1.0:
            return

        step = -1 * int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
        target_canvas.yview_scroll(step, "units")

    def _build_rule_inspector(self):
        # 1. Breadcrumb Path Bar (Dynamic Levels)
        self.bar_breadcrumb = tk.Frame(self.frame_rule, bg="#f1f5f9", padx=8, pady=4, highlightbackground="#e2e8f0", highlightthickness=1)
        self.bar_breadcrumb.pack(fill=tk.X, pady=(0, 4))

        self.lbl_breadcrumb = tk.Label(
            self.bar_breadcrumb,
            text="Folder: Engineering_Team > SCADA_Part > PLC_Unit (Level 3)",
            bg="#f1f5f9",
            fg="#0369a1",
            font=("", 9, "bold")
        )
        self.lbl_breadcrumb.pack(side=tk.LEFT)

        ttk.Button(self.bar_breadcrumb, text="Change Folder...", command=self._open_folder_picker_dialog).pack(side=tk.RIGHT, padx=2)

        # 2. Rule Name & Active Status Card
        card_header = tk.Frame(self.frame_rule, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=5)
        card_header.pack(fill=tk.X, pady=(0, 4))

        row1 = tk.Frame(card_header, bg="#ffffff")
        row1.pack(fill=tk.X)

        tk.Label(row1, text="Rule Name:", bg="#ffffff", font=("", 9, "bold"), fg="#334155").pack(side=tk.LEFT, padx=(0, 6))
        self.lbl_rule_name = tk.Label(
            row1, text=MANAGED_PREFIX, bg="#ffffff", fg="#0284c7", font=("", 9, "bold"), anchor=tk.W
        )
        self.lbl_rule_name.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        enabled_box = tk.Frame(row1, bg="#ffffff")
        enabled_box.pack(side=tk.RIGHT)
        self.chk_rule_enabled = ttk.Checkbutton(enabled_box, text="Enabled", variable=self.var_rule_enabled)
        self.chk_rule_enabled.pack(side=tk.LEFT)
        tk.Label(
            enabled_box,
            text="(applies to Outlook on next Sync)",
            bg="#ffffff",
            fg="#64748b",
            font=("", 8),
        ).pack(side=tk.LEFT, padx=(4, 0))

        # Quota meter (live compiled preview)
        self.lbl_quota = tk.Label(
            card_header,
            text="Outlook: 0 senders, 0 domains, 0 keywords → 0 native rules",
            bg="#ffffff",
            fg="#16a34a",
            font=("", 8, "bold")
        )
        self.lbl_quota.pack(anchor=tk.W, pady=(4, 0))

        self.lbl_quota_subrules = tk.Label(
            card_header,
            text="",
            bg="#ffffff",
            fg="#475569",
            font=("", 8),
            wraplength=540,
            justify=tk.LEFT,
        )
        self.lbl_quota_subrules.pack(anchor=tk.W, pady=(1, 0))

        # Pack bottom footer & tester strip BEFORE middle scrollable content so they never overflow off-screen
        # 5. Rule Action Footer
        btn_bar_rule = tk.Frame(self.frame_rule, bg="#ffffff")
        btn_bar_rule.pack(fill=tk.X, side=tk.BOTTOM)

        self.btn_save_rule = ttk.Button(
            btn_bar_rule, text="Save Rule to YAML", style="Accent.TButton", command=self._save_rule_changes
        )
        self.btn_save_rule.pack(side=tk.LEFT, padx=2)

        ttk.Button(btn_bar_rule, text="Delete Rule", style="Danger.TButton", command=self._delete_selected).pack(side=tk.RIGHT, padx=2)

        # 4. Interactive Match Tester Strip
        tester_strip = tk.Frame(
            self.frame_rule, bg="#f8fafc", padx=6, pady=4, highlightbackground="#e2e8f0", highlightthickness=1
        )
        tester_strip.pack(fill=tk.X, side=tk.BOTTOM, pady=(0, 4))

        tk.Label(tester_strip, text="Test Match:", bg="#f8fafc", font=("", 8, "bold"), fg="#475569").pack(side=tk.LEFT, padx=(0, 4))
        tk.Label(tester_strip, text="Email:", bg="#f8fafc", font=("", 8), fg="#475569").pack(side=tk.LEFT)
        self.ent_test_match = ttk.Entry(tester_strip, width=18)
        self.ent_test_match.pack(side=tk.LEFT, padx=(2, 6))
        tk.Label(tester_strip, text="Subject:", bg="#f8fafc", font=("", 8), fg="#475569").pack(side=tk.LEFT)
        self.ent_test_subject = ttk.Entry(tester_strip, width=16)
        self.ent_test_subject.pack(side=tk.LEFT, padx=(2, 4))
        ttk.Button(tester_strip, text="Check", command=self._test_rule_match).pack(side=tk.LEFT, padx=2)
        self.lbl_test_result = tk.Label(tester_strip, text="", bg="#f8fafc", font=("", 8, "bold"))
        self.lbl_test_result.pack(side=tk.LEFT, padx=6)

        # 3. Recipients & Conditions (single text mode inside scrollable body)
        card_cond = tk.LabelFrame(self.frame_rule, text="Filter Conditions", bg="#ffffff", padx=8, pady=4)
        card_cond.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        self.rule_scroll_canvas, rule_cond_body = self._create_scrollable_section(card_cond, bg="#ffffff")

        # Emails (one per line) + Import button
        row_emails_hdr = tk.Frame(rule_cond_body, bg="#ffffff")
        row_emails_hdr.pack(fill=tk.X, pady=(0, 2))
        self.lbl_rule_emails_hdr = tk.Label(
            row_emails_hdr, text="Emails (0)", bg="#ffffff", font=("", 8, "bold"), fg="#475569"
        )
        self.lbl_rule_emails_hdr.pack(side=tk.LEFT)
        ttk.Button(row_emails_hdr, text="Import CSV/Excel...", command=self._import_addresses_to_rule).pack(side=tk.RIGHT)

        self.txt_emails = tk.Text(rule_cond_body, font=("Consolas", 9), height=6)
        self.txt_emails.pack(fill=tk.X, pady=(0, 6))
        self.txt_emails.bind("<KeyRelease>", self._on_rule_text_changed)
        self.txt_emails.bind("<FocusOut>", self._on_rule_text_changed)

        # Domains (one per line)
        self.lbl_rule_domains_hdr = tk.Label(
            rule_cond_body, text="Domains (0)", bg="#ffffff", font=("", 8, "bold"), fg="#475569"
        )
        self.lbl_rule_domains_hdr.pack(anchor=tk.W, pady=(0, 2))
        self.txt_domains = tk.Text(rule_cond_body, font=("Consolas", 9), height=3)
        self.txt_domains.pack(fill=tk.X, pady=(0, 6))
        self.txt_domains.bind("<KeyRelease>", self._on_rule_text_changed)
        self.txt_domains.bind("<FocusOut>", self._on_rule_text_changed)

        # Subject Keywords (one per line)
        self.lbl_rule_keywords_hdr = tk.Label(
            rule_cond_body, text="Subject Keywords (0)", bg="#ffffff", font=("", 8, "bold"), fg="#475569"
        )
        self.lbl_rule_keywords_hdr.pack(anchor=tk.W, pady=(0, 2))
        self.txt_keywords = tk.Text(rule_cond_body, font=("Consolas", 9), height=3)
        self.txt_keywords.pack(fill=tk.X, pady=(0, 4))
        self.txt_keywords.bind("<KeyRelease>", self._on_rule_text_changed)
        self.txt_keywords.bind("<FocusOut>", self._on_rule_text_changed)

    def _build_folder_inspector(self):
        # Folder Header Banner (Dynamic Level Display)
        header = tk.Frame(self.frame_folder, bg="#f1f5f9", padx=10, pady=8, highlightbackground="#e2e8f0", highlightthickness=1)
        header.pack(fill=tk.X, pady=(0, 8))

        self.lbl_folder_title = tk.Label(
            header,
            text="Folder: Engineering_Team \\ SCADA_Part \\ PLC_Unit",
            bg="#f1f5f9",
            fg="#0f172a",
            font=("", 11, "bold")
        )
        self.lbl_folder_title.pack(anchor=tk.W)

        self.lbl_folder_level = tk.Label(
            header,
            text="Level: Level 3",
            bg="#f1f5f9",
            fg="#0284c7",
            font=("", 8, "bold")
        )
        self.lbl_folder_level.pack(anchor=tk.W, pady=(2, 0))

        # Metrics Card
        metrics_box = tk.Frame(self.frame_folder, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=8)
        metrics_box.pack(fill=tk.X, pady=(0, 8))

        self.lbl_folder_stats = tk.Label(
            metrics_box,
            text="Rules: 1  |  Total Monitored Senders: 4",
            bg="#f8fafc",
            fg="#334155",
            font=("", 9, "bold")
        )
        self.lbl_folder_stats.pack(anchor=tk.W)

        # Rules inside this folder
        tk.Label(self.frame_folder, text="Rules in this Folder:", bg="#ffffff", font=("", 9, "bold"), fg="#334155").pack(anchor=tk.W, pady=(4, 2))

        self.tree_folder_rules = ttk.Treeview(self.frame_folder, columns=("Status", "Senders"), show="tree headings", height=8)
        self.tree_folder_rules.heading("#0", text="Rule Name")
        self.tree_folder_rules.heading("Status", text="Status")
        self.tree_folder_rules.heading("Senders", text="Senders")
        self.tree_folder_rules.column("#0", width=180)
        self.tree_folder_rules.column("Status", width=70)
        self.tree_folder_rules.column("Senders", width=80)
        self.tree_folder_rules.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.tree_folder_rules.bind("<Double-Button-1>", self._on_folder_rule_double_click)

        # Folder Actions Bar (Dynamic level management)
        self.btn_bar_folder = tk.Frame(self.frame_folder, bg="#ffffff")
        self.btn_bar_folder.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(self.btn_bar_folder, text="+ Add Rule Here", command=self._add_rule_in_selected_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.btn_bar_folder, text="+ Subfolder", command=self._add_subfolder).pack(side=tk.LEFT, padx=2)

        self.btn_promote_root = ttk.Button(self.btn_bar_folder, text="Move to Top Level", command=self._promote_selected_folder_to_root)
        self.btn_move_up = ttk.Button(self.btn_bar_folder, text="Move Up 1 Level", command=self._move_selected_folder_up)

        ttk.Button(self.btn_bar_folder, text="Rename", command=self._rename_selected_folder).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.btn_bar_folder, text="Delete Folder", style="Danger.TButton", command=self._delete_selected_folder).pack(side=tk.RIGHT, padx=2)

    def _build_pool_inspector(self):
        header = tk.Frame(self.frame_pool, bg="#fef2f2", padx=10, pady=8, highlightbackground="#fecaca", highlightthickness=1)
        header.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            header,
            text="Unclassified Pool (Orphaned Addresses)",
            bg="#fef2f2",
            fg="#991b1b",
            font=("", 11, "bold")
        ).pack(anchor=tk.W)

        tk.Label(
            header,
            text="Addresses removed from rules are kept here so incoming emails\n"
                 "are caught by the [Unclassified] rule instead of cluttering Inbox.",
            bg="#fef2f2",
            fg="#7f1d1d",
            font=("", 8)
        ).pack(anchor=tk.W, pady=(2, 0))

        # Pool listbox
        self.lst_pool = tk.Listbox(self.frame_pool, font=("Consolas", 9), selectmode=tk.EXTENDED)
        self.lst_pool.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        # Action bar
        btn_bar_pool = tk.Frame(self.frame_pool, bg="#ffffff")
        btn_bar_pool.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_bar_pool, text="Assign Selected to Rule...", command=self._assign_pool_to_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar_pool, text="Remove from Pool", command=self._remove_from_pool).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar_pool, text="Clear Entire Pool", style="Danger.TButton", command=self._clear_pool).pack(side=tk.RIGHT, padx=2)

    def _show_inspector(self, target_frame: tk.Frame):
        """Switch right pane to display the requested inspector."""
        for f in [self.frame_empty, self.frame_rule, self.frame_folder, self.frame_pool]:
            f.pack_forget()
        target_frame.pack(fill=tk.BOTH, expand=True)

    # =================================================================
    # TREE REFRESH & DYNAMIC HIERARCHY POPULATION (ARBITRARY DEPTH)
    # =================================================================
    def refresh_all(self, preserve_selection_iid: Optional[str] = None):
        """Rebuild the visual tree supporting arbitrary folder levels from YamlConfigManager."""
        self._in_tree_transition = True
        previous_open = {
            iid: bool(self.tree.item(iid, "open")) for iid in self.rule_nodes_map if self.tree.exists(iid)
        }
        try:
            self.tree.delete(*self.tree.get_children())
            self._mail_node_ids = []
            self._drop_hover_iid = None
            self.folder_nodes_map.clear()
            self.rule_nodes_map.clear()

            q = self.search_query.lower()

            # ---------------------------------------------------------
            # Category 1: Folders & Rules (Arbitrary Depth)
            # ---------------------------------------------------------
            root_hier_id = "__HIERARCHY__"
            self.tree.insert("", tk.END, iid=root_hier_id, text="Folders & Rules", values=("Root",), open=True)

            self._populate_hierarchy(root_hier_id, q, previous_open)

            # ---------------------------------------------------------
            # Category 2: Unclassified Pool
            # ---------------------------------------------------------
            root_pool_id = "__POOL__"
            pool_count = len(self.yaml_mgr.unclassified_pool)
            self.tree.insert("", tk.END, iid=root_pool_id, text=f"Unclassified Pool ({pool_count})", values=("Pool",), open=True)
            for email in self.yaml_mgr.unclassified_pool:
                if q and q not in email.lower():
                    continue
                pool_iid = f"pool_{email}"
                self.tree.insert(root_pool_id, tk.END, iid=pool_iid, text=f"📧 {email}", values=("Orphaned",))

            self._pending_nodes = {}
            self._insert_mail_nodes()
            self._insert_pending_rule_nodes()

            target_sel = preserve_selection_iid or self._current_selected_iid
            if target_sel and self.tree.exists(target_sel):
                self.tree.selection_set(target_sel)
        finally:
            self.update_idletasks()
            self._in_tree_transition = False

    @staticmethod
    def _split_path(path: str) -> List[str]:
        return [p.strip() for p in re.split(r'[\\/]', path or "") if p.strip()]

    @staticmethod
    def _folder_iid(path: str) -> str:
        return f"fld_{path.lower().replace(' ', '_')}"

    def _rule_matches_query(self, rule: RuleConfig, q: str) -> bool:
        if not q:
            return True
        all_emails, all_domains, keywords = self.sync_engine.get_rule_conditions(rule)
        return (
            q in rule.name.lower()
            or q in (rule.target_folder or "").lower()
            or any(q in e.lower() for e in all_emails)
            or any(q in d.lower() for d in all_domains)
            or any(q in kw.lower() for kw in keywords)
        )

    def _populate_hierarchy(self, root_iid: str, q: str, previous_open: Dict[str, bool]):
        """Folders of any depth; every folder with a rule is one merged node; subfolders sit below it."""
        unclassified = self.yaml_mgr.unclassified_folder()
        rules = [r for r in self.yaml_mgr.rules if self._rule_matches_query(r, q)]

        # Every folder path (and its parents), in display order
        ordered: List[str] = []
        seen = set()
        for path in self.yaml_mgr.get_all_folders() + [r.target_folder or unclassified for r in rules]:
            parts = self._split_path(path)
            for i in range(1, len(parts) + 1):
                sub = "\\".join(parts[:i])
                if sub.lower() not in seen:
                    seen.add(sub.lower())
                    ordered.append(sub)

        rules_by_folder: Dict[str, List[RuleConfig]] = {}
        for rule in rules:
            key = "\\".join(self._split_path(rule.target_folder or unclassified)).lower()
            rules_by_folder.setdefault(key, []).append(rule)

        def _rule_values(rule):
            summary = self.sync_engine.get_rule_quota_summary(rule)
            text = pluralize_count(summary["email_count"], "sender")
            if summary["domain_count"]:
                text += f", {pluralize_count(summary['domain_count'], 'domain')}"
            return (text,)

        def _rule_tags(rule):
            return ("rule_enabled",) if rule.enabled else ("rule_disabled",)

        folder_iid_by_path: Dict[str, str] = {}
        for path in ordered:
            parts = self._split_path(path)
            parent_key = "\\".join(parts[:-1]).lower()
            parent_iid = root_iid if len(parts) == 1 else folder_iid_by_path.get(parent_key, root_iid)
            if not self.tree.exists(parent_iid):
                parent_iid = root_iid
            key = path.lower()
            folder_rules = rules_by_folder.get(key, [])
            if len(folder_rules) == 1 and not self.yaml_mgr.is_inside_unclassified(path):
                rule = folder_rules[0]
                rule_iid = f"rule_{rule.id}"
                state = "" if rule.enabled else " (disabled)"
                self.tree.insert(
                    parent_iid, tk.END, iid=rule_iid,
                    text=f"📁 {parts[-1]}  (rule: {rule.name}){state}",
                    values=_rule_values(rule), open=previous_open.get(rule_iid, True), tags=_rule_tags(rule),
                )
                self.rule_nodes_map[rule_iid] = rule.id
                self.folder_nodes_map[rule_iid] = path
                folder_iid_by_path[key] = rule_iid
                continue
            fld_iid = self._folder_iid(path)
            self.tree.insert(
                parent_iid, tk.END, iid=fld_iid,
                text=f"📁 {parts[-1]}", values=("",), open=True,
            )
            self.folder_nodes_map[fld_iid] = path
            folder_iid_by_path[key] = fld_iid
            for rule in folder_rules:
                rule_iid = f"rule_{rule.id}"
                label = f"⚡ {rule.name}" if rule.enabled else f"⏸ {rule.name} (disabled)"
                self.tree.insert(
                    fld_iid, tk.END, iid=rule_iid, text=label,
                    values=_rule_values(rule), open=previous_open.get(rule_iid, True), tags=_rule_tags(rule),
                )
                self.rule_nodes_map[rule_iid] = rule.id

    # --- mails under their rule ----------------------------------------
    def _insert_mail_nodes(self):
        if not callable(self.mail_provider):
            return
        by_rule = self.mail_provider() or {}
        for rule_id, items in by_rule.items():
            parent = f"rule_{rule_id}"
            if not self.tree.exists(parent):
                continue
            for msg, staged in items:
                iid = f"mail::{msg.entry_id}"
                if self.tree.exists(iid):
                    continue
                who = msg.sender_name or msg.sender_email
                try:
                    when = msg.received_time.strftime("%d/%m")
                except (AttributeError, ValueError):
                    when = ""
                insert_idx = sum(1 for c in self.tree.get_children(parent) if self.mail_entry_id(c))
                self.tree.insert(
                    parent, insert_idx, iid=iid,
                    text=f"{'* ' if staged else ''}✉ {who} — {msg.subject}",
                    values=(when,), tags=("mail_staged" if staged else "mail",),
                )
                self._mail_node_ids.append(iid)

    def _insert_pending_rule_nodes(self):
        """Mails staged into a rule that only exists after Apply: show them under that future rule."""
        if not callable(self.pending_provider):
            return
        for folder, (rule_name, msgs) in (self.pending_provider() or {}).items():
            parent = next((i for i, p in self.folder_nodes_map.items()
                           if p.lower() == folder.lower() and i.startswith("fld_")), None)
            if parent is None:
                # Merged folder+rule node or a folder that will be created: show at its parent / root
                parent = next((i for i, p in self.folder_nodes_map.items() if p.lower() == folder.lower()), None)
            label_folder = "" if parent and self.folder_nodes_map.get(parent, "").lower() == folder.lower() else f"  in {folder}"
            if parent is None:
                parent = "__HIERARCHY__"
            node = f"pending::{folder.lower()}"
            if self.tree.exists(node):
                continue
            self.tree.insert(
                parent, 0, iid=node, open=True, tags=("mail_staged",),
                text=f"* ⚡ {rule_name}  (new - Apply to create){label_folder}", values=("new",),
            )
            self._pending_nodes[node] = folder
            self._mail_node_ids.append(node)
            for msg in msgs:
                iid = f"mail::{msg.entry_id}"
                if self.tree.exists(iid):
                    continue
                self.tree.insert(
                    node, tk.END, iid=iid, tags=("mail_staged",),
                    text=f"* ✉ {msg.sender_name or msg.sender_email} — {msg.subject}",
                    values=(msg.received_time.strftime("%d/%m") if hasattr(msg.received_time, "strftime") else "",),
                )
                self._mail_node_ids.append(iid)

    def refresh_mail_nodes(self):
        """Re-list the mails under each rule (inbox loaded, mail staged or applied)."""
        selected = self.tree.selection()
        self._in_tree_transition = True
        try:
            for iid in self._mail_node_ids:
                if self.tree.exists(iid):
                    self.tree.delete(iid)
            self._mail_node_ids = []
            self._pending_nodes = {}
            self._insert_mail_nodes()
            self._insert_pending_rule_nodes()
            kept = [i for i in selected if self.tree.exists(i)]
            if kept:
                self.tree.selection_set(kept)
        finally:
            self._in_tree_transition = False

    @staticmethod
    def mail_entry_id(iid: Optional[str]) -> Optional[str]:
        return iid.split("::", 1)[1] if iid and iid.startswith("mail::") else None

    def _select_tree_iid_silently(self, iid: Optional[str]):
        """Select a tree item programmatically without firing dirty prompts."""
        self._in_tree_transition = True
        try:
            if iid and self.tree.exists(iid):
                self.tree.selection_set(iid)
                self._current_selected_iid = iid
            else:
                self.tree.selection_remove(self.tree.selection())
                self._current_selected_iid = None
        finally:
            self.update_idletasks()
            self._in_tree_transition = False

    def _get_current_rule_form_values(self) -> Tuple[bool, List[str], List[str], List[str]]:
        enabled = bool(self.var_rule_enabled.get())
        emails = [l.strip().lower() for l in self.txt_emails.get("1.0", tk.END).split("\n") if l.strip()]
        raw_domains = self.txt_domains.get("1.0", tk.END).split("\n")
        raw_keywords = self.txt_keywords.get("1.0", tk.END).split("\n")
        return (
            enabled,
            sorted(list(set(emails))),
            sorted(list(set(YamlConfigManager.normalize_domains(raw_domains)))),
            YamlConfigManager.normalize_keywords(raw_keywords),
        )

    def _update_rule_count_labels(self):
        _, emails, domains, keywords = self._get_current_rule_form_values()
        self.lbl_rule_emails_hdr.config(text=f"Emails ({len(emails)})")
        self.lbl_rule_domains_hdr.config(text=f"Domains ({len(domains)})")
        self.lbl_rule_keywords_hdr.config(text=f"Subject Keywords ({len(keywords)})")

    def _on_rule_text_changed(self, _event=None):
        self._update_rule_count_labels()
        self._refresh_dirty_state()

    def is_rule_dirty(self) -> bool:
        if not self.selected_rule or not self.frame_rule.winfo_manager():
            return False
        r = self.selected_rule
        f_enabled, f_emails, f_domains, f_keywords = self._get_current_rule_form_values()
        saved_emails = sorted(list(set(e.strip().lower() for e in (r.emails or []) if e.strip())))
        saved_domains = sorted(list(set(YamlConfigManager.normalize_domains(r.domains or []))))
        saved_keywords = YamlConfigManager.normalize_keywords(r.subject_keywords or [])
        return (
            f_enabled != bool(r.enabled)
            or f_emails != saved_emails
            or f_domains != saved_domains
            or f_keywords != saved_keywords
        )

    def has_unsaved_changes(self) -> bool:
        return self.is_rule_dirty()

    def _refresh_dirty_state(self):
        if self._populating_inspector:
            return
        if self.is_rule_dirty():
            self.btn_save_rule.config(text="Save Changes ●", style="DirtySave.TButton")
        else:
            self.btn_save_rule.config(text="Save Rule to YAML", style="Accent.TButton")

    def confirm_pending_changes(self, reset_if_discard: bool = True, refresh_tree: bool = True) -> bool:
        """Prompt user if rule inspector has unsaved changes.

        Returns True to allow navigation/close, False if user cancelled or save validation failed.
        """
        if self.is_rule_dirty() and self.selected_rule is not None:
            ans = messagebox.askyesnocancel(
                "Unsaved Changes",
                f"Save changes to '{self.selected_rule.name}'?",
                icon=messagebox.WARNING,
            )
            if ans is None:
                return False
            if ans:
                return self._save_rule_changes(refresh_tree=refresh_tree, select_after=False)
            if reset_if_discard:
                self._populate_rule_inspector(self.selected_rule)
            return True

        return True

    # =================================================================
    # TREE SELECTION & INSPECTOR SWITCHING
    # =================================================================
    def _on_tree_select(self, event=None):
        if self._in_tree_transition:
            return
        sel = self.tree.selection()
        if not sel:
            if self._current_selected_iid is not None:
                if not self.confirm_pending_changes(reset_if_discard=False, refresh_tree=False):
                    self._select_tree_iid_silently(self._current_selected_iid)
                    return
            self._current_selected_iid = None
            self.selected_rule = None
            self.selected_folder_path = None
            self.selected_pool_item = None
            self._show_inspector(self.frame_empty)
            self._refresh_dirty_state()
            return

        iid = sel[0]
        if iid == self._current_selected_iid:
            return

        if self._current_selected_iid is not None:
            was_dirty = self.has_unsaved_changes()
            if not self.confirm_pending_changes(reset_if_discard=False, refresh_tree=False):
                self._select_tree_iid_silently(self._current_selected_iid)
                return
            if was_dirty and not self.has_unsaved_changes():
                # Previous edits were saved; refresh tree counts/names and preserve target iid
                self.refresh_all(preserve_selection_iid=iid)

        self._current_selected_iid = iid

        # 0. Selected a mail under a rule: show it in the mail reader
        entry_id = self.mail_entry_id(iid)
        if entry_id:
            self.selected_rule = None
            self.selected_folder_path = None
            self.selected_pool_item = None
            self._show_inspector(self.frame_empty)
            self._refresh_dirty_state()
            if callable(self.on_mail_selected):
                self.on_mail_selected(entry_id)
            return

        # 1. Selected a Rule (a merged "folder + rule" node also knows its folder)
        if iid.startswith("rule_"):
            rule_id = self.rule_nodes_map.get(iid)
            self.selected_rule = next((r for r in self.yaml_mgr.rules if r.id == rule_id), None)
            self.selected_folder_path = self.folder_nodes_map.get(iid)
            self.selected_pool_item = None
            if self.selected_rule:
                self._populate_rule_inspector(self.selected_rule)
                self._show_inspector(self.frame_rule)
            return

        # 2. Selected a Folder (Any Level: L1, L2, L3, L4...)
        if iid.startswith("fld_"):
            self.selected_folder_path = self.folder_nodes_map.get(iid)
            self.selected_rule = None
            self.selected_pool_item = None
            if self.selected_folder_path:
                self._populate_folder_inspector(self.selected_folder_path)
                self._show_inspector(self.frame_folder)
            self._refresh_dirty_state()
            return

        # 3. Selected Pool root or pool item
        if iid == "__POOL__" or iid.startswith("pool_"):
            self.selected_pool_item = iid.replace("pool_", "", 1) if iid.startswith("pool_") else None
            self.selected_rule = None
            self.selected_folder_path = None
            self._populate_pool_inspector()
            self._show_inspector(self.frame_pool)
            self._refresh_dirty_state()
            return

        # Category headers
        self._show_inspector(self.frame_empty)
        self._refresh_dirty_state()

    def _on_tree_double_click(self, event):
        """Toggle expand/collapse on double-click."""
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if self.tree.get_children(iid):
            is_open = self.tree.item(iid, "open")
            self.tree.item(iid, open=not is_open)

    # =================================================================
    # POPULATING INSPECTORS (DYNAMIC LEVELS)
    # =================================================================
    def _populate_rule_inspector(self, rule: RuleConfig):
        self._populating_inspector = True
        try:
            # Breadcrumbs without [L1]/[L2] prefix, keeping (Level N) at end
            folder_path = rule.target_folder or "_Unclassified"
            parts = [p.strip() for p in re.split(r'[\\/]', folder_path) if p.strip()]
            breadcrumb_str = " > ".join(parts) if parts else "(Root)"
            self.lbl_breadcrumb.config(text=f"📁 {breadcrumb_str} (Level {len(parts)})")

            # Read-only rule name
            prefix = "" if rule.id == "rule_unclassified" else MANAGED_PREFIX
            self.lbl_rule_name.config(text=f"{prefix}{rule.name}")
            self.var_rule_enabled.set(rule.enabled)

            # Quota Meter
            self._update_rule_quota_display()

            # Condition text fields (one entry per line)
            self.txt_emails.delete("1.0", tk.END)
            self.txt_emails.insert(tk.END, "\n".join(sorted(rule.emails)))

            self.txt_domains.delete("1.0", tk.END)
            self.txt_domains.insert(tk.END, "\n".join(sorted(rule.domains)))

            norm_keywords = YamlConfigManager.normalize_keywords(rule.subject_keywords)
            self.txt_keywords.delete("1.0", tk.END)
            self.txt_keywords.insert(tk.END, "\n".join(norm_keywords))

            self._update_rule_count_labels()

            self.lbl_test_result.config(text="")
            self.ent_test_match.delete(0, tk.END)
            self.ent_test_subject.delete(0, tk.END)
            self.rule_scroll_canvas.yview_moveto(0)
        finally:
            self._populating_inspector = False
        self._refresh_dirty_state()

    def _update_rule_quota_display(self):
        """Update quota banner and sub-rule preview from SyncEngine without duplicating split logic."""
        if not self.selected_rule:
            self.lbl_quota.config(text="", fg="#475569")
            self.lbl_quota_subrules.config(text="")
            return

        summary = self.sync_engine.get_rule_quota_summary(self.selected_rule)
        skip_reason = summary.get("skip_reason")
        if skip_reason == "no_conditions":
            self.lbl_quota.config(text="⚠ No conditions — will be skipped on sync", fg="#ea580c")
            self.lbl_quota_subrules.config(text="")
            return
        if skip_reason == "no_target_folder":
            self.lbl_quota.config(text="⚠ No target folder — will be skipped on sync", fg="#ea580c")
            self.lbl_quota_subrules.config(text="")
            return

        names = summary["native_names"]
        has_threshold_split = any("(Part " in name for name in names)
        color = "#ea580c" if has_threshold_split else "#16a34a"
        self.lbl_quota.config(
            text=(
                f"Outlook: {pluralize_count(summary['email_count'], 'sender')}, "
                f"{pluralize_count(summary['domain_count'], 'domain')}, "
                f"{pluralize_count(summary['keyword_count'], 'keyword')} → "
                f"{pluralize_count(len(names), 'native rule')}"
            ),
            fg=color,
        )
        self.lbl_quota_subrules.config(text=f"Sub-rules: {', '.join(names)}")

    def _populate_folder_inspector(self, folder_path: str):
        self.lbl_folder_title.config(text=f"Folder: {folder_path}")
        parts = [p.strip() for p in re.split(r'[\\/]', folder_path) if p.strip()]
        depth = len(parts)

        parent_text = parts[-2] if depth > 1 else "(Root)"
        crumb_text = " > ".join(parts)
        self.lbl_folder_level.config(text=f"Level: Level {depth}  |  Parent: {parent_text}\nPath: {crumb_text}")

        # Rules in folder
        folder_rules = [r for r in self.yaml_mgr.rules if r.target_folder == folder_path]
        rule_counts = {}
        total_senders = 0
        for r in folder_rules:
            summary = self.sync_engine.get_rule_quota_summary(r)
            cnt = summary["email_count"] + summary["domain_count"]
            rule_counts[r.id] = cnt
            total_senders += cnt

        self.lbl_folder_stats.config(text=f"Rules in this Folder: {len(folder_rules)}  |  Total Monitored Senders: {total_senders}")

        self.tree_folder_rules.delete(*self.tree_folder_rules.get_children())
        for r in folder_rules:
            st = "Active" if r.enabled else "Disabled"
            self.tree_folder_rules.insert(
                "", tk.END, iid=f"frule_{r.id}", text=r.name, values=(st, pluralize_count(rule_counts[r.id], "sender"))
            )

        # Configure Level shifting buttons (Promote / Move Up)
        if depth > 1:
            self.btn_promote_root.pack(side=tk.LEFT, padx=2)
            self.btn_move_up.config(text=f"Move Up to L{depth-1}")
            self.btn_move_up.pack(side=tk.LEFT, padx=2)
        else:
            self.btn_promote_root.pack_forget()
            self.btn_move_up.pack_forget()

    def _populate_pool_inspector(self):
        self.lst_pool.delete(0, tk.END)
        for email in self.yaml_mgr.unclassified_pool:
            self.lst_pool.insert(tk.END, email)

    def _on_folder_rule_double_click(self, event):
        """Double clicking a rule inside the folder inspector selects and edits that rule."""
        sel = self.tree_folder_rules.selection()
        if not sel:
            return
        rule_id = sel[0].replace("frule_", "", 1)
        tree_iid = f"rule_{rule_id}"
        if self.tree.exists(tree_iid):
            self.tree.selection_set(tree_iid)
            self._on_tree_select()

    # =================================================================
    # DYNAMIC DRAG AND DROP REORGANIZATION (ARBITRARY LEVELS)
    # =================================================================
    def _on_drag_start(self, event):
        """Record start node and mouse position."""
        item = self.tree.identify_row(event.y)
        self.drag_source_id = item if item else None
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        self.is_dragging = False

    def _on_drag_motion(self, event):
        """Track drag motion, create floating badge, and highlight drop target."""
        if not self.drag_source_id:
            return

        dx = abs(event.x - self.drag_start_x)
        dy = abs(event.y - self.drag_start_y)
        if not self.is_dragging and (dx > 4 or dy > 4):
            self.is_dragging = True

        if not self.is_dragging:
            return

        # Create or update floating drag tooltip
        if not self.drag_window:
            self.drag_window = tk.Toplevel(self)
            self.drag_window.wm_overrideredirect(True)
            self.drag_window.attributes("-topmost", True)
            self.drag_window.config(bg="#0f172a")

            source_label = self._get_drag_source_title(self.drag_source_id)
            self.lbl_drag_text = tk.Label(
                self.drag_window,
                text=f"Moving: {source_label}",
                bg="#0f172a",
                fg="#f8fafc",
                font=("", 8, "bold"),
                padx=8,
                pady=4
            )
            self.lbl_drag_text.pack()

        self.drag_window.geometry(f"+{event.x_root + 15}+{event.y_root + 12}")

        # Hover highlight (selection is left alone so the inspector doesn't flicker)
        self._set_drop_hover(self.tree.identify_row(event.y) or None)

    def _set_drop_hover(self, iid: Optional[str]):
        if iid == self._drop_hover_iid:
            return
        for old in (self._drop_hover_iid,):
            if old and self.tree.exists(old):
                self.tree.item(old, tags=tuple(t for t in self.tree.item(old, "tags") if t != "drop_hover"))
        self._drop_hover_iid = iid
        if iid and self.tree.exists(iid):
            self.tree.item(iid, tags=tuple(self.tree.item(iid, "tags")) + ("drop_hover",))

    def _on_drag_release(self, event):
        """Execute folder or rule move upon drop."""
        if self.drag_window:
            self.drag_window.destroy()
            self.drag_window = None
        self._set_drop_hover(None)
        self._drop_ctrl = bool(getattr(event, "state", 0) & 0x0004)

        if not self.is_dragging or not self.drag_source_id:
            self.drag_source_id = None
            self.is_dragging = False
            return

        source_iid = self.drag_source_id
        target_iid = self.tree.identify_row(event.y)

        self.drag_source_id = None
        self.is_dragging = False

        if not target_iid or source_iid == target_iid:
            return

        self._execute_drop(source_iid, target_iid)

    def _execute_drop(self, source_iid: str, target_iid: str):
        """Reorganize hierarchy based on drop source and target (arbitrary levels)."""
        # A mail is dropped like a mail from the list: it re-stages its sender
        entry_id = self.mail_entry_id(source_iid)
        if entry_id:
            if self.mail_entry_id(target_iid):
                target_iid = self.tree.parent(target_iid)
            if callable(self.on_mail_dropped) and self.resolve_drop_iid(target_iid) is not None:
                self.on_mail_dropped(entry_id, target_iid, self._drop_ctrl)
            return
        if self.mail_entry_id(target_iid):
            target_iid = self.tree.parent(target_iid)
        if not target_iid or target_iid == source_iid:
            return
        # A merged "folder + rule" node moves as a folder (its rule goes with it)
        if source_iid.startswith("rule_") and source_iid in self.folder_nodes_map:
            self._move_folder_by_drop(self.folder_nodes_map[source_iid], target_iid)
            return
        # -------------------------------------------------------------
        # CASE 1: Dragging a Rule
        # -------------------------------------------------------------
        if source_iid.startswith("rule_"):
            rule_id = self.rule_nodes_map.get(source_iid)
            rule = next((r for r in self.yaml_mgr.rules if r.id == rule_id), None)
            if not rule:
                return

            dest_folder = None
            # Target is a folder node of any level
            if target_iid in self.folder_nodes_map:
                dest_folder = self.folder_nodes_map.get(target_iid)
            # Target is another rule node (move into that rule's folder)
            elif target_iid.startswith("rule_"):
                target_rule_id = self.rule_nodes_map.get(target_iid)
                target_rule = next((r for r in self.yaml_mgr.rules if r.id == target_rule_id), None)
                if target_rule:
                    dest_folder = target_rule.target_folder
            # Target is Root Hierarchy
            elif target_iid == "__HIERARCHY__":
                dest_folder = simpledialog.askstring(
                    "Move Rule to Root Folder",
                    "Enter Root Folder (Level 1) name:",
                    initialvalue=rule.name.replace(" ", "_")
                )
                if not dest_folder:
                    return

            if dest_folder and dest_folder.lower() == (rule.target_folder or "").lower():
                self._show_toast(f"Rule '{rule.name}' is already in '{dest_folder}'.")
                return
            if dest_folder:
                ok, res = self.yaml_mgr.move_rule_to_folder(rule_id, dest_folder)
                if not ok:
                    self._show_toast(res, error=True)
                    return
                self._show_toast(f"Moved rule '{rule.name}' -> '{dest_folder}'")
                self.refresh_all()
                new_iid = f"rule_{rule_id}"
                if self.tree.exists(new_iid):
                    self.tree.selection_set(new_iid)
                    self._on_tree_select()
            return

        # -------------------------------------------------------------
        # CASE 2: Dragging a Folder Hierarchy (L3 -> L1, L3 -> L2, L2 -> L4, etc.)
        # -------------------------------------------------------------
        if source_iid.startswith("fld_"):
            source_folder = self.folder_nodes_map.get(source_iid)
            if not source_folder:
                return
            self._move_folder_by_drop(source_folder, target_iid)
            return

        self._execute_pool_drop(source_iid, target_iid)

    def _select_folder_node(self, path: str):
        """Select the node showing folder `path` (a folder node or a merged folder+rule node)."""
        iid = next((i for i, p in self.folder_nodes_map.items() if p.lower() == (path or "").lower()), None)
        if iid and self.tree.exists(iid):
            self.tree.selection_set(iid)
            self._on_tree_select()

    def _move_folder_by_drop(self, source_folder: str, target_iid: str):
        """Move folder `source_folder` onto tree item `target_iid` (root, folder or rule)."""
        source_parts = [p.strip() for p in re.split(r'[\\/]', source_folder) if p.strip()]
        folder_name = source_parts[-1]
        current_parent = "\\".join(source_parts[:-1])

        # Dropped onto Root Hierarchy: Promote directly to Root (Level 1)!
        if target_iid == "__HIERARCHY__":
            if not current_parent:
                self._show_toast(f"'{folder_name}' is already a top-level folder.")
                return
            ok, res = self.yaml_mgr.promote_folder_to_root(source_folder)
            if ok:
                self._show_toast(f"Promoted '{folder_name}' to Root (Level 1)")
                self.refresh_all()
                self._select_folder_node(res)
            else:
                messagebox.showwarning("Promote Folder", res)
            return

        # Dropped onto another Folder node
        dest_parent = ""
        if target_iid in self.folder_nodes_map:
            dest_parent = self.folder_nodes_map.get(target_iid)
        elif target_iid.startswith("rule_"):
            target_rule_id = self.rule_nodes_map.get(target_iid)
            target_rule = next((r for r in self.yaml_mgr.rules if r.id == target_rule_id), None)
            dest_parent = target_rule.target_folder if target_rule else ""
        else:
            return
        if (dest_parent or "").lower() == current_parent.lower():
            self._show_toast(f"'{folder_name}' is already in '{current_parent}'.")
            return

        ok, res = self.yaml_mgr.move_folder_hierarchy(source_folder, dest_parent)
        if ok:
            new_parts = [p.strip() for p in re.split(r'[\\/]', res) if p.strip()]
            new_depth = len(new_parts)
            self._show_toast(f"Moved '{folder_name}' to Level {new_depth}: '{res}'")
            self.refresh_all()
            self._select_folder_node(res)
        else:
            self._show_toast(res, error=True)

    def _execute_pool_drop(self, source_iid: str, target_iid: str):
        # -------------------------------------------------------------
        # CASE 3: Dragging an Unclassified Email
        # -------------------------------------------------------------
        if source_iid.startswith("pool_"):
            email = source_iid.replace("pool_", "", 1)
            # Dropped onto a Rule
            if target_iid.startswith("rule_"):
                target_rule_id = self.rule_nodes_map.get(target_iid)
                self.yaml_mgr.add_sender_to_rule_or_group(email, target_rule_id)
                self._show_toast(f"Added '{email}' to rule")
                self.refresh_all()
                self.tree.selection_set(target_iid)
                self._on_tree_select()

    def _get_drag_source_title(self, iid: str) -> str:
        """Return human-readable title for dragging item."""
        if self.mail_entry_id(iid):
            return "mail (drop on a rule or folder)"
        if iid.startswith("rule_") and iid in self.folder_nodes_map:
            return f"Folder '{self._split_path(self.folder_nodes_map[iid])[-1]}' with its rule"
        if iid.startswith("rule_"):
            rule_id = self.rule_nodes_map.get(iid)
            rule = next((r for r in self.yaml_mgr.rules if r.id == rule_id), None)
            return f"Rule '{rule.name}'" if rule else "Rule"
        elif iid.startswith("fld_"):
            path = self.folder_nodes_map.get(iid, "")
            parts = [p.strip() for p in re.split(r'[\\/]', path) if p.strip()]
            return f"Folder [L{len(parts)}] '{parts[-1]}'" if parts else "Folder"
        elif iid.startswith("pool_"):
            return f"Address '{iid.replace('pool_', '')}'"
        return "Item"

    def _on_destroy(self, event=None):
        """Cancel any pending toast timer when the view is destroyed."""
        if event is not None and event.widget is not self:
            return
        if self._toast_after_id:
            try:
                self.after_cancel(self._toast_after_id)
            except tk.TclError:
                pass
            self._toast_after_id = None

    # --- integrated-mode helpers --------------------------------------
    def resolve_drop_iid(self, iid: Optional[str]):
        """What a mail dropped on tree item `iid` means: ('rule', id) / ('folder', path) / ('new', None)."""
        if not iid:
            return None
        if self.mail_entry_id(iid):
            iid = self.tree.parent(iid)
        if iid in self._pending_nodes:
            return ("folder", self._pending_nodes[iid])
        if iid in self.rule_nodes_map:
            return ("rule", self.rule_nodes_map[iid])
        if iid in self.folder_nodes_map:
            return ("folder", self.folder_nodes_map[iid])
        if iid == "__HIERARCHY__":
            return ("new", None)
        return None

    def _notify_item_activated(self, event=None):
        sel = self.tree.selection()
        if callable(self.on_item_activated) and sel and not self.mail_entry_id(sel[0]):
            self.after_idle(self.on_item_activated)

    def _on_delete_key(self):
        if self.selected_rule:
            self._delete_selected(ask=False)
        elif self.selected_folder_path:
            self._delete_selected_folder()
        return "break"

    def _on_rename_key(self):
        if self.selected_rule and self.selected_folder_path:
            self._rename_selected_folder()
        elif self.selected_folder_path:
            self._rename_selected_folder()
        return "break"

    def _request_undo(self):
        if callable(self.on_undo_request):
            self.on_undo_request()

    def refresh_undo_button(self):
        label = self.yaml_mgr.undo_label()
        if label:
            short = label if len(label) <= 40 else label[:37] + "..."
            self.btn_undo.config(state=tk.NORMAL, text=f"Undo: {short}")
        else:
            self.btn_undo.config(state=tk.DISABLED, text="Undo (Ctrl+Z)")

    def reset_selection_after_undo(self):
        """Undo replaces the model objects, so drop references to the old ones."""
        self.selected_rule = None
        self.selected_folder_path = None
        self.selected_pool_item = None
        self._select_tree_iid_silently(None)
        self._show_inspector(self.frame_empty)

    def _show_toast(self, message: str, error: bool = False):
        """Display non-blocking status notification in bottom tip bar."""
        self.lbl_toast.config(text=message, fg="#b91c1c" if error else "#0284c7")
        if self._toast_after_id:
            try:
                self.after_cancel(self._toast_after_id)
            except tk.TclError:
                pass
        self._toast_after_id = self.after(
            5000,
            lambda: self.winfo_exists() and self.lbl_toast.config(text=self._default_tip_text, fg="#475569"),
        )

    # =================================================================
    # CONTEXT MENUS & ACTIONS (DYNAMIC LEVEL MANAGEMENT)
    # =================================================================
    def _show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        self._on_tree_select()

        menu = tk.Menu(self, tearoff=0)

        # Folder context menu (Dynamic Level Shift)
        if iid.startswith("fld_") or iid == "__HIERARCHY__":
            if iid.startswith("fld_"):
                folder_path = self.folder_nodes_map.get(iid, "")
                parts = [p.strip() for p in re.split(r'[\\/]', folder_path) if p.strip()]
                depth = len(parts)

                menu.add_command(label=f"+ Add Subfolder (Level {depth+1})", command=self._add_subfolder)
                menu.add_command(label="+ Add Rule Here", command=self._add_rule_in_selected_folder)
                menu.add_separator()

                if depth > 1:
                    menu.add_command(label="Move to Top Level", command=self._promote_selected_folder_to_root)
                    menu.add_command(label=f"Move Up 1 Level (to Level {depth-1})", command=self._move_selected_folder_up)

                menu.add_command(label="Move to Folder...", command=self._open_move_folder_dialog)
                menu.add_separator()
                menu.add_command(label="Rename Folder...", command=self._rename_selected_folder)
                menu.add_command(label="Delete Folder...", command=self._delete_selected_folder)
            else:
                menu.add_command(label="+ New Root Folder (Level 1)", command=self._add_root_folder)
                menu.add_command(label="+ New Rule in Root", command=self._add_rule_in_selected_folder)

        # Rule context menu
        elif iid.startswith("rule_"):
            menu.add_command(label="Toggle Active / Disabled", command=self._toggle_rule_enabled)
            menu.add_command(label="Move Rule to Folder...", command=self._open_folder_picker_dialog)
            menu.add_separator()
            menu.add_command(label="Delete Rule", command=self._delete_selected)
            if iid in self.folder_nodes_map:
                menu.add_separator()
                menu.add_command(label="+ Add Subfolder", command=self._add_subfolder)
                menu.add_command(label="Rename Folder...", command=self._rename_selected_folder)
                menu.add_command(label="Delete Folder...", command=self._delete_selected_folder)
        elif self.mail_entry_id(iid):
            return

        # Pool context menu
        elif iid.startswith("pool_"):
            menu.add_command(label="Assign to Rule...", command=self._assign_pool_to_rule)
            menu.add_command(label="Remove from Pool", command=self._remove_from_pool)

        menu.tk_popup(event.x_root, event.y_root)

    # -----------------------------------------------------------------
    # DYNAMIC FOLDER ACTIONS (PROMOTING, MOVING, CREATING)
    # -----------------------------------------------------------------
    def _add_root_folder(self):
        """Prompt to create a new Root (Level 1) folder."""
        folder_name = simpledialog.askstring("New Root Folder (Level 1)", "Enter Root Folder Name (e.g. Operations, Logistics):")
        if not folder_name:
            return
        folder_name = folder_name.strip().replace("\\", "_").replace("/", "_")
        if folder_name.startswith("_"):
            self._show_toast("Folder name cannot start with '_'.", error=True)
            return
        self.yaml_mgr.add_folder(folder_name)
        self._show_toast(f"Created Root Folder (Level 1): '{folder_name}'")
        self.refresh_all()
        fld_iid = f"fld_{folder_name.lower().replace(' ', '_')}"
        if self.tree.exists(fld_iid):
            self.tree.selection_set(fld_iid)
            self._on_tree_select()

    def _add_subfolder(self):
        """Add subfolder under currently selected folder (creates Level N+1)."""
        parent_path = self.selected_folder_path
        if not parent_path:
            if self.selected_rule and self.selected_rule.target_folder:
                parent_path = self.selected_rule.target_folder
            else:
                folders = self.yaml_mgr.get_all_folders()
                parent_path = folders[0] if folders else "General"

        parts = [p.strip() for p in re.split(r'[\\/]', parent_path) if p.strip()]
        new_level = len(parts) + 1

        sub_name = simpledialog.askstring(
            f"New Subfolder (Level {new_level})",
            f"Enter Subfolder Name to add under:\n'{parent_path}' (Level {len(parts)}):\n\n"
            f"This will become Level {new_level}:"
        )
        if not sub_name:
            return
        sub_name = sub_name.strip().replace("\\", "_").replace("/", "_")
        if sub_name.startswith("_"):
            self._show_toast("Folder name cannot start with '_'.", error=True)
            return
        full_sub_path = f"{parent_path}\\{sub_name}"
        self.yaml_mgr.add_folder(full_sub_path)
        self._show_toast(f"Created Level {new_level} folder: '{full_sub_path}'")
        self.refresh_all()
        fld_iid = f"fld_{full_sub_path.lower().replace(' ', '_')}"
        if self.tree.exists(fld_iid):
            self.tree.selection_set(fld_iid)
            self._on_tree_select()

    def _promote_selected_folder_to_root(self):
        """1-click promote any subfolder (L2, L3, L4...) to Root (Level 1)."""
        if not self.selected_folder_path:
            return
        folder_name = self.selected_folder_path.split("\\")[-1]
        ok, res = self.yaml_mgr.promote_folder_to_root(self.selected_folder_path)
        if ok:
            self._show_toast(f"Promoted '{folder_name}' to Root (Level 1)")
            self.selected_folder_path = res
            self.refresh_all()
            fld_iid = f"fld_{res.lower().replace(' ', '_')}"
            if self.tree.exists(fld_iid):
                self.tree.selection_set(fld_iid)
                self._on_tree_select()
        else:
            messagebox.showwarning("Promote Folder", res)

    def _move_selected_folder_up(self):
        """1-click move folder up one level (e.g. Level 3 -> Level 2, Level 2 -> Level 1)."""
        if not self.selected_folder_path:
            return
        ok, res = self.yaml_mgr.move_folder_up_one_level(self.selected_folder_path)
        if ok:
            parts = [p.strip() for p in re.split(r'[\\/]', res) if p.strip()]
            self._show_toast(f"Moved folder up to Level {len(parts)}: '{res}'")
            self.selected_folder_path = res
            self.refresh_all()
            fld_iid = f"fld_{res.lower().replace(' ', '_')}"
            if self.tree.exists(fld_iid):
                self.tree.selection_set(fld_iid)
                self._on_tree_select()
        else:
            messagebox.showwarning("Move Folder Up", res)

    def _open_move_folder_dialog(self):
        """Modal dialog to move selected folder to any destination parent folder."""
        if not self.selected_folder_path:
            return

        dlg = tk.Toplevel(self)
        dlg.title("Move Folder Hierarchy")
        dlg.geometry("450x380")
        dlg.transient(self)
        dlg.grab_set()

        source_path = self.selected_folder_path
        source_name = source_path.split("\\")[-1]

        tk.Label(
            dlg,
            text=f"Move '{source_name}' to another folder:",
            font=("", 10, "bold"),
            padx=10,
            pady=8
        ).pack(anchor=tk.W)

        frame_list = ttk.Frame(dlg, padding=8)
        frame_list.pack(fill=tk.BOTH, expand=True)

        lst = tk.Listbox(frame_list, font=("Consolas", 9))
        lst.pack(fill=tk.BOTH, expand=True)

        # First entry: Root (Level 1)
        lst.insert(tk.END, "[Root Level 1] (Promote to top level)")

        all_folders = [f for f in self.yaml_mgr.get_all_folders() if f != source_path and not f.startswith(source_path + "\\")]
        for f in all_folders:
            depth = len(f.split("\\"))
            indent = "  " * (depth - 1)
            lst.insert(tk.END, f"{indent}[L{depth}] {f}")

        def _do_move():
            sel = lst.curselection()
            if not sel:
                return
            idx = sel[0]
            if idx == 0:
                # Promote to root
                ok, res = self.yaml_mgr.promote_folder_to_root(source_path)
            else:
                target_parent = all_folders[idx - 1]
                ok, res = self.yaml_mgr.move_folder_hierarchy(source_path, target_parent)

            if ok:
                dlg.destroy()
                parts = [p.strip() for p in re.split(r'[\\/]', res) if p.strip()]
                self._show_toast(f"Moved '{source_name}' to Level {len(parts)}: '{res}'")
                self.selected_folder_path = res
                self.refresh_all()
                fld_iid = f"fld_{res.lower().replace(' ', '_')}"
                if self.tree.exists(fld_iid):
                    self.tree.selection_set(fld_iid)
                    self._on_tree_select()
            else:
                messagebox.showwarning("Move Folder", res)

        btn_box = ttk.Frame(dlg, padding=8)
        btn_box.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_box, text="Move Folder", style="Accent.TButton", command=_do_move).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_box, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

    def _rename_selected_folder(self):
        if not self.selected_folder_path:
            return
        parts = [p.strip() for p in re.split(r'[\\/]', self.selected_folder_path) if p.strip()]
        current_name = parts[-1]

        new_name = simpledialog.askstring(
            "Rename Folder",
            f"Enter new name for folder '{current_name}':",
            initialvalue=current_name
        )
        if not new_name or new_name == current_name:
            return

        ok, new_path = self.yaml_mgr.rename_folder_hierarchy(self.selected_folder_path, new_name)
        if ok:
            self._show_toast(f"Renamed folder to '{new_path}'")
            self.refresh_all()
            new_fld_iid = f"fld_{new_path.lower().replace(' ', '_')}"
            if self.tree.exists(new_fld_iid):
                self.tree.selection_set(new_fld_iid)
                self._on_tree_select()
        else:
            messagebox.showwarning("Rename Folder", new_path)

    def _delete_selected_folder(self):
        if not self.selected_folder_path:
            return
        folder_path = self.selected_folder_path

        rules_in_fld = [r for r in self.yaml_mgr.rules if r.target_folder == folder_path or (r.target_folder and r.target_folder.startswith(folder_path + "\\"))]

        msg = f"Are you sure you want to delete folder '{folder_path}'?\n\n"
        if rules_in_fld:
            msg += f"Contains {len(rules_in_fld)} rule(s).\nAll rule addresses will be safely repooled to the Unclassified Pool."
        else:
            msg += "This folder is empty."

        confirm = messagebox.askyesno("Confirm Delete Folder", msg, icon=messagebox.WARNING)
        if confirm:
            affected = self.yaml_mgr.delete_folder_hierarchy(folder_path, repool_addresses=True)
            self._show_toast(f"Deleted folder '{folder_path}' ({affected} rules repooled)")
            self.selected_folder_path = None
            self.refresh_all()
            self._show_inspector(self.frame_empty)

    # -----------------------------------------------------------------
    # RULE CREATION & MODIFICATION
    # -----------------------------------------------------------------
    def _add_rule_in_selected_folder(self):
        """Create new rule inside currently selected folder (or select existing rule if present)."""
        dest_folder = self.selected_folder_path
        if not dest_folder:
            if self.selected_rule and self.selected_rule.target_folder:
                dest_folder = self.selected_rule.target_folder
            else:
                folders = [f for f in self.yaml_mgr.get_all_folders() if not self.yaml_mgr.is_inside_unclassified(f)]
                dest_folder = folders[0] if folders else "General"
        if self.yaml_mgr.is_inside_unclassified(dest_folder):
            self._show_toast(f"New rules cannot be created inside '{self.yaml_mgr.unclassified_folder()}'.", error=True)
            return

        existing = self.yaml_mgr.rule_for_folder(dest_folder)
        if existing is not None:
            rule_iid = f"rule_{existing.id}"
            if self.tree.exists(rule_iid):
                self.tree.selection_set(rule_iid)
                self._on_tree_select()
            self._show_toast(f"'{dest_folder}' already has a rule.")
            return

        self.yaml_mgr.next_change_label = f"Create rule in '{dest_folder}'"
        new_rule = self.yaml_mgr.ensure_rule_for_folder(dest_folder)
        self.yaml_mgr.save()
        self._show_toast(f"Created rule '{new_rule.name}' in '{dest_folder}'")
        self.refresh_all()

        rule_iid = f"rule_{new_rule.id}"
        if self.tree.exists(rule_iid):
            self.tree.selection_set(rule_iid)
            self._on_tree_select()

    def _save_rule_changes(self, refresh_tree: bool = True, select_after: bool = True) -> bool:
        if not self.selected_rule:
            return True

        enabled, emails, domains, keywords = self._get_current_rule_form_values()
        self.selected_rule.enabled = enabled
        self.selected_rule.emails = emails
        self.selected_rule.domains = domains
        self.selected_rule.subject_keywords = keywords

        self.yaml_mgr.next_change_label = f"Edit rule '{self.selected_rule.name}'"
        self.yaml_mgr.save()
        self._show_toast(f"Saved rule '{self.selected_rule.name}' to rules.yaml")
        self._refresh_dirty_state()

        if refresh_tree:
            self.refresh_all()

        if select_after:
            rule_iid = f"rule_{self.selected_rule.id}"
            if self.tree.exists(rule_iid):
                self._select_tree_iid_silently(rule_iid)
                self._populate_rule_inspector(self.selected_rule)
                self._show_inspector(self.frame_rule)
        return True

    def _toggle_rule_enabled(self):
        if not self.selected_rule:
            return
        self.selected_rule.enabled = not self.selected_rule.enabled
        self.yaml_mgr.save()
        st = "Enabled" if self.selected_rule.enabled else "Disabled"
        self._show_toast(f"Rule '{self.selected_rule.name}' {st}")
        rule_iid = f"rule_{self.selected_rule.id}"
        self.refresh_all(preserve_selection_iid=rule_iid)
        self._populate_rule_inspector(self.selected_rule)

    def _delete_selected(self, ask: bool = True):
        """Delete currently selected rule or folder (Delete key: no question, Undo is available)."""
        if self.selected_rule:
            rule = self.selected_rule
            if rule.id == "rule_unclassified":
                messagebox.showwarning("Notice", "Cannot delete the default [Unclassified] fallback rule.")
                return

            confirm = (not ask) or messagebox.askyesno(
                "Confirm Delete Rule",
                f"Are you sure you want to delete rule '{rule.name}'?\n\n"
                f"Addresses will be safely moved to the Unclassified Pool.",
                icon=messagebox.WARNING
            )
            if confirm:
                self.yaml_mgr.remove_rule_and_repool(rule.id)
                self._show_toast(f"Deleted rule '{rule.name}' (Ctrl+Z to restore)")
                self.selected_rule = None
                self._current_selected_iid = None
                self.refresh_all()
                self._show_inspector(self.frame_empty)
                self._refresh_dirty_state()
        elif self.selected_folder_path:
            self._delete_selected_folder()

    # -----------------------------------------------------------------
    # MATCH TESTER
    # -----------------------------------------------------------------
    def _test_rule_match(self):
        query = self.ent_test_match.get().strip().lower()
        subj_query = self.ent_test_subject.get().strip()
        if (not query and not subj_query) or not self.selected_rule:
            return
        matched, reason = self.sync_engine.test_rule_match(self.selected_rule, query, subj_query)
        self.lbl_test_result.config(text=reason, fg="#16a34a" if matched else "#dc2626")

    # -----------------------------------------------------------------
    # FOLDER PICKER MODAL DIALOG (DYNAMIC ARBITRARY LEVELS)
    # -----------------------------------------------------------------
    def _open_folder_picker_dialog(self):
        """Modal dialog to pick or enter an arbitrary target folder hierarchy."""
        if not self.selected_rule:
            return

        dlg = tk.Toplevel(self)
        dlg.title("Select Target Folder Hierarchy")
        dlg.geometry("450x380")
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(
            dlg,
            text=f"Change Folder for: '{self.selected_rule.name}'",
            font=("", 10, "bold"),
            padx=10,
            pady=8
        ).pack(anchor=tk.W)

        # Existing folders list
        frame_list = ttk.Frame(dlg, padding=8)
        frame_list.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame_list, text="Choose an existing folder or enter path:").pack(anchor=tk.W)
        lst_folders = tk.Listbox(frame_list, font=("Consolas", 9))
        lst_folders.pack(fill=tk.BOTH, expand=True, pady=4)

        all_folders = self.yaml_mgr.get_all_folders()
        for idx, f in enumerate(all_folders):
            depth = len(f.split("\\"))
            indent = "  " * (depth - 1)
            lst_folders.insert(tk.END, f"{indent}[L{depth}] {f}")
            if f == self.selected_rule.target_folder:
                lst_folders.selection_set(idx)

        # Custom path entry (arbitrary depth)
        frame_custom = ttk.Frame(dlg, padding=8)
        frame_custom.pack(fill=tk.X)
        tk.Label(frame_custom, text="Folder Path (e.g. L1\\L2\\L3\\L4...):", font=("", 9, "bold")).pack(anchor=tk.W)
        ent_custom = ttk.Entry(frame_custom)
        ent_custom.insert(0, self.selected_rule.target_folder or "")
        ent_custom.pack(fill=tk.X, pady=2)

        def _on_list_select(event):
            sel = lst_folders.curselection()
            if sel:
                val = all_folders[sel[0]]
                ent_custom.delete(0, tk.END)
                ent_custom.insert(0, val)

        lst_folders.bind("<<ListboxSelect>>", _on_list_select)

        # Bottom buttons
        btn_box = ttk.Frame(dlg, padding=8)
        btn_box.pack(fill=tk.X, side=tk.BOTTOM)

        def _apply():
            chosen = ent_custom.get().strip()
            if not chosen:
                return
            chosen = "\\".join([s.strip() for s in re.split(r'[\\/]', chosen) if s.strip()])
            ok, msg = self.yaml_mgr.move_rule_to_folder(self.selected_rule.id, chosen)
            if not ok:
                messagebox.showwarning("Change Folder", msg, parent=dlg)
                return
            dlg.destroy()
            self._show_toast(f"Moved rule '{self.selected_rule.name}' -> '{chosen}'")
            self.refresh_all()
            rule_iid = f"rule_{self.selected_rule.id}"
            if self.tree.exists(rule_iid):
                self.tree.selection_set(rule_iid)
                self._on_tree_select()

        ttk.Button(btn_box, text="Apply Folder", style="Accent.TButton", command=_apply).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_box, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

    # -----------------------------------------------------------------
    # POOL OPERATIONS
    # -----------------------------------------------------------------
    def _assign_pool_to_rule(self):
        sel_indices = self.lst_pool.curselection()
        if not sel_indices:
            messagebox.showinfo("Notice", "Select an address from the Unclassified Pool first.")
            return
        email = self.lst_pool.get(sel_indices[0])

        dlg = tk.Toplevel(self)
        dlg.title("Assign Address to Rule")
        dlg.geometry("400x320")
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text=f"Assign '{email}' to:", font=("", 9, "bold"), padx=8, pady=6).pack(anchor=tk.W)

        lst = tk.Listbox(dlg, font=("Consolas", 9))
        lst.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        for r in self.yaml_mgr.rules:
            lst.insert(tk.END, f"{r.name}  ({r.target_folder})")

        def _do_assign():
            s = lst.curselection()
            if not s:
                return
            target_rule = self.yaml_mgr.rules[s[0]]
            self.yaml_mgr.add_sender_to_rule_or_group(email, target_rule.id)
            dlg.destroy()
            self._show_toast(f"Assigned '{email}' to '{target_rule.name}'")
            self.refresh_all()

        btn_bar = ttk.Frame(dlg, padding=8)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_bar, text="Assign", command=_do_assign).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_bar, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

    def _remove_from_pool(self):
        sel = list(self.lst_pool.curselection())
        if not sel:
            return
        for idx in reversed(sel):
            val = self.lst_pool.get(idx)
            if val in self.yaml_mgr.unclassified_pool:
                self.yaml_mgr.unclassified_pool.remove(val)
        self.yaml_mgr.save()
        self.refresh_all()
        self._populate_pool_inspector()

    def _clear_pool(self):
        if messagebox.askyesno("Confirm", "Clear all addresses in the Unclassified Pool?"):
            self.yaml_mgr.unclassified_pool = []
            self.yaml_mgr.save()
            self.refresh_all()
            self._populate_pool_inspector()

    # -----------------------------------------------------------------
    # EXCEL / CSV IMPORT
    # -----------------------------------------------------------------
    def _import_addresses_to_rule(self):
        emails = self._read_addresses_from_file()
        if not emails:
            return
        current = [l.strip().lower() for l in self.txt_emails.get("1.0", tk.END).split("\n") if l.strip()]
        combined = sorted(list(set(current + emails)))
        self.txt_emails.delete("1.0", tk.END)
        self.txt_emails.insert(tk.END, "\n".join(combined))
        self._update_rule_count_labels()
        self._refresh_dirty_state()
        messagebox.showinfo("Imported", f"Successfully imported {len(emails)} email addresses.")

    def _read_addresses_from_file(self) -> List[str]:
        filepath = filedialog.askopenfilename(
            title="Import Addresses",
            filetypes=[("Excel & CSV Files", "*.xlsx;*.csv"), ("Excel Files", "*.xlsx"), ("CSV Files", "*.csv")]
        )
        if not filepath:
            return []

        imported_emails = []
        try:
            if filepath.endswith(".csv"):
                import csv
                with open(filepath, "r", encoding="utf-8-sig", errors="ignore") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        for cell in row:
                            if "@" in cell:
                                imported_emails.append(cell.strip().lower())
            else:
                import openpyxl
                wb = openpyxl.load_workbook(filepath, read_only=True)
                ws = wb.active
                for row in ws.iter_rows(values_only=True):
                    for cell in row:
                        if cell and isinstance(cell, str) and "@" in cell:
                            imported_emails.append(cell.strip().lower())

            imported_emails = sorted(list(set(imported_emails)))
            if not imported_emails:
                messagebox.showwarning("Notice", "No email addresses found in file.")
                return []
            return imported_emails
        except Exception as ex:
            messagebox.showerror("Import Error", f"Failed to read file:\n{str(ex)}")
            return []

    # -----------------------------------------------------------------
    # SEARCH & TREE VIEW CONTROLS
    # -----------------------------------------------------------------
    def _on_search_change(self):
        self.search_query = self.ent_search.get().strip()
        self.refresh_all()

    def _expand_all(self):
        for item in self.tree.get_children():
            self._set_tree_open_recursive(item, True)

    def _collapse_all(self):
        for item in self.tree.get_children():
            self._set_tree_open_recursive(item, False)

    def _set_tree_open_recursive(self, iid: str, is_open: bool):
        self.tree.item(iid, open=is_open)
        for child in self.tree.get_children(iid):
            self._set_tree_open_recursive(child, is_open)
