"""Conflict Inspector and Resolution Dialog."""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List

from core.conflict_detector import ConflictDetector, RuleConflict
from core.yaml_manager import YamlConfigManager
from core.sync_engine import SyncEngine


class ConflictDialog(tk.Toplevel):
    """Modal dialog allowing inspection and resolution of rule conflicts between YAML and Outlook."""

    def __init__(self, parent, detector: ConflictDetector, sync_engine: SyncEngine):
        super().__init__(parent)
        self.detector = detector
        self.sync_engine = sync_engine
        self.conflicts: List[RuleConflict] = []

        self.title("Rule Conflict Inspector & Resolver")
        self.geometry("780x520")
        self.minsize(700, 450)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self.run_detection()

    def _build_ui(self):
        container = ttk.Frame(self, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        # Header
        lbl_title = ttk.Label(container, text="Outlook & YAML Rule Conflict Inspector", font=("", 12, "bold"))
        lbl_title.pack(anchor=tk.W, pady=(0, 4))

        lbl_desc = ttk.Label(
            container,
            text="The following discrepancies were detected between rules.yaml and native Outlook rules.\n"
                 "Select an action for each conflict, or use 'Auto-Resolve' to apply YAML as master.",
            wraplength=740
        )
        lbl_desc.pack(anchor=tk.W, pady=(0, 10))

        # Conflict Table
        cols = ("Type", "Rule Name", "Issue Description", "Resolution")
        self.tree = ttk.Treeview(container, columns=cols, show="headings", selectmode="browse", height=10)
        self.tree.heading("Type", text="Conflict Type")
        self.tree.heading("Rule Name", text="Rule Name / Sender")
        self.tree.heading("Issue Description", text="Details")
        self.tree.heading("Resolution", text="Action")

        self.tree.column("Type", width=140)
        self.tree.column("Rule Name", width=180)
        self.tree.column("Issue Description", width=280)
        self.tree.column("Resolution", width=120)

        scroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=4)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_select_conflict)

        # Bottom Detail & Action Box
        detail_box = ttk.LabelFrame(container, text="Conflict Action", padding=10)
        detail_box.pack(fill=tk.X, pady=8)

        self.lbl_selected_desc = ttk.Label(detail_box, text="Select a conflict above to review or change resolution.", wraplength=720)
        self.lbl_selected_desc.pack(anchor=tk.W, pady=(0, 6))

        btn_row = ttk.Frame(detail_box)
        btn_row.pack(fill=tk.X)

        self.btn_set_overwrite = ttk.Button(
            btn_row,
            text="Set Action: Overwrite Outlook",
            command=lambda: self._set_action("OVERWRITE")
        )
        self.btn_set_overwrite.pack(side=tk.LEFT, padx=2)

        self.btn_set_import = ttk.Button(
            btn_row,
            text="Set Action: Import to YAML",
            command=lambda: self._set_action("IMPORT")
        )
        self.btn_set_import.pack(side=tk.LEFT, padx=2)

        self.btn_set_ignore = ttk.Button(
            btn_row,
            text="Set Action: Ignore / Skip",
            command=lambda: self._set_action("IGNORE")
        )
        self.btn_set_ignore.pack(side=tk.LEFT, padx=2)

        # Dialog Footer Buttons
        footer = ttk.Frame(container, padding=(0, 6))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        btn_cancel = ttk.Button(footer, text="Cancel", command=self.destroy)
        btn_cancel.pack(side=tk.RIGHT, padx=4)

        btn_apply = ttk.Button(
            footer,
            text="Execute Resolutions & Sync",
            command=self._execute_resolutions
        )
        btn_apply.pack(side=tk.RIGHT, padx=4)

    def run_detection(self):
        """Run conflict scan and display results in Treeview."""
        self.tree.delete(*self.tree.get_children())
        self.conflicts = self.detector.detect_conflicts()

        if not self.conflicts:
            self.lbl_selected_desc.config(text="✓ Great news! No rule conflicts detected between YAML and Outlook.")
            return

        for idx, c in enumerate(self.conflicts):
            item_id = f"conflict_{idx}"
            self.tree.insert(
                "",
                tk.END,
                iid=item_id,
                values=(c.conflict_type, c.rule_name, c.description, c.suggested_action)
            )

    def _on_select_conflict(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0].split("_")[1])
        c = self.conflicts[idx]
        self.lbl_selected_desc.config(text=f"Selected: {c.rule_name}\n{c.description}")

    def _set_action(self, action_name: str):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0].split("_")[1])
        self.conflicts[idx].suggested_action = action_name
        c = self.conflicts[idx]
        self.tree.item(sel[0], values=(c.conflict_type, c.rule_name, c.description, action_name))

    def _execute_resolutions(self):
        """Execute selected resolutions."""
        if not self.conflicts:
            self.destroy()
            return

        import_count = 0
        overwrite_count = 0

        for c in self.conflicts:
            if c.suggested_action == "IMPORT":
                self.detector.resolve_import_to_yaml(c)
                import_count += 1
            elif c.suggested_action == "OVERWRITE":
                overwrite_count += 1

        # Push to Outlook
        success, msg = self.sync_engine.push_to_outlook()
        messagebox.showinfo(
            "Conflict Resolution Complete",
            f"Resolved {len(self.conflicts)} conflicts.\n"
            f"• Imported to YAML: {import_count}\n"
            f"• Overwritten in Outlook: {overwrite_count}\n\n"
            f"Outlook Sync: {msg}"
        )
        self.destroy()
