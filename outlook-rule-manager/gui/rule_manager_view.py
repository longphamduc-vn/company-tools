r"""Rule and Address Group Management View with Dynamic Arbitrary Folder Hierarchy & Drag-and-Drop Reorganization."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os
import re
from typing import Optional, List, Tuple, Dict, Any

from core.models import RuleConfig, AddressGroup
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
        self.selected_folder_path: Optional[str] = None
        self.selected_group: Optional[AddressGroup] = None
        self.selected_pool_item: Optional[str] = None

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

        # Mode toggle: 'visual' vs 'bulk' for conditions
        self.condition_mode: str = "visual"

        self._build_ui()
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

        # Quick action buttons (Dynamic arbitrary levels)
        ttk.Button(toolbar, text="+ Root Folder (L1)", command=self._add_root_folder).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(toolbar, text="+ Subfolder (L+1)", command=self._add_subfolder).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="+ New Rule", command=self._add_rule_in_selected_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="+ New Group", command=self._add_group).pack(side=tk.LEFT, padx=4)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        ttk.Button(toolbar, text="Expand All", command=self._expand_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Collapse All", command=self._collapse_all).pack(side=tk.LEFT, padx=2)

        # Toast notification label
        self.lbl_toast = tk.Label(
            toolbar,
            text="Tip: Folders have flexible levels. Drag to Root for Level 1, or drop into any folder for Level 2, 3, 4...",
            bg="#ffffff",
            fg="#64748b",
            font=("", 8, "italic")
        )
        self.lbl_toast.pack(side=tk.LEFT, padx=12)

        # Search filter entry
        self.ent_search = ttk.Entry(toolbar, width=22)
        self.ent_search.pack(side=tk.RIGHT, padx=4)
        self.ent_search.bind("<KeyRelease>", lambda e: self._on_search_change())
        tk.Label(toolbar, text="Filter:", bg="#ffffff", fg="#475569", font=("", 9, "bold")).pack(side=tk.RIGHT, padx=2)

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
            text="DYNAMIC FOLDER HIERARCHY & RULES NAVIGATOR",
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
        self.tree.heading("#0", text="Folder Hierarchy (L1 \\ L2 \\ L3 \\ L4...)")
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

        # Left Bottom Quick Action Bar
        btn_bar_left = tk.Frame(self.frame_left, bg="#f8fafc", padx=4, pady=4)
        btn_bar_left.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_bar_left, text="Delete Selected", command=self._delete_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar_left, text="Duplicate Rule", command=self._duplicate_selected_rule).pack(side=tk.LEFT, padx=2)

        # -------------------------------------------------------------
        # Right Pane: Studio Inspector Card
        # -------------------------------------------------------------
        self.frame_right = tk.Frame(paned, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1)
        paned.add(self.frame_right, weight=6)

        self.inspector_container = tk.Frame(self.frame_right, bg="#ffffff")
        self.inspector_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

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

    def _build_rule_inspector(self):
        # 1. Breadcrumb Path Bar (Dynamic Levels)
        self.bar_breadcrumb = tk.Frame(self.frame_rule, bg="#f1f5f9", padx=8, pady=6, highlightbackground="#e2e8f0", highlightthickness=1)
        self.bar_breadcrumb.pack(fill=tk.X, pady=(0, 6))

        self.lbl_breadcrumb = tk.Label(
            self.bar_breadcrumb,
            text="Folder: [L1] Engineering_Team > [L2] SCADA_Part > [L3] PLC_Unit",
            bg="#f1f5f9",
            fg="#0369a1",
            font=("", 9, "bold")
        )
        self.lbl_breadcrumb.pack(side=tk.LEFT)

        ttk.Button(self.bar_breadcrumb, text="Change Folder...", command=self._open_folder_picker_dialog).pack(side=tk.RIGHT, padx=2)

        # 2. Rule Name & Active Status Card
        card_header = tk.Frame(self.frame_rule, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=8)
        card_header.pack(fill=tk.X, pady=(0, 6))

        row1 = tk.Frame(card_header, bg="#ffffff")
        row1.pack(fill=tk.X)

        tk.Label(row1, text="Rule Name:", bg="#ffffff", font=("", 9, "bold"), fg="#334155").pack(side=tk.LEFT, padx=(0, 6))
        self.ent_rule_name = ttk.Entry(row1, font=("", 9), width=28)
        self.ent_rule_name.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self.var_rule_enabled = tk.BooleanVar(value=True)
        self.chk_rule_enabled = ttk.Checkbutton(row1, text="Active in Outlook", variable=self.var_rule_enabled)
        self.chk_rule_enabled.pack(side=tk.RIGHT)

        # Quota meter
        self.lbl_quota = tk.Label(
            card_header,
            text="Outlook Quota: 4 / 40 recipients (1 native sub-rule) - OK",
            bg="#ffffff",
            fg="#16a34a",
            font=("", 8, "bold")
        )
        self.lbl_quota.pack(anchor=tk.W, pady=(6, 0))

        # 3. Recipients & Conditions Notebook / Mode Switcher
        card_cond = tk.LabelFrame(self.frame_rule, text="Filter Conditions (Emails & Domains)", bg="#ffffff", padx=8, pady=8)
        card_cond.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        mode_strip = tk.Frame(card_cond, bg="#ffffff")
        mode_strip.pack(fill=tk.X, pady=(0, 4))

        self.btn_mode_visual = tk.Button(
            mode_strip, text="Visual Chips", relief="flat", bg="#0284c7", fg="#ffffff",
            font=("", 8, "bold"), padx=8, pady=2, command=lambda: self._set_condition_mode("visual")
        )
        self.btn_mode_visual.pack(side=tk.LEFT, padx=(0, 2))

        self.btn_mode_bulk = tk.Button(
            mode_strip, text="Bulk Text Editor", relief="flat", bg="#e2e8f0", fg="#475569",
            font=("", 8, "bold"), padx=8, pady=2, command=lambda: self._set_condition_mode("bulk")
        )
        self.btn_mode_bulk.pack(side=tk.LEFT, padx=2)

        ttk.Button(mode_strip, text="Import CSV/Excel...", command=self._import_addresses_to_rule).pack(side=tk.RIGHT)

        # Container for Visual Mode vs Bulk Mode
        self.box_cond_container = tk.Frame(card_cond, bg="#ffffff")
        self.box_cond_container.pack(fill=tk.BOTH, expand=True)

        # --- A. Visual Mode Frames ---
        self.box_visual = tk.Frame(self.box_cond_container, bg="#ffffff")

        # Visual Emails
        frame_vis_emails = tk.Frame(self.box_visual, bg="#ffffff")
        frame_vis_emails.pack(fill=tk.BOTH, expand=True, pady=2)

        row_add_email = tk.Frame(frame_vis_emails, bg="#ffffff")
        row_add_email.pack(fill=tk.X, pady=(0, 2))
        tk.Label(row_add_email, text="Direct Emails:", bg="#ffffff", font=("", 8, "bold"), fg="#475569").pack(side=tk.LEFT)
        self.ent_add_email = ttk.Entry(row_add_email, width=26)
        self.ent_add_email.pack(side=tk.LEFT, padx=4)
        self.ent_add_email.bind("<Return>", lambda e: self._add_email_chip())
        ttk.Button(row_add_email, text="+ Add", command=self._add_email_chip).pack(side=tk.LEFT)
        ttk.Button(row_add_email, text="Remove Selected", command=self._remove_email_chip).pack(side=tk.RIGHT)

        self.lst_emails = tk.Listbox(frame_vis_emails, font=("Consolas", 9), height=5, selectmode=tk.EXTENDED)
        self.lst_emails.pack(fill=tk.BOTH, expand=True)

        # Visual Domains
        frame_vis_domains = tk.Frame(self.box_visual, bg="#ffffff")
        frame_vis_domains.pack(fill=tk.BOTH, expand=True, pady=(6, 2))

        row_add_dom = tk.Frame(frame_vis_domains, bg="#ffffff")
        row_add_dom.pack(fill=tk.X, pady=(0, 2))
        tk.Label(row_add_dom, text="Domains (e.g. @company.com):", bg="#ffffff", font=("", 8, "bold"), fg="#475569").pack(side=tk.LEFT)
        self.ent_add_domain = ttk.Entry(row_add_dom, width=20)
        self.ent_add_domain.pack(side=tk.LEFT, padx=4)
        self.ent_add_domain.bind("<Return>", lambda e: self._add_domain_chip())
        ttk.Button(row_add_dom, text="+ Add Domain", command=self._add_domain_chip).pack(side=tk.LEFT)
        ttk.Button(row_add_dom, text="Remove Selected", command=self._remove_domain_chip).pack(side=tk.RIGHT)

        self.lst_domains = tk.Listbox(frame_vis_domains, font=("Consolas", 9), height=3, selectmode=tk.EXTENDED)
        self.lst_domains.pack(fill=tk.BOTH, expand=True)

        # --- B. Bulk Mode Frames ---
        self.box_bulk = tk.Frame(self.box_cond_container, bg="#ffffff")

        tk.Label(self.box_bulk, text="Emails (one per line):", bg="#ffffff", font=("", 8, "bold")).pack(anchor=tk.W)
        self.txt_bulk_emails = tk.Text(self.box_bulk, font=("Consolas", 9), height=6)
        self.txt_bulk_emails.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        tk.Label(self.box_bulk, text="Domains (e.g. @omron.com, one per line):", bg="#ffffff", font=("", 8, "bold")).pack(anchor=tk.W)
        self.txt_bulk_domains = tk.Text(self.box_bulk, font=("Consolas", 9), height=3)
        self.txt_bulk_domains.pack(fill=tk.X, pady=(0, 4))

        self.box_visual.pack(fill=tk.BOTH, expand=True)

        # 4. Interactive Match Tester Strip
        tester_strip = tk.Frame(self.frame_rule, bg="#f8fafc", padx=6, pady=4, highlightbackground="#e2e8f0", highlightthickness=1)
        tester_strip.pack(fill=tk.X, pady=(0, 6))

        tk.Label(tester_strip, text="Test Match:", bg="#f8fafc", font=("", 8, "bold"), fg="#475569").pack(side=tk.LEFT, padx=(0, 4))
        self.ent_test_match = ttk.Entry(tester_strip, width=24)
        self.ent_test_match.pack(side=tk.LEFT, padx=2)
        ttk.Button(tester_strip, text="Check", command=self._test_rule_match).pack(side=tk.LEFT, padx=2)
        self.lbl_test_result = tk.Label(tester_strip, text="", bg="#f8fafc", font=("", 8, "bold"))
        self.lbl_test_result.pack(side=tk.LEFT, padx=6)

        # 5. Rule Action Footer
        btn_bar_rule = tk.Frame(self.frame_rule, bg="#ffffff")
        btn_bar_rule.pack(fill=tk.X, side=tk.BOTTOM)

        btn_save = ttk.Button(btn_bar_rule, text="Save Rule to YAML", style="Accent.TButton", command=self._save_rule_changes)
        btn_save.pack(side=tk.LEFT, padx=2)

        ttk.Button(btn_bar_rule, text="Duplicate Rule", command=self._duplicate_selected_rule).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar_rule, text="Delete Rule", command=self._delete_selected).pack(side=tk.RIGHT, padx=2)

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
        ttk.Button(self.btn_bar_folder, text="+ Subfolder (L+1)", command=self._add_subfolder).pack(side=tk.LEFT, padx=2)

        self.btn_promote_root = ttk.Button(self.btn_bar_folder, text="Promote to Root (L1)", command=self._promote_selected_folder_to_root)
        self.btn_move_up = ttk.Button(self.btn_bar_folder, text="Move Up 1 Level", command=self._move_selected_folder_up)

        ttk.Button(self.btn_bar_folder, text="Rename", command=self._rename_selected_folder).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.btn_bar_folder, text="Delete Folder", command=self._delete_selected_folder).pack(side=tk.RIGHT, padx=2)

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
        self.ent_group_name = ttk.Entry(row_name, width=28)
        self.ent_group_name.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Group Members
        tk.Label(self.frame_group, text="Member Emails (one per line):", bg="#ffffff", font=("", 8, "bold")).pack(anchor=tk.W)
        self.txt_group_emails = tk.Text(self.frame_group, font=("Consolas", 9), height=6)
        self.txt_group_emails.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        tk.Label(self.frame_group, text="Member Domains (e.g. @omron.com, one per line):", bg="#ffffff", font=("", 8, "bold")).pack(anchor=tk.W)
        self.txt_group_domains = tk.Text(self.frame_group, font=("Consolas", 9), height=3)
        self.txt_group_domains.pack(fill=tk.X, pady=(0, 8))

        # Action bar
        btn_bar_grp = tk.Frame(self.frame_group, bg="#ffffff")
        btn_bar_grp.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_bar_grp, text="Save Group to YAML", style="Accent.TButton", command=self._save_group_changes).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar_grp, text="Import CSV/Excel...", command=self._import_addresses_to_group).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar_grp, text="Delete Group", command=self._delete_selected_group).pack(side=tk.RIGHT, padx=2)

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
        ttk.Button(btn_bar_pool, text="Clear Entire Pool", command=self._clear_pool).pack(side=tk.RIGHT, padx=2)

    def _show_inspector(self, target_frame: tk.Frame):
        """Switch right pane to display the requested inspector."""
        for f in [self.frame_empty, self.frame_rule, self.frame_folder, self.frame_group, self.frame_pool]:
            f.pack_forget()
        target_frame.pack(fill=tk.BOTH, expand=True)

    # =================================================================
    # TREE REFRESH & DYNAMIC HIERARCHY POPULATION (ARBITRARY DEPTH)
    # =================================================================
    def refresh_all(self):
        """Rebuild the visual tree supporting arbitrary folder levels from YamlConfigManager."""
        self.tree.delete(*self.tree.get_children())
        self.folder_nodes_map.clear()
        self.rule_nodes_map.clear()

        q = self.search_query.lower()

        # -------------------------------------------------------------
        # Category 1: Hierarchical Folders & Rules (Arbitrary Depth)
        # -------------------------------------------------------------
        root_hier_id = "__HIERARCHY__"
        self.tree.insert("", tk.END, iid=root_hier_id, text="▼ HIERARCHICAL FOLDERS & RULES", values=("Root",), open=True)

        # Collect all folders
        all_folders = self.yaml_mgr.get_all_folders()

        # Build folder nodes for any depth (L1, L2, L3, L4, L5...)
        for fld in all_folders:
            parts = [p.strip() for p in re.split(r'[\\/]', fld) if p.strip()]
            parent_id = root_hier_id
            accum_path = ""
            for depth, part in enumerate(parts):
                accum_path = f"{accum_path}\\{part}" if accum_path else part
                fld_node_id = f"fld_{accum_path.lower().replace(' ', '_')}"
                if fld_node_id not in self.folder_nodes_map:
                    lbl = f"📁 [L{depth+1}] {part}"
                    self.tree.insert(parent_id, tk.END, iid=fld_node_id, text=lbl, values=(f"Level {depth+1}",), open=True)
                    self.folder_nodes_map[fld_node_id] = accum_path
                parent_id = fld_node_id

        # Insert rules under their respective folder nodes
        for rule in self.yaml_mgr.rules:
            # Check filter
            all_emails = self.yaml_mgr.get_all_emails_for_rule(rule)
            all_domains = self.yaml_mgr.get_all_domains_for_rule(rule)

            if q:
                match_name = q in rule.name.lower()
                match_folder = q in (rule.target_folder or "").lower()
                match_emails = any(q in e.lower() for e in all_emails)
                match_domains = any(q in d.lower() for d in all_domains)
                if not (match_name or match_folder or match_emails or match_domains):
                    continue

            # Determine parent folder node
            raw_folder = rule.target_folder or "_Unclassified"
            fld_node_id = f"fld_{raw_folder.lower().replace(' ', '_')}"

            # If folder node doesn't exist, create it under root
            if fld_node_id not in self.folder_nodes_map:
                parts = [p.strip() for p in re.split(r'[\\/]', raw_folder) if p.strip()]
                parent_id = root_hier_id
                accum = ""
                for d, pt in enumerate(parts):
                    accum = f"{accum}\\{pt}" if accum else pt
                    curr_fid = f"fld_{accum.lower().replace(' ', '_')}"
                    if curr_fid not in self.folder_nodes_map:
                        self.tree.insert(parent_id, tk.END, iid=curr_fid, text=f"📁 [L{d+1}] {pt}", values=(f"Level {d+1}",), open=True)
                        self.folder_nodes_map[curr_fid] = accum
                    parent_id = curr_fid
                fld_node_id = parent_id

            status_str = "[ON]" if rule.enabled else "[OFF]"
            total_senders = len(all_emails) + len(all_domains)
            rule_iid = f"rule_{rule.id}"
            self.tree.insert(
                fld_node_id, tk.END, iid=rule_iid,
                text=f"⚡ {status_str} {rule.name}",
                values=(f"{total_senders} senders",),
                open=False
            )
            self.rule_nodes_map[rule_iid] = rule.id

        # -------------------------------------------------------------
        # Category 2: Shared Address Groups
        # -------------------------------------------------------------
        root_grp_id = "__GROUPS__"
        self.tree.insert("", tk.END, iid=root_grp_id, text="▼ SHARED ADDRESS GROUPS", values=("Groups",), open=True)
        for g_id, grp in self.yaml_mgr.groups.items():
            if q and not (q in grp.name.lower() or any(q in e.lower() for e in grp.emails)):
                continue
            count = len(grp.emails) + len(grp.domains)
            grp_iid = f"grp_{g_id}"
            self.tree.insert(root_grp_id, tk.END, iid=grp_iid, text=f"👥 {grp.name}", values=(f"{count} members",))

        # -------------------------------------------------------------
        # Category 3: Unclassified Pool
        # -------------------------------------------------------------
        root_pool_id = "__POOL__"
        pool_count = len(self.yaml_mgr.unclassified_pool)
        self.tree.insert("", tk.END, iid=root_pool_id, text=f"▼ UNCLASSIFIED POOL ({pool_count})", values=("Pool",), open=True)
        for email in self.yaml_mgr.unclassified_pool:
            if q and q not in email.lower():
                continue
            pool_iid = f"pool_{email}"
            self.tree.insert(root_pool_id, tk.END, iid=pool_iid, text=f"📧 {email}", values=("Orphaned",))

    # =================================================================
    # TREE SELECTION & INSPECTOR SWITCHING
    # =================================================================
    def _on_tree_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            self._show_inspector(self.frame_empty)
            return

        iid = sel[0]

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
            return

        # Category headers
        self._show_inspector(self.frame_empty)

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
        # Breadcrumbs with Dynamic Level tags
        folder_path = rule.target_folder or "_Unclassified"
        parts = [p.strip() for p in re.split(r'[\\/]', folder_path) if p.strip()]
        breadcrumb_str = " > ".join(f"[L{i+1}] {p}" for i, p in enumerate(parts)) if parts else "(Root)"
        self.lbl_breadcrumb.config(text=f"📁 {breadcrumb_str} (Level {len(parts)})")

        # Core properties
        self.ent_rule_name.delete(0, tk.END)
        self.ent_rule_name.insert(0, rule.name)
        self.var_rule_enabled.set(rule.enabled)

        # Quota Meter
        all_emails = self.yaml_mgr.get_all_emails_for_rule(rule)
        all_domains = self.yaml_mgr.get_all_domains_for_rule(rule)
        total_recipients = len(all_emails) + len(all_domains)
        threshold = int(self.yaml_mgr.settings.get("auto_split_threshold", 40))

        if total_recipients <= threshold:
            self.lbl_quota.config(
                text=f"Outlook Quota: {total_recipients} / {threshold} senders (1 native sub-rule) - OK",
                fg="#16a34a"
            )
        else:
            num_parts = (total_recipients + threshold - 1) // threshold
            self.lbl_quota.config(
                text=f"Outlook Quota: {total_recipients} senders exceeds {threshold} limit -> Auto-splits into {num_parts} sub-rules",
                fg="#ea580c"
            )

        # Visual Lists
        self.lst_emails.delete(0, tk.END)
        for e in sorted(rule.emails):
            self.lst_emails.insert(tk.END, e)

        self.lst_domains.delete(0, tk.END)
        for d in sorted(rule.domains):
            self.lst_domains.insert(tk.END, d)

        # Bulk Texts
        self.txt_bulk_emails.delete("1.0", tk.END)
        self.txt_bulk_emails.insert(tk.END, "\n".join(sorted(rule.emails)))

        self.txt_bulk_domains.delete("1.0", tk.END)
        self.txt_bulk_domains.insert(tk.END, "\n".join(sorted(rule.domains)))

        self.lbl_test_result.config(text="")
        self.ent_test_match.delete(0, tk.END)

    def _populate_folder_inspector(self, folder_path: str):
        self.lbl_folder_title.config(text=f"Folder: {folder_path}")
        parts = [p.strip() for p in re.split(r'[\\/]', folder_path) if p.strip()]
        depth = len(parts)

        parent_text = parts[-2] if depth > 1 else "(Root)"
        crumb_text = " > ".join(f"[L{i+1}] {p}" for i, p in enumerate(parts))
        self.lbl_folder_level.config(text=f"Level: Level {depth}  |  Parent: {parent_text}\nPath: {crumb_text}")

        # Rules in folder
        folder_rules = [r for r in self.yaml_mgr.rules if r.target_folder == folder_path]
        total_senders = sum(len(self.yaml_mgr.get_all_emails_for_rule(r)) + len(self.yaml_mgr.get_all_domains_for_rule(r)) for r in folder_rules)

        self.lbl_folder_stats.config(text=f"Rules in this Folder: {len(folder_rules)}  |  Total Monitored Senders: {total_senders}")

        self.tree_folder_rules.delete(*self.tree_folder_rules.get_children())
        for r in folder_rules:
            st = "Active" if r.enabled else "Disabled"
            cnt = len(self.yaml_mgr.get_all_emails_for_rule(r)) + len(self.yaml_mgr.get_all_domains_for_rule(r))
            self.tree_folder_rules.insert("", tk.END, iid=f"frule_{r.id}", text=r.name, values=(st, f"{cnt} senders"))

        # Configure Level shifting buttons (Promote / Move Up)
        if depth > 1:
            self.btn_promote_root.pack(side=tk.LEFT, padx=2)
            self.btn_move_up.config(text=f"Move Up to L{depth-1}")
            self.btn_move_up.pack(side=tk.LEFT, padx=2)
        else:
            self.btn_promote_root.pack_forget()
            self.btn_move_up.pack_forget()

    def _populate_group_inspector(self, group: AddressGroup):
        self.lbl_group_title.config(text=f"Shared Address Group: {group.name}")
        self.ent_group_name.delete(0, tk.END)
        self.ent_group_name.insert(0, group.name)

        self.txt_group_emails.delete("1.0", tk.END)
        self.txt_group_emails.insert(tk.END, "\n".join(sorted(group.emails)))

        self.txt_group_domains.delete("1.0", tk.END)
        self.txt_group_domains.insert(tk.END, "\n".join(sorted(group.domains)))

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

    def _show_toast(self, message: str):
        """Display non-blocking status notification in top bar."""
        self.lbl_toast.config(text=message, fg="#0284c7")
        self.after(5000, lambda: self.lbl_toast.config(text="Tip: Folders have flexible levels. Drag to Root for Level 1, or drop into any folder for Level 2, 3, 4...", fg="#64748b"))

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
                    menu.add_command(label="Promote to Root (Level 1)", command=self._promote_selected_folder_to_root)
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

        new_id = f"rule_{len(self.yaml_mgr.rules) + 1}"
        new_rule = RuleConfig(
            id=new_id,
            name=f"New Rule {len(self.yaml_mgr.rules) + 1}",
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

    def _save_rule_changes(self):
        if not self.selected_rule:
            return

        name = self.ent_rule_name.get().strip()
        if not name:
            messagebox.showwarning("Notice", "Rule name cannot be empty.")
            return

        self.selected_rule.name = name
        self.selected_rule.enabled = self.var_rule_enabled.get()

        if self.condition_mode == "visual":
            emails = [self.lst_emails.get(i).strip().lower() for i in range(self.lst_emails.size())]
            domains = [self.lst_domains.get(i).strip().lower() for i in range(self.lst_domains.size())]
        else:
            emails = [l.strip().lower() for l in self.txt_bulk_emails.get("1.0", tk.END).split("\n") if l.strip()]
            domains = [l.strip().lower() for l in self.txt_bulk_domains.get("1.0", tk.END).split("\n") if l.strip()]

        self.selected_rule.emails = sorted(list(set(emails)))
        self.selected_rule.domains = sorted(list(set(domains)))

        self.yaml_mgr.save()
        self._show_toast(f"Saved rule '{name}' to rules.yaml")
        self.refresh_all()

        rule_iid = f"rule_{self.selected_rule.id}"
        if self.tree.exists(rule_iid):
            self.tree.selection_set(rule_iid)
            self._on_tree_select()

    def _toggle_rule_enabled(self):
        if not self.selected_rule:
            return
        self.selected_rule.enabled = not self.selected_rule.enabled
        self.yaml_mgr.save()
        st = "Enabled" if self.selected_rule.enabled else "Disabled"
        self._show_toast(f"Rule '{self.selected_rule.name}' {st}")
        self.refresh_all()

    def _duplicate_selected_rule(self):
        if not self.selected_rule:
            messagebox.showwarning("Notice", "Select a rule to duplicate.")
            return
        dup = self.yaml_mgr.duplicate_rule(self.selected_rule.id)
        if dup:
            self._show_toast(f"Duplicated: '{dup.name}'")
            self.refresh_all()
            dup_iid = f"rule_{dup.id}"
            if self.tree.exists(dup_iid):
                self.tree.selection_set(dup_iid)
                self._on_tree_select()

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
                self.refresh_all()
                self._show_inspector(self.frame_empty)
        elif self.selected_folder_path:
            self._delete_selected_folder()

    # -----------------------------------------------------------------
    # CONDITION EDITORS & CHIPS
    # -----------------------------------------------------------------
    def _set_condition_mode(self, mode: str):
        self.condition_mode = mode
        if mode == "visual":
            self.btn_mode_visual.config(bg="#0284c7", fg="#ffffff")
            self.btn_mode_bulk.config(bg="#e2e8f0", fg="#475569")
            # Sync bulk text into visual lists
            emails = [l.strip().lower() for l in self.txt_bulk_emails.get("1.0", tk.END).split("\n") if l.strip()]
            domains = [l.strip().lower() for l in self.txt_bulk_domains.get("1.0", tk.END).split("\n") if l.strip()]
            self.lst_emails.delete(0, tk.END)
            for e in sorted(list(set(emails))):
                self.lst_emails.insert(tk.END, e)
            self.lst_domains.delete(0, tk.END)
            for d in sorted(list(set(domains))):
                self.lst_domains.insert(tk.END, d)
            self.box_bulk.pack_forget()
            self.box_visual.pack(fill=tk.BOTH, expand=True)
        else:
            self.btn_mode_visual.config(bg="#e2e8f0", fg="#475569")
            self.btn_mode_bulk.config(bg="#0284c7", fg="#ffffff")
            # Sync visual lists into bulk text
            emails = [self.lst_emails.get(i) for i in range(self.lst_emails.size())]
            domains = [self.lst_domains.get(i) for i in range(self.lst_domains.size())]
            self.txt_bulk_emails.delete("1.0", tk.END)
            self.txt_bulk_emails.insert(tk.END, "\n".join(emails))
            self.txt_bulk_domains.delete("1.0", tk.END)
            self.txt_bulk_domains.insert(tk.END, "\n".join(domains))
            self.box_visual.pack_forget()
            self.box_bulk.pack(fill=tk.BOTH, expand=True)

    def _add_email_chip(self):
        val = self.ent_add_email.get().strip().lower()
        if not val or "@" not in val:
            return
        existing = [self.lst_emails.get(i) for i in range(self.lst_emails.size())]
        if val not in existing:
            self.lst_emails.insert(tk.END, val)
        self.ent_add_email.delete(0, tk.END)

    def _remove_email_chip(self):
        sel = list(self.lst_emails.curselection())
        for idx in reversed(sel):
            self.lst_emails.delete(idx)

    def _add_domain_chip(self):
        val = self.ent_add_domain.get().strip().lower()
        if not val:
            return
        if not val.startswith("@"):
            val = "@" + val
        existing = [self.lst_domains.get(i) for i in range(self.lst_domains.size())]
        if val not in existing:
            self.lst_domains.insert(tk.END, val)
        self.ent_add_domain.delete(0, tk.END)

    def _remove_domain_chip(self):
        sel = list(self.lst_domains.curselection())
        for idx in reversed(sel):
            self.lst_domains.delete(idx)

    def _test_rule_match(self):
        query = self.ent_test_match.get().strip().lower()
        if not query or not self.selected_rule:
            return
        all_emails = self.yaml_mgr.get_all_emails_for_rule(self.selected_rule)
        all_domains = self.yaml_mgr.get_all_domains_for_rule(self.selected_rule)

        if query in all_emails:
            self.lbl_test_result.config(text="MATCH! (Exact Email)", fg="#16a34a")
        elif any(query.endswith(d) or d.lstrip("@") in query for d in all_domains):
            self.lbl_test_result.config(text="MATCH! (Domain Rule)", fg="#16a34a")
        else:
            self.lbl_test_result.config(text="NO MATCH", fg="#dc2626")

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
        g_id = f"group_{len(self.yaml_mgr.groups) + 1}"
        new_g = AddressGroup(id=g_id, name=g_name)
        self.yaml_mgr.groups[g_id] = new_g
        self.yaml_mgr.save()
        self._show_toast(f"Created group '{g_name}'")
        self.refresh_all()
        grp_iid = f"grp_{g_id}"
        if self.tree.exists(grp_iid):
            self.tree.selection_set(grp_iid)
            self._on_tree_select()

    def _save_group_changes(self):
        if not self.selected_group:
            return
        name = self.ent_group_name.get().strip()
        if not name:
            messagebox.showwarning("Notice", "Group name cannot be empty.")
            return

        emails = [l.strip().lower() for l in self.txt_group_emails.get("1.0", tk.END).split("\n") if l.strip()]
        domains = [l.strip().lower() for l in self.txt_group_domains.get("1.0", tk.END).split("\n") if l.strip()]

        self.selected_group.name = name
        self.selected_group.emails = sorted(list(set(emails)))
        self.selected_group.domains = sorted(list(set(domains)))
        self.yaml_mgr.save()
        self._show_toast(f"Saved group '{name}'")
        self.refresh_all()

    def _rename_selected_group(self):
        if not self.selected_group:
            return
        new_name = simpledialog.askstring("Rename Group", "Enter new name:", initialvalue=self.selected_group.name)
        if new_name and new_name != self.selected_group.name:
            self.selected_group.name = new_name
            self.yaml_mgr.save()
            self._show_toast(f"Renamed group to '{new_name}'")
            self.refresh_all()

    def _delete_selected_group(self):
        if not self.selected_group:
            return
        confirm = messagebox.askyesno("Confirm Delete", f"Delete group '{self.selected_group.name}'?", icon=messagebox.WARNING)
        if confirm:
            g_id = self.selected_group.id
            if g_id in self.yaml_mgr.groups:
                del self.yaml_mgr.groups[g_id]
                self.yaml_mgr.save()
                self._show_toast("Deleted group")
                self.selected_group = None
                self.refresh_all()
                self._show_inspector(self.frame_empty)

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
        if self.condition_mode == "visual":
            existing = [self.lst_emails.get(i) for i in range(self.lst_emails.size())]
            for e in emails:
                if e not in existing:
                    self.lst_emails.insert(tk.END, e)
        else:
            current = [l.strip().lower() for l in self.txt_bulk_emails.get("1.0", tk.END).split("\n") if l.strip()]
            combined = sorted(list(set(current + emails)))
            self.txt_bulk_emails.delete("1.0", tk.END)
            self.txt_bulk_emails.insert(tk.END, "\n".join(combined))
        messagebox.showinfo("Imported", f"Successfully imported {len(emails)} email addresses.")

    def _import_addresses_to_group(self):
        emails = self._read_addresses_from_file()
        if not emails:
            return
        current = [l.strip().lower() for l in self.txt_group_emails.get("1.0", tk.END).split("\n") if l.strip()]
        combined = sorted(list(set(current + emails)))
        self.txt_group_emails.delete("1.0", tk.END)
        self.txt_group_emails.insert(tk.END, "\n".join(combined))
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
