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
        """Execute selected resolutions respecting IGNORE, IMPORT, OVERWRITE, and MERGE."""
        if not self.conflicts:
            self.destroy()
            return

        import_results = []
        overwrite_count = 0
        merge_count = 0
        ignore_count = 0

        for c in self.conflicts:
            action = c.suggested_action
            if action == "IGNORE":
                ignore_count += 1
            elif action == "IMPORT":
                res = self.detector.resolve_import_to_yaml(c, save=False)
                if res:
                    import_results.append(res)
            elif action == "OVERWRITE":
                overwrite_count += 1
            elif action == "MERGE":
                merge_count += 1

        import_count = len(import_results)
        if import_count > 0:
            self.detector.yaml_mgr.save()

        needs_push = (import_count + overwrite_count + merge_count) > 0
        if not needs_push:
            messagebox.showinfo(
                "Conflict Resolution Complete",
                f"Processed {len(self.conflicts)} conflicts.\n"
                f"• Imported to YAML: 0\n"
                f"• Overwritten in Outlook: 0\n"
                f"• Merged via Outlook sync: 0\n"
                f"• Ignored / Skipped: {ignore_count}\n\n"
                f"Outlook Sync: Skipped (all conflicts ignored)"
            )
            self.destroy()
            return

        remove_legacy = False
        remove_legacy_names = None
        if import_results:
            problematic = [r for r in import_results if r.has_warnings]
            clean_imports = [r for r in import_results if not r.has_warnings]

            if problematic and not clean_imports:
                prob_lines = self._format_import_warning_lines(problematic)
                messagebox.showwarning(
                    "Imported Rules Require Review",
                    "The following imported rules have unsupported conditions or unresolved recipients.\n"
                    "Rules with unsupported conditions were imported as DISABLED and must be reviewed before enabling.\n\n"
                    f"{prob_lines}\n\n"
                    "Their original Outlook rules were kept (not deleted) so no conditions are lost."
                )
            elif problematic:
                prob_lines = self._format_import_warning_lines(problematic)
                clean_lines = "\n".join(f"• {r.rule_name}" for r in clean_imports)
                remove_legacy = bool(messagebox.askyesno(
                    "Remove Original Outlook Rules?",
                    "Warning: Some imported rules have unsupported conditions or unresolved recipients "
                    "(rules with unsupported conditions were imported as DISABLED and must be reviewed before enabling; "
                    "their original Outlook rules will NOT be deleted):\n\n"
                    f"{prob_lines}\n\n"
                    "Remove the original Outlook rules for the clean imports listed below?\n"
                    f"{clean_lines}",
                    icon=messagebox.WARNING,
                    default=messagebox.NO,
                ))
                if remove_legacy:
                    remove_legacy_names = [r.rule_name for r in clean_imports]
            else:
                listed = "\n".join(f"• {r.rule_name}" for r in clean_imports)
                remove_legacy = bool(messagebox.askyesno(
                    "Remove Original Outlook Rules?",
                    "Remove the original Outlook rules for the clean imports listed below?\n\n"
                    f"{listed}",
                    icon=messagebox.QUESTION,
                ))
                if remove_legacy:
                    remove_legacy_names = [r.rule_name for r in clean_imports]

        success, msg = self.sync_engine.push_to_outlook(
            remove_legacy=remove_legacy,
            remove_legacy_names=remove_legacy_names,
        )
        sim_prefix = "[SIMULATION] No changes were made to Outlook.\n\n" if self.sync_engine.outlook.is_simulated() else ""
        messagebox.showinfo(
            "Conflict Resolution Complete",
            f"{sim_prefix}"
            f"Resolved {len(self.conflicts)} conflicts.\n"
            f"• Imported to YAML: {import_count}\n"
            f"• Overwritten in Outlook: {overwrite_count}\n"
            f"• Merged via Outlook sync: {merge_count}\n"
            f"• Ignored / Skipped: {ignore_count}\n\n"
            f"Outlook Sync: {msg}"
        )
        self.destroy()

    @staticmethod
    def _format_import_warning_lines(problematic_results) -> str:
        lines = []
        for r in problematic_results:
            reasons = []
            if r.has_unsupported_conditions:
                reasons.append("unsupported conditions - imported DISABLED, review before enabling")
            if r.unresolved_recipients:
                reasons.append(f"unresolved recipients: {', '.join(r.unresolved_recipients)}")
            lines.append(f"• {r.rule_name} ({'; '.join(reasons)})")
        return "\n".join(lines)
