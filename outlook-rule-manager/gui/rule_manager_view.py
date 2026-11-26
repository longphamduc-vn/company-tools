r"""Rule and Address Group Management View with Dynamic Arbitrary Folder Hierarchy & Drag-and-Drop Reorganization."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os
import re
from typing import Optional, List, Tuple, Dict, Any

from core.models import RuleConfig, AddressGroup, pluralize_count
from core.yaml_manager import YamlConfigManager
from core.sync_engine import SyncEngine


class RuleManagerView(ttk.Frame):
    r"""Intuitive Studio for Outlook Rules, Dynamic Folders (arbitrary levels), and Address Groups with Drag-and-Drop."""

    def __init__(self, parent, yaml_mgr: YamlConfigManager, sync_engine: SyncEngine):
        super().__init__(parent)
        self.yaml_mgr = yaml_mgr
        self.sync_engine = sync_engine

        # Selection state
        self.selected_rule: Optional[RuleConfig] = None
        self._editing_rule_group_ids: List[str] = []
        self.selected_folder_path: Optional[str] = None
        self.selected_group: Optional[AddressGroup] = None
        self.selected_pool_item: Optional[str] = None

        # Dirty-tracking & programmatic tree refresh guards
        self.var_rule_name = tk.StringVar()
        self.var_rule_enabled = tk.BooleanVar(value=True)
        self.var_group_name = tk.StringVar()
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

        # Mapping of tree iid to folder path
        self.folder_nodes_map: Dict[str, str] = {}
        self.rule_nodes_map: Dict[str, str] = {}  # iid -> rule_id

        # Scrollable inspector canvases + single shared mousewheel handler
        self._scrollable_canvases: List[tk.Canvas] = []
        self._mousewheel_bound: bool = False
        self._toast_after_id: Optional[str] = None

        self._build_ui()
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.var_rule_name.trace_add("write", lambda *_: self._refresh_dirty_state())
        self.var_rule_enabled.trace_add("write", lambda *_: self._refresh_dirty_state())
        self.var_group_name.trace_add("write", lambda *_: self._refresh_dirty_state())
        self.refresh_all()

    # =================================================================
    # UI CONSTRUCTION
    # =================================================================
    def _build_ui(self):
        # -------------------------------------------------------------
        # TOP TOOLBAR: Dynamic Actions, Search, & Drag Hint
        # -------------------------------------------------------------
        toolbar = tk.Frame(self, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=10, pady=6)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        # Merged creation menu + tree controls
        self.mb_new = ttk.Menubutton(toolbar, text="New")
        self.menu_new = tk.Menu(self.mb_new, tearoff=0)
        self.menu_new.add_command(label="Rule", command=self._add_rule_in_selected_folder)
        self.menu_new.add_command(label="Folder", command=self._add_root_folder)
        self.menu_new.add_command(label="Subfolder", command=self._add_subfolder)
        self.menu_new.add_command(label="Group", command=self._add_group)
        self.mb_new.config(menu=self.menu_new)
        self.mb_new.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)

        ttk.Button(toolbar, text="Expand", command=self._expand_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Collapse", command=self._collapse_all).pack(side=tk.LEFT, padx=2)

        # Search filter entry
        self.ent_search = ttk.Entry(toolbar, width=22)
        self.ent_search.pack(side=tk.RIGHT, padx=4)
        self.ent_search.bind("<KeyRelease>", lambda e: self._on_search_change())
        tk.Label(toolbar, text="Filter:", bg="#ffffff", fg="#475569", font=("", 9, "bold")).pack(side=tk.RIGHT, padx=2)

        # Bottom tip / status bar packed BEFORE paned so text is never clipped at 1120x720
        self._default_tip_text = (
            "Tip: drag rules or folders to reorganize. Right-click for more actions."
        )
        tip_bar = tk.Frame(self, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=4)
        tip_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=(0, 6))
        self.lbl_toast = tk.Label(
            tip_bar,
            text=self._default_tip_text,
            bg="#f8fafc",
            fg="#475569",
            font=("", 8, "italic"),
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=1080,
        )
        self.lbl_toast.pack(fill=tk.X)
        tip_bar.bind("<Configure>", lambda e: self.lbl_toast.config(wraplength=max(200, e.width - 20)))

        # -------------------------------------------------------------
        # MAIN 2-PANE WORKSPACE: Tree (Left) + Studio Inspector (Right)
        # -------------------------------------------------------------
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

        # -------------------------------------------------------------
        # Right Pane: Studio Inspector Card
        # -------------------------------------------------------------
        self.frame_right = tk.Frame(paned, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1)
        paned.add(self.frame_right, weight=6)

        self.inspector_container = tk.Frame(self.frame_right, bg="#ffffff")
        self.inspector_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)

        # Sub-inspectors
        self.frame_empty = tk.Frame(self.inspector_container, bg="#ffffff")
        self.frame_rule = tk.Frame(self.inspector_container, bg="#ffffff")
        self.frame_folder = tk.Frame(self.inspector_container, bg="#ffffff")
        self.frame_group = tk.Frame(self.inspector_container, bg="#ffffff")
        self.frame_pool = tk.Frame(self.inspector_container, bg="#ffffff")

        self._build_empty_inspector()
        self._build_rule_inspector()
        self._build_folder_inspector()
        self._build_group_inspector()
        self._build_pool_inspector()

        # Show empty inspector initially
        self._show_inspector(self.frame_empty)

    # -----------------------------------------------------------------
    # SUB-INSPECTOR BUILDERS
    # -----------------------------------------------------------------
    def _build_empty_inspector(self):
        box = tk.Frame(self.frame_empty, bg="#ffffff")
        box.pack(expand=True)
        tk.Label(box, text="Select a Folder, Rule, or Address Group", font=("", 12, "bold"), fg="#64748b", bg="#ffffff").pack(pady=4)
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
        self.ent_rule_name = ttk.Entry(row1, font=("", 9), width=26, textvariable=self.var_rule_name)
        self.ent_rule_name.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

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

        ttk.Button(btn_bar_rule, text="Duplicate Rule", command=self._duplicate_selected_rule).pack(side=tk.LEFT, padx=4)
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

        # Linked Groups (above Emails)
        frame_linked_groups = tk.Frame(rule_cond_body, bg="#ffffff")
        frame_linked_groups.pack(fill=tk.X, pady=(0, 4))

        row_grp_hdr = tk.Frame(frame_linked_groups, bg="#ffffff")
        row_grp_hdr.pack(fill=tk.X, pady=(0, 2))
        tk.Label(row_grp_hdr, text="Linked Groups:", bg="#ffffff", font=("", 8, "bold"), fg="#475569").pack(side=tk.LEFT)
        ttk.Button(row_grp_hdr, text="Link Group...", command=self._link_group_to_rule).pack(side=tk.LEFT, padx=(6, 2))
        ttk.Button(row_grp_hdr, text="Unlink", command=self._unlink_group_from_rule).pack(side=tk.LEFT, padx=2)

        self.lst_rule_groups = tk.Listbox(frame_linked_groups, font=("Consolas", 9), height=2, selectmode=tk.EXTENDED)
        self.lst_rule_groups.pack(fill=tk.X)

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

    def _build_group_inspector(self):
        header = tk.Frame(self.frame_group, bg="#f1f5f9", padx=10, pady=8, highlightbackground="#e2e8f0", highlightthickness=1)
        header.pack(fill=tk.X, pady=(0, 8))

        self.lbl_group_title = tk.Label(
            header,
            text="Shared Address Group: Engineering SCADA Team",
            bg="#f1f5f9",
            fg="#0f172a",
            font=("", 11, "bold")
        )
        self.lbl_group_title.pack(anchor=tk.W)

        # Group Name
        row_name = tk.Frame(self.frame_group, bg="#ffffff")
        row_name.pack(fill=tk.X, pady=(0, 8))
        tk.Label(row_name, text="Group Name:", bg="#ffffff", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        self.ent_group_name = ttk.Entry(row_name, textvariable=self.var_group_name, width=28)
        self.ent_group_name.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Action bar packed BEFORE scrollable middle content so buttons always stay visible
        btn_bar_grp = tk.Frame(self.frame_group, bg="#ffffff")
        btn_bar_grp.pack(fill=tk.X, side=tk.BOTTOM)
        self.btn_save_group = ttk.Button(
            btn_bar_grp, text="Save Group to YAML", style="Accent.TButton", command=self._save_group_changes
        )
        self.btn_save_group.pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar_grp, text="Import CSV/Excel...", command=self._import_addresses_to_group).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar_grp, text="Delete Group", style="Danger.TButton", command=self._delete_selected_group).pack(side=tk.RIGHT, padx=2)

        # Scrollable Group Members area
        grp_scroll_box = tk.Frame(self.frame_group, bg="#ffffff")
        grp_scroll_box.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.group_scroll_canvas, grp_inner = self._create_scrollable_section(grp_scroll_box, bg="#ffffff")

        tk.Label(grp_inner, text="Member Emails (one per line):", bg="#ffffff", font=("", 8, "bold")).pack(anchor=tk.W)
        self.txt_group_emails = tk.Text(grp_inner, font=("Consolas", 9), height=6)
        self.txt_group_emails.pack(fill=tk.X, pady=(0, 6))
        self.txt_group_emails.bind("<KeyRelease>", lambda _e: self._refresh_dirty_state())
        self.txt_group_emails.bind("<FocusOut>", lambda _e: self._refresh_dirty_state())

        tk.Label(grp_inner, text="Member Domains (e.g. @omron.com, one per line):", bg="#ffffff", font=("", 8, "bold")).pack(anchor=tk.W)
        self.txt_group_domains = tk.Text(grp_inner, font=("Consolas", 9), height=3)
        self.txt_group_domains.pack(fill=tk.X, pady=(0, 4))
        self.txt_group_domains.bind("<KeyRelease>", lambda _e: self._refresh_dirty_state())
        self.txt_group_domains.bind("<FocusOut>", lambda _e: self._refresh_dirty_state())

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
        for f in [self.frame_empty, self.frame_rule, self.frame_folder, self.frame_group, self.frame_pool]:
            f.pack_forget()
        target_frame.pack(fill=tk.BOTH, expand=True)

    # =================================================================
    # TREE REFRESH & DYNAMIC HIERARCHY POPULATION (ARBITRARY DEPTH)
    # =================================================================
    def refresh_all(self, preserve_selection_iid: Optional[str] = None):
        """Rebuild the visual tree supporting arbitrary folder levels from YamlConfigManager."""
        self._in_tree_transition = True
        try:
            self.tree.delete(*self.tree.get_children())
            self.folder_nodes_map.clear()
            self.rule_nodes_map.clear()

            q = self.search_query.lower()

            # ---------------------------------------------------------
            # Category 1: Folders & Rules (Arbitrary Depth)
            # ---------------------------------------------------------
            root_hier_id = "__HIERARCHY__"
            self.tree.insert("", tk.END, iid=root_hier_id, text="Folders & Rules", values=("Root",), open=True)

            all_folders = self.yaml_mgr.get_all_folders()

            for fld in all_folders:
                parts = [p.strip() for p in re.split(r'[\\/]', fld) if p.strip()]
                parent_id = root_hier_id
                accum_path = ""
                for depth, part in enumerate(parts):
                    accum_path = f"{accum_path}\\{part}" if accum_path else part
                    fld_node_id = f"fld_{accum_path.lower().replace(' ', '_')}"
                    if fld_node_id not in self.folder_nodes_map:
                        self.tree.insert(
                            parent_id, tk.END, iid=fld_node_id,
                            text=f"📁 {part}", values=(f"Level {depth+1}",), open=True
                        )
                        self.folder_nodes_map[fld_node_id] = accum_path
                    parent_id = fld_node_id

            for rule in self.yaml_mgr.rules:
                all_emails, all_domains, keywords = self.sync_engine.get_rule_conditions(rule)

                if q:
                    match_name = q in rule.name.lower()
                    match_folder = q in (rule.target_folder or "").lower()
                    match_emails = any(q in e.lower() for e in all_emails)
                    match_domains = any(q in d.lower() for d in all_domains)
                    match_kw = any(q in kw.lower() for kw in keywords)
                    if not (match_name or match_folder or match_emails or match_domains or match_kw):
                        continue

                raw_folder = rule.target_folder or "_Unclassified"
                fld_node_id = f"fld_{raw_folder.lower().replace(' ', '_')}"

                if fld_node_id not in self.folder_nodes_map:
                    parts = [p.strip() for p in re.split(r'[\\/]', raw_folder) if p.strip()]
                    parent_id = root_hier_id
                    accum = ""
                    for d, pt in enumerate(parts):
                        accum = f"{accum}\\{pt}" if accum else pt
                        curr_fid = f"fld_{accum.lower().replace(' ', '_')}"
                        if curr_fid not in self.folder_nodes_map:
                            self.tree.insert(
                                parent_id, tk.END, iid=curr_fid,
                                text=f"📁 {pt}", values=(f"Level {d+1}",), open=True
                            )
                            self.folder_nodes_map[curr_fid] = accum
                        parent_id = curr_fid
                    fld_node_id = parent_id

                summary = self.sync_engine.get_rule_quota_summary(rule)
                total_senders = summary["email_count"] + summary["domain_count"]
                rule_iid = f"rule_{rule.id}"
                if rule.enabled:
                    rule_label = f"⚡ {rule.name}"
                    rule_tags = ("rule_enabled",)
                else:
                    rule_label = f"⏸ {rule.name} (disabled)"
                    rule_tags = ("rule_disabled",)
                self.tree.insert(
                    fld_node_id, tk.END, iid=rule_iid,
                    text=rule_label,
                    values=(pluralize_count(total_senders, "sender"),),
                    open=False,
                    tags=rule_tags,
                )
                self.rule_nodes_map[rule_iid] = rule.id

            # ---------------------------------------------------------
            # Category 2: Shared Address Groups
            # ---------------------------------------------------------
            root_grp_id = "__GROUPS__"
            self.tree.insert("", tk.END, iid=root_grp_id, text="Shared Address Groups", values=("Groups",), open=True)
            for g_id, grp in self.yaml_mgr.groups.items():
                if q and not (q in grp.name.lower() or any(q in e.lower() for e in grp.emails)):
                    continue
                count = len(grp.emails) + len(grp.domains)
                grp_iid = f"grp_{g_id}"
                self.tree.insert(
                    root_grp_id, tk.END, iid=grp_iid,
                    text=f"👥 {grp.name}", values=(pluralize_count(count, "member"),)
                )

            # ---------------------------------------------------------
            # Category 3: Unclassified Pool
            # ---------------------------------------------------------
            root_pool_id = "__POOL__"
            pool_count = len(self.yaml_mgr.unclassified_pool)
            self.tree.insert("", tk.END, iid=root_pool_id, text=f"Unclassified Pool ({pool_count})", values=("Pool",), open=True)
            for email in self.yaml_mgr.unclassified_pool:
                if q and q not in email.lower():
                    continue
                pool_iid = f"pool_{email}"
                self.tree.insert(root_pool_id, tk.END, iid=pool_iid, text=f"📧 {email}", values=("Orphaned",))

            target_sel = preserve_selection_iid or self._current_selected_iid
            if target_sel and self.tree.exists(target_sel):
                self.tree.selection_set(target_sel)
        finally:
            self.update_idletasks()
            self._in_tree_transition = False

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

    def _get_current_rule_form_values(self) -> Tuple[str, bool, List[str], List[str], List[str], List[str]]:
        name = self.var_rule_name.get().strip()
        enabled = bool(self.var_rule_enabled.get())
        groups = list(self._editing_rule_group_ids)
        emails = [l.strip().lower() for l in self.txt_emails.get("1.0", tk.END).split("\n") if l.strip()]
        raw_domains = self.txt_domains.get("1.0", tk.END).split("\n")
        raw_keywords = self.txt_keywords.get("1.0", tk.END).split("\n")
        return (
            name,
            enabled,
            groups,
            sorted(list(set(emails))),
            sorted(list(set(YamlConfigManager.normalize_domains(raw_domains)))),
            YamlConfigManager.normalize_keywords(raw_keywords),
        )

    def _update_rule_count_labels(self):
        _, _, _, emails, domains, keywords = self._get_current_rule_form_values()
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
        f_name, f_enabled, f_groups, f_emails, f_domains, f_keywords = self._get_current_rule_form_values()
        saved_emails = sorted(list(set(e.strip().lower() for e in (r.emails or []) if e.strip())))
        saved_domains = sorted(list(set(YamlConfigManager.normalize_domains(r.domains or []))))
        saved_keywords = YamlConfigManager.normalize_keywords(r.subject_keywords or [])
        return (
            f_name != (r.name or "").strip()
            or f_enabled != bool(r.enabled)
            or f_groups != list(r.groups or [])
            or f_emails != saved_emails
            or f_domains != saved_domains
            or f_keywords != saved_keywords
        )

    def _get_current_group_form_values(self) -> Tuple[str, List[str], List[str]]:
        name = self.var_group_name.get().strip()
        emails = [l.strip().lower() for l in self.txt_group_emails.get("1.0", tk.END).split("\n") if l.strip()]
        raw_domains = self.txt_group_domains.get("1.0", tk.END).split("\n")
        return (
            name,
            sorted(list(set(emails))),
            sorted(list(set(YamlConfigManager.normalize_domains(raw_domains)))),
        )

    def is_group_dirty(self) -> bool:
        if not self.selected_group or not self.frame_group.winfo_manager():
            return False
        g = self.selected_group
        f_name, f_emails, f_domains = self._get_current_group_form_values()
        saved_emails = sorted(list(set(e.strip().lower() for e in (g.emails or []) if e.strip())))
        saved_domains = sorted(list(set(YamlConfigManager.normalize_domains(g.domains or []))))
        return (
            f_name != (g.name or "").strip()
            or f_emails != saved_emails
            or f_domains != saved_domains
        )

    def has_unsaved_changes(self) -> bool:
        return self.is_rule_dirty() or self.is_group_dirty()

    def _refresh_dirty_state(self):
        if self._populating_inspector:
            return
        if self.is_rule_dirty():
            self.btn_save_rule.config(text="Save Changes ●", style="DirtySave.TButton")
        else:
            self.btn_save_rule.config(text="Save Rule to YAML", style="Accent.TButton")

        if self.is_group_dirty():
            self.btn_save_group.config(text="Save Changes ●", style="DirtySave.TButton")
        else:
            self.btn_save_group.config(text="Save Group to YAML", style="Accent.TButton")

    def confirm_pending_changes(self, reset_if_discard: bool = True, refresh_tree: bool = True) -> bool:
        """Prompt user if rule or group inspector has unsaved changes.

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

        if self.is_group_dirty() and self.selected_group is not None:
            ans = messagebox.askyesnocancel(
                "Unsaved Changes",
                f"Save changes to '{self.selected_group.name}'?",
                icon=messagebox.WARNING,
            )
            if ans is None:
                return False
            if ans:
                return self._save_group_changes(refresh_tree=refresh_tree, select_after=False)
            if reset_if_discard:
                self._populate_group_inspector(self.selected_group)
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
            self.selected_group = None
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

        # 1. Selected a Rule
        if iid.startswith("rule_"):
            rule_id = self.rule_nodes_map.get(iid)
            self.selected_rule = next((r for r in self.yaml_mgr.rules if r.id == rule_id), None)
            self.selected_folder_path = None
            self.selected_group = None
            self.selected_pool_item = None
            if self.selected_rule:
                self._populate_rule_inspector(self.selected_rule)
                self._show_inspector(self.frame_rule)
            return

        # 2. Selected a Folder (Any Level: L1, L2, L3, L4...)
        if iid.startswith("fld_"):
            self.selected_folder_path = self.folder_nodes_map.get(iid)
            self.selected_rule = None
            self.selected_group = None
            self.selected_pool_item = None
            if self.selected_folder_path:
                self._populate_folder_inspector(self.selected_folder_path)
                self._show_inspector(self.frame_folder)
            self._refresh_dirty_state()
            return

        # 3. Selected a Group
        if iid.startswith("grp_"):
            grp_id = iid.replace("grp_", "", 1)
            self.selected_group = self.yaml_mgr.groups.get(grp_id)
            self.selected_rule = None
            self.selected_folder_path = None
            self.selected_pool_item = None
            if self.selected_group:
                self._populate_group_inspector(self.selected_group)
                self._show_inspector(self.frame_group)
            return

        # 4. Selected Pool root or pool item
        if iid == "__POOL__" or iid.startswith("pool_"):
            self.selected_pool_item = iid.replace("pool_", "", 1) if iid.startswith("pool_") else None
            self.selected_rule = None
            self.selected_folder_path = None
            self.selected_group = None
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

            # Core properties
            self.ent_rule_name.delete(0, tk.END)
            self.ent_rule_name.insert(0, rule.name)
            self.var_rule_enabled.set(rule.enabled)

            # Linked Groups
            self._editing_rule_group_ids = list(rule.groups)
            self._refresh_linked_groups_listbox()

            # Quota Meter (uses live editing group IDs + SyncEngine compiler)
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

        summary = self.sync_engine.get_rule_quota_summary(
            self.selected_rule, group_ids=self._editing_rule_group_ids
        )
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

    def _populate_group_inspector(self, group: AddressGroup):
        self._populating_inspector = True
        try:
            self.lbl_group_title.config(text=f"Shared Address Group: {group.name}")
            self.ent_group_name.delete(0, tk.END)
            self.ent_group_name.insert(0, group.name)

            self.txt_group_emails.delete("1.0", tk.END)
            self.txt_group_emails.insert(tk.END, "\n".join(sorted(group.emails)))

            self.txt_group_domains.delete("1.0", tk.END)
            self.txt_group_domains.insert(tk.END, "\n".join(sorted(group.domains)))
            self.group_scroll_canvas.yview_moveto(0)
        finally:
            self._populating_inspector = False
        self._refresh_dirty_state()

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

        # Hover hit test on tree
        hover_iid = self.tree.identify_row(event.y)
        if hover_iid:
            self.tree.selection_set(hover_iid)

    def _on_drag_release(self, event):
        """Execute folder or rule move upon drop."""
        if self.drag_window:
            self.drag_window.destroy()
            self.drag_window = None

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
            if target_iid.startswith("fld_"):
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

            if dest_folder:
                self.yaml_mgr.move_rule_to_folder(rule_id, dest_folder)
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

            source_parts = [p.strip() for p in re.split(r'[\\/]', source_folder) if p.strip()]
            folder_name = source_parts[-1]

            # Dropped onto Root Hierarchy: Promote directly to Root (Level 1)!
            if target_iid == "__HIERARCHY__":
                ok, res = self.yaml_mgr.promote_folder_to_root(source_folder)
                if ok:
                    self._show_toast(f"Promoted '{folder_name}' to Root (Level 1)")
                    self.refresh_all()
                    new_fld_iid = f"fld_{res.lower().replace(' ', '_')}"
                    if self.tree.exists(new_fld_iid):
                        self.tree.selection_set(new_fld_iid)
                        self._on_tree_select()
                else:
                    messagebox.showwarning("Promote Folder", res)
                return

            # Dropped onto another Folder node
            dest_parent = ""
            if target_iid.startswith("fld_"):
                dest_parent = self.folder_nodes_map.get(target_iid)
            elif target_iid.startswith("rule_"):
                target_rule_id = self.rule_nodes_map.get(target_iid)
                target_rule = next((r for r in self.yaml_mgr.rules if r.id == target_rule_id), None)
                dest_parent = target_rule.target_folder if target_rule else ""
            else:
                return

            ok, res = self.yaml_mgr.move_folder_hierarchy(source_folder, dest_parent)
            if ok:
                new_parts = [p.strip() for p in re.split(r'[\\/]', res) if p.strip()]
                new_depth = len(new_parts)
                self._show_toast(f"Moved '{folder_name}' to Level {new_depth}: '{res}'")
                self.refresh_all()
                new_fld_iid = f"fld_{res.lower().replace(' ', '_')}"
                if self.tree.exists(new_fld_iid):
                    self.tree.selection_set(new_fld_iid)
                    self._on_tree_select()
            else:
                messagebox.showwarning("Move Folder", res)
            return

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
            # Dropped onto a Group
            elif target_iid.startswith("grp_"):
                grp_id = target_iid.replace("grp_", "", 1)
                grp = self.yaml_mgr.groups.get(grp_id)
                if grp and email not in grp.emails:
                    grp.emails.append(email)
                    if email in self.yaml_mgr.unclassified_pool:
                        self.yaml_mgr.unclassified_pool.remove(email)
                    self.yaml_mgr.save()
                    self._show_toast(f"Added '{email}' to group '{grp.name}'")
                    self.refresh_all()
                    self.tree.selection_set(target_iid)
                    self._on_tree_select()

    def _get_drag_source_title(self, iid: str) -> str:
        """Return human-readable title for dragging item."""
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

    def _show_toast(self, message: str):
        """Display non-blocking status notification in bottom tip bar."""
        self.lbl_toast.config(text=message, fg="#0284c7")
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
            menu.add_command(label="Move to Folder...", command=self._open_folder_picker_dialog)
            menu.add_command(label="Duplicate Rule", command=self._duplicate_selected_rule)
            menu.add_separator()
            menu.add_command(label="Delete Rule", command=self._delete_selected)

        # Group context menu
        elif iid.startswith("grp_"):
            menu.add_command(label="Rename Group...", command=self._rename_selected_group)
            menu.add_separator()
            menu.add_command(label="Delete Group", command=self._delete_selected_group)

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
        self.yaml_mgr.add_custom_folder(folder_name)
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
        full_sub_path = f"{parent_path}\\{sub_name}"
        self.yaml_mgr.add_custom_folder(full_sub_path)
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
        """Create new rule inside currently selected folder."""
        dest_folder = self.selected_folder_path
        if not dest_folder:
            if self.selected_rule and self.selected_rule.target_folder:
                dest_folder = self.selected_rule.target_folder
            else:
                folders = self.yaml_mgr.get_all_folders()
                dest_folder = folders[0] if folders else "General"

        rule_name = f"New Rule {len(self.yaml_mgr.rules) + 1}"
        new_id = self.yaml_mgr.generate_rule_id(rule_name)
        new_rule = RuleConfig(
            id=new_id,
            name=rule_name,
            enabled=True,
            target_store="active_archive",
            target_folder=dest_folder
        )
        self.yaml_mgr.rules.append(new_rule)
        self.yaml_mgr.save()
        self._show_toast(f"Created rule '{new_rule.name}' in '{dest_folder}'")
        self.refresh_all()

        rule_iid = f"rule_{new_id}"
        if self.tree.exists(rule_iid):
            self.tree.selection_set(rule_iid)
            self._on_tree_select()

    def _save_rule_changes(self, refresh_tree: bool = True, select_after: bool = True) -> bool:
        if not self.selected_rule:
            return True

        name, enabled, groups, emails, domains, keywords = self._get_current_rule_form_values()
        if not name:
            messagebox.showwarning("Notice", "Rule name cannot be empty.")
            return False

        self.selected_rule.name = name
        self.selected_rule.enabled = enabled
        self.selected_rule.groups = groups
        self.selected_rule.emails = emails
        self.selected_rule.domains = domains
        self.selected_rule.subject_keywords = keywords

        self.yaml_mgr.save()
        self._show_toast(f"Saved rule '{name}' to rules.yaml")
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

    def _duplicate_selected_rule(self):
        if not self.selected_rule:
            messagebox.showwarning("Notice", "Select a rule to duplicate.")
            return
        if not self.confirm_pending_changes(reset_if_discard=True):
            return
        dup = self.yaml_mgr.duplicate_rule(self.selected_rule.id)
        if dup:
            self._show_toast(f"Duplicated: '{dup.name}'")
            dup_iid = f"rule_{dup.id}"
            self.refresh_all()
            if self.tree.exists(dup_iid):
                self._select_tree_iid_silently(dup_iid)
                self.selected_rule = dup
                self._populate_rule_inspector(dup)
                self._show_inspector(self.frame_rule)

    def _delete_selected(self):
        """Delete currently selected rule or folder."""
        if self.selected_rule:
            rule = self.selected_rule
            if rule.id == "rule_unclassified":
                messagebox.showwarning("Notice", "Cannot delete the default [Unclassified] fallback rule.")
                return

            confirm = messagebox.askyesno(
                "Confirm Delete Rule",
                f"Are you sure you want to delete rule '{rule.name}'?\n\n"
                f"Addresses will be safely moved to the Unclassified Pool.",
                icon=messagebox.WARNING
            )
            if confirm:
                self.yaml_mgr.remove_rule_and_repool(rule.id)
                self._show_toast(f"Deleted rule '{rule.name}'")
                self.selected_rule = None
                self._current_selected_iid = None
                self.refresh_all()
                self._show_inspector(self.frame_empty)
                self._refresh_dirty_state()
        elif self.selected_folder_path:
            self._delete_selected_folder()

    # -----------------------------------------------------------------
    # CONDITION EDITORS & CHIPS
    # -----------------------------------------------------------------
    def _refresh_linked_groups_listbox(self):
        self.lst_rule_groups.delete(0, tk.END)
        for g_id in self._editing_rule_group_ids:
            grp = self.yaml_mgr.groups.get(g_id)
            if grp:
                label = (
                    f"{grp.name} ({pluralize_count(len(grp.emails), 'email')}, "
                    f"{pluralize_count(len(grp.domains), 'domain')})"
                )
            else:
                label = f"{g_id} (missing group)"
            self.lst_rule_groups.insert(tk.END, label)

    def _link_group_to_rule(self):
        if not self.selected_rule:
            return
        available = [
            grp for g_id, grp in self.yaml_mgr.groups.items()
            if g_id not in self._editing_rule_group_ids
        ]
        if not available:
            messagebox.showinfo("Link Group", "No additional groups available to link.")
            return

        dlg = tk.Toplevel(self)
        dlg.title("Link Address Group")
        dlg.geometry("380x280")
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(
            dlg,
            text=f"Select group(s) to link to '{self.selected_rule.name}':",
            font=("", 9, "bold"),
            padx=10,
            pady=8,
        ).pack(anchor=tk.W)

        lst = tk.Listbox(dlg, font=("Consolas", 9), selectmode=tk.EXTENDED)
        lst.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        for grp in available:
            lst.insert(
                tk.END,
                f"{grp.name} ({pluralize_count(len(grp.emails), 'email')}, {pluralize_count(len(grp.domains), 'domain')})",
            )

        def _apply():
            sel = lst.curselection()
            if not sel:
                return
            for idx in sel:
                g_id = available[idx].id
                if g_id not in self._editing_rule_group_ids:
                    self._editing_rule_group_ids.append(g_id)
            self._refresh_linked_groups_listbox()
            self._update_rule_quota_display()
            self._refresh_dirty_state()
            dlg.destroy()

        btn_bar = ttk.Frame(dlg, padding=8)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_bar, text="Link Selected", style="Accent.TButton", command=_apply).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_bar, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)

    def _unlink_group_from_rule(self):
        sel = list(self.lst_rule_groups.curselection())
        if not sel:
            return
        for idx in reversed(sel):
            if 0 <= idx < len(self._editing_rule_group_ids):
                self._editing_rule_group_ids.pop(idx)
        self._refresh_linked_groups_listbox()
        self._update_rule_quota_display()
        self._refresh_dirty_state()

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
            self.selected_rule.target_folder = chosen
            self.yaml_mgr.save()
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
    # GROUP & POOL OPERATIONS
    # -----------------------------------------------------------------
    def _add_group(self):
        g_name = simpledialog.askstring("New Address Group", "Enter Group Name:")
        if not g_name:
            return
        g_id = self.yaml_mgr.generate_group_id(g_name)
        new_g = AddressGroup(id=g_id, name=g_name)
        self.yaml_mgr.groups[g_id] = new_g
        self.yaml_mgr.save()
        self._show_toast(f"Created group '{g_name}'")
        self.refresh_all()
        grp_iid = f"grp_{g_id}"
        if self.tree.exists(grp_iid):
            self.tree.selection_set(grp_iid)
            self._on_tree_select()

    def _save_group_changes(self, refresh_tree: bool = True, select_after: bool = True) -> bool:
        if not self.selected_group:
            return True
        name, emails, domains = self._get_current_group_form_values()
        if not name:
            messagebox.showwarning("Notice", "Group name cannot be empty.")
            return False

        self.selected_group.name = name
        self.selected_group.emails = emails
        self.selected_group.domains = domains
        self.yaml_mgr.save()
        self._show_toast(f"Saved group '{name}'")
        self._refresh_dirty_state()

        if refresh_tree:
            self.refresh_all()

        if select_after:
            grp_iid = f"grp_{self.selected_group.id}"
            if self.tree.exists(grp_iid):
                self._select_tree_iid_silently(grp_iid)
                self._populate_group_inspector(self.selected_group)
                self._show_inspector(self.frame_group)
        return True

    def _rename_selected_group(self):
        if not self.selected_group:
            return
        new_name = simpledialog.askstring("Rename Group", "Enter new name:", initialvalue=self.selected_group.name)
        if new_name and new_name != self.selected_group.name:
            self.selected_group.name = new_name
            self.yaml_mgr.save()
            self._show_toast(f"Renamed group to '{new_name}'")
            grp_iid = f"grp_{self.selected_group.id}"
            self.refresh_all(preserve_selection_iid=grp_iid)
            self._populate_group_inspector(self.selected_group)

    def _delete_selected_group(self):
        if not self.selected_group:
            return
        g_id = self.selected_group.id
        g_name = self.selected_group.name
        choice = messagebox.askyesnocancel(
            "Delete Group",
            f"Delete group '{g_name}'?\n\n"
            f"Yes: Delete group and move its emails to Unclassified Pool\n"
            f"No: Delete group without repooling emails\n"
            f"Cancel: Keep group",
            icon=messagebox.WARNING
        )
        if choice is None:
            return

        if self.yaml_mgr.delete_group(g_id, repool_emails=bool(choice)):
            self._show_toast("Deleted group")
            self.selected_group = None
            self._current_selected_iid = None
            self.refresh_all()
            self._show_inspector(self.frame_empty)
            self._refresh_dirty_state()

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

    def _import_addresses_to_group(self):
        emails = self._read_addresses_from_file()
        if not emails:
            return
        current = [l.strip().lower() for l in self.txt_group_emails.get("1.0", tk.END).split("\n") if l.strip()]
        combined = sorted(list(set(current + emails)))
        self.txt_group_emails.delete("1.0", tk.END)
        self.txt_group_emails.insert(tk.END, "\n".join(combined))
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
