"""Dry-Run Simulation View."""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List

from core.yaml_manager import YamlConfigManager
from core.outlook_client import BaseOutlookClient
from core.sync_engine import SyncEngine


class DryRunView(ttk.Frame):
    """Simulates rule matching against current Inbox without modifying Outlook."""

    def __init__(self, parent, yaml_mgr: YamlConfigManager, outlook: BaseOutlookClient, sync_engine: SyncEngine):
        super().__init__(parent)
        self.yaml_mgr = yaml_mgr
        self.outlook = outlook
        self.sync_engine = sync_engine

        self._build_ui()

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=(8, 8))
        toolbar.pack(fill=tk.X)

        btn_run = ttk.Button(toolbar, text="Run Simulation", command=self.run_simulation)
        btn_run.pack(side=tk.LEFT, padx=4)

        self.lbl_stats = ttk.Label(toolbar, text="Click 'Run Simulation' to test current rules against Inbox emails.")
        self.lbl_stats.pack(side=tk.LEFT, padx=12)

        # Results table
        frame_table = ttk.Frame(self, padding=8)
        frame_table.pack(fill=tk.BOTH, expand=True)

        cols = ("Sender", "Subject", "Rule", "Folder", "Reason")
        self.tree = ttk.Treeview(frame_table, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("Sender", text="From (Resolved SMTP)")
        self.tree.heading("Subject", text="Subject")
        self.tree.heading("Rule", text="Target Rule")
        self.tree.heading("Folder", text="Target Folder")
        self.tree.heading("Reason", text="Matching Specificity")

        self.tree.column("Sender", width=140)
        self.tree.column("Subject", width=220)
        self.tree.column("Rule", width=110)
        self.tree.column("Folder", width=110)
        self.tree.column("Reason", width=160)

        scroll_y = ttk.Scrollbar(frame_table, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

    def run_simulation(self):
        """Execute simulation against Inbox."""
        self.tree.delete(*self.tree.get_children())
        messages = self.outlook.get_inbox_messages(limit=100)

        total = len(messages)
        matched_count = 0
        untracked_count = 0

        for msg in messages:
            rule, reason = self.sync_engine.match_message(msg.sender_email, msg.subject)
            if rule:
                matched_count += 1
                rule_name = rule.name
                folder = rule.target_folder or "(Root)"
            else:
                untracked_count += 1
                rule_name = "(None)"
                folder = "Inbox (Untouched)"

            self.tree.insert(
                "",
                tk.END,
                values=(msg.sender_email, msg.subject, rule_name, folder, reason)
            )

        self.lbl_stats.config(
            text=f"Total: {total} emails | Matched: {matched_count} | Untracked (Remain in Inbox): {untracked_count}"
        )
