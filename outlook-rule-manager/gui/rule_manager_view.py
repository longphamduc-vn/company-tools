"""Rule and Address Group Management View."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from typing import Optional

from core.models import RuleConfig, AddressGroup
from core.yaml_manager import YamlConfigManager
from core.sync_engine import SyncEngine


class RuleManagerView(ttk.Frame):
    """Editor for Outlook Rules, Address Groups, and Unclassified Pool."""

    def __init__(self, parent, yaml_mgr: YamlConfigManager, sync_engine: SyncEngine):
        super().__init__(parent)
        self.yaml_mgr = yaml_mgr
        self.sync_engine = sync_engine
        self.selected_rule: Optional[RuleConfig] = None
        self.selected_group: Optional[AddressGroup] = None

        self._build_ui()
        self.refresh_all()

    def _build_ui(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # -------------------------------------------------------------
        # LEFT PANE: List of Rules, Groups, and Unclassified Pool
        # -------------------------------------------------------------
        frame_left = ttk.Frame(paned, padding=4)
        paned.add(frame_left, weight=1)

        notebook_left = ttk.Notebook(frame_left)
        notebook_left.pack(fill=tk.BOTH, expand=True)

        # Sub-tab: Rules
        tab_rules = ttk.Frame(notebook_left, padding=4)
        notebook_left.add(tab_rules, text="Rules")

        self.tree_rules = ttk.Treeview(tab_rules, columns=("Folder",), show="tree headings", selectmode="browse")
        self.tree_rules.heading("#0", text="Rule Name")
        self.tree_rules.heading("Folder", text="Target Folder")
        self.tree_rules.column("#0", width=140)
        self.tree_rules.column("Folder", width=120)

        rules_scroll = ttk.Scrollbar(tab_rules, orient=tk.VERTICAL, command=self.tree_rules.yview)
        self.tree_rules.configure(yscrollcommand=rules_scroll.set)
        self.tree_rules.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        rules_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree_rules.bind("<<TreeviewSelect>>", self._on_rule_select)

        btn_bar_rules = ttk.Frame(tab_rules, padding=4)
        btn_bar_rules.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_bar_rules, text="+ New Rule", command=self._add_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar_rules, text="Delete", command=self._delete_rule).pack(side=tk.LEFT, padx=2)

        # Sub-tab: Groups
        tab_groups = ttk.Frame(notebook_left, padding=4)
        notebook_left.add(tab_groups, text="Address Groups")

        self.tree_groups = ttk.Treeview(tab_groups, columns=("Count",), show="tree headings", selectmode="browse")
        self.tree_groups.heading("#0", text="Group Name")
        self.tree_groups.heading("Count", text="Members")
        self.tree_groups.column("#0", width=150)
        self.tree_groups.column("Count", width=60)

        self.tree_groups.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.tree_groups.bind("<<TreeviewSelect>>", self._on_group_select)

        btn_bar_groups = ttk.Frame(tab_groups, padding=4)
        btn_bar_groups.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_bar_groups, text="+ New Group", command=self._add_group).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar_groups, text="Delete", command=self._delete_group).pack(side=tk.LEFT, padx=2)

        # Sub-tab: Unclassified Pool
        tab_pool = ttk.Frame(notebook_left, padding=4)
        notebook_left.add(tab_pool, text="Unclassified Pool")

        ttk.Label(
            tab_pool,
            text="Addresses orphaned from deleted rules:\n(Auto-routed to [Unclassified] folder in Outlook)",
            font=("", 8, "italic")
        ).pack(pady=4)

        self.lst_pool = tk.Listbox(tab_pool, font=("Consolas", 9))
        self.lst_pool.pack(fill=tk.BOTH, expand=True, pady=4)

        btn_pool_bar = ttk.Frame(tab_pool)
        btn_pool_bar.pack(fill=tk.X)
        ttk.Button(btn_pool_bar, text="Clear Pool", command=self._clear_pool).pack(side=tk.LEFT, padx=2)

        # -------------------------------------------------------------
        # RIGHT PANE: Details Editor
        # -------------------------------------------------------------
        self.frame_right = ttk.LabelFrame(paned, text="Details Editor", padding=8)
        paned.add(self.frame_right, weight=2)

        # Form fields
        grid = ttk.Frame(self.frame_right)
        grid.pack(fill=tk.X, pady=4)

        ttk.Label(grid, text="Name / Label:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.ent_name = ttk.Entry(grid, width=32)
        self.ent_name.grid(row=0, column=1, sticky=tk.EW, pady=3, padx=4)

        ttk.Label(grid, text="Target Folder:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.ent_folder = ttk.Entry(grid, width=32)
        self.ent_folder.grid(row=1, column=1, sticky=tk.EW, pady=3, padx=4)

        self.var_enabled = tk.BooleanVar(value=True)
        self.chk_enabled = ttk.Checkbutton(grid, text="Rule Active", variable=self.var_enabled)
        self.chk_enabled.grid(row=2, column=1, sticky=tk.W, pady=3, padx=4)

        ttk.Label(self.frame_right, text="Emails (one per line):").pack(anchor=tk.W, pady=(6, 2))
        self.txt_emails = tk.Text(self.frame_right, height=8, font=("Consolas", 9))
        self.txt_emails.pack(fill=tk.BOTH, expand=True, pady=2)

        ttk.Label(self.frame_right, text="Domains (e.g. @company.com, one per line):").pack(anchor=tk.W, pady=(6, 2))
        self.txt_domains = tk.Text(self.frame_right, height=4, font=("Consolas", 9))
        self.txt_domains.pack(fill=tk.X, pady=2)

        # Bottom action bar
        btn_bar = ttk.Frame(self.frame_right, padding=6)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        btn_save = ttk.Button(btn_bar, text="Save to YAML", command=self._save_changes)
        btn_save.pack(side=tk.LEFT, padx=4)

        btn_import = ttk.Button(btn_bar, text="Import from Excel/CSV", command=self._import_addresses)
        btn_import.pack(side=tk.LEFT, padx=4)

    def refresh_all(self):
        """Reload data from YamlConfigManager into UI."""
        self.tree_rules.delete(*self.tree_rules.get_children())
        for r in self.yaml_mgr.rules:
            prefix = "[ON]" if r.enabled else "[OFF]"
            self.tree_rules.insert("", tk.END, iid=r.id, text=f"{prefix} {r.name}", values=(r.target_folder,))

        self.tree_groups.delete(*self.tree_groups.get_children())
        for g_id, g in self.yaml_mgr.groups.items():
            count = len(g.emails) + len(g.domains)
            self.tree_groups.insert("", tk.END, iid=g_id, text=g.name, values=(f"{count} items",))

        self.lst_pool.delete(0, tk.END)
        for email in self.yaml_mgr.unclassified_pool:
            self.lst_pool.insert(tk.END, email)

    def _on_rule_select(self, event):
        sel = self.tree_rules.selection()
        if not sel:
            return
        rule_id = sel[0]
        self.selected_rule = next((r for r in self.yaml_mgr.rules if r.id == rule_id), None)
        self.selected_group = None
        if not self.selected_rule:
            return

        self.frame_right.config(text=f"Editing Rule: {self.selected_rule.name}")
        self.ent_name.delete(0, tk.END)
        self.ent_name.insert(0, self.selected_rule.name)

        self.ent_folder.delete(0, tk.END)
        self.ent_folder.insert(0, self.selected_rule.target_folder)

        self.var_enabled.set(self.selected_rule.enabled)

        all_emails = self.yaml_mgr.get_all_emails_for_rule(self.selected_rule)
        self.txt_emails.delete("1.0", tk.END)
        self.txt_emails.insert(tk.END, "\n".join(all_emails))

        all_domains = self.yaml_mgr.get_all_domains_for_rule(self.selected_rule)
        self.txt_domains.delete("1.0", tk.END)
        self.txt_domains.insert(tk.END, "\n".join(all_domains))

    def _on_group_select(self, event):
        sel = self.tree_groups.selection()
        if not sel:
            return
        g_id = sel[0]
        self.selected_group = self.yaml_mgr.groups.get(g_id)
        self.selected_rule = None
        if not self.selected_group:
            return

        self.frame_right.config(text=f"Editing Group: {self.selected_group.name}")
        self.ent_name.delete(0, tk.END)
        self.ent_name.insert(0, self.selected_group.name)

        self.ent_folder.delete(0, tk.END)
        self.ent_folder.insert(0, "(Managed at Rule level)")

        self.txt_emails.delete("1.0", tk.END)
        self.txt_emails.insert(tk.END, "\n".join(self.selected_group.emails))

        self.txt_domains.delete("1.0", tk.END)
        self.txt_domains.insert(tk.END, "\n".join(self.selected_group.domains))

    def _save_changes(self):
        name = self.ent_name.get().strip()
        folder = self.ent_folder.get().strip()
        emails = [line.strip().lower() for line in self.txt_emails.get("1.0", tk.END).split("\n") if line.strip()]
        domains = [line.strip().lower() for line in self.txt_domains.get("1.0", tk.END).split("\n") if line.strip()]

        if self.selected_rule:
            self.selected_rule.name = name
            self.selected_rule.target_folder = folder
            self.selected_rule.enabled = self.var_enabled.get()
            self.selected_rule.emails = emails
            self.selected_rule.domains = domains
            self.yaml_mgr.save()
            messagebox.showinfo("Saved", f"Rule '{name}' saved to rules.yaml.\nRemember to click 'Sync to Outlook' when ready.")
        elif self.selected_group:
            self.selected_group.name = name
            self.selected_group.emails = emails
            self.selected_group.domains = domains
            self.yaml_mgr.save()
            messagebox.showinfo("Saved", f"Group '{name}' saved to rules.yaml.")
        else:
            messagebox.showwarning("Notice", "Select a Rule or Group to save.")
            return

        self.refresh_all()

    def _add_rule(self):
        new_id = f"rule_{len(self.yaml_mgr.rules) + 1}"
        new_rule = RuleConfig(
            id=new_id,
            name=f"New Rule {len(self.yaml_mgr.rules) + 1}",
            enabled=True,
            target_store="active_archive",
            target_folder="New_Folder"
        )
        self.yaml_mgr.rules.append(new_rule)
        self.yaml_mgr.save()
        self.refresh_all()
        self.tree_rules.selection_set(new_id)

    def _delete_rule(self):
        sel = self.tree_rules.selection()
        if not sel:
            return
        rule_id = sel[0]
        rule = next((r for r in self.yaml_mgr.rules if r.id == rule_id), None)
        if not rule:
            return

        if rule.id == "rule_unclassified":
            messagebox.showwarning("Notice", "Cannot delete the default [Unclassified] rule.")
            return

        confirm = messagebox.askyesno(
            "Confirm Delete Rule",
            f"Are you sure you want to delete rule '{rule.name}'?\n\n"
            f"All addresses will be safely moved to the 'Unclassified Pool' "
            f"so subsequent incoming emails are routed to '{self.yaml_mgr.settings.get('unclassified_folder', '_Unclassified')}'.",
            icon=messagebox.WARNING
        )
        if confirm:
            self.yaml_mgr.remove_rule_and_repool(rule_id)
            self.refresh_all()
            messagebox.showinfo("Deleted", f"Rule '{rule.name}' removed. Addresses repooled.")

    def _add_group(self):
        g_id = f"group_{len(self.yaml_mgr.groups) + 1}"
        new_g = AddressGroup(id=g_id, name=f"New Group {len(self.yaml_mgr.groups) + 1}")
        self.yaml_mgr.groups[g_id] = new_g
        self.yaml_mgr.save()
        self.refresh_all()
        self.tree_groups.selection_set(g_id)

    def _delete_group(self):
        sel = self.tree_groups.selection()
        if not sel:
            return
        g_id = sel[0]
        if g_id in self.yaml_mgr.groups:
            del self.yaml_mgr.groups[g_id]
            self.yaml_mgr.save()
            self.refresh_all()

    def _clear_pool(self):
        if messagebox.askyesno("Confirm", "Clear all addresses in the Unclassified Pool?"):
            self.yaml_mgr.unclassified_pool = []
            self.yaml_mgr.save()
            self.refresh_all()

    def _import_addresses(self):
        filepath = filedialog.askopenfilename(
            title="Import Addresses",
            filetypes=[("Excel & CSV Files", "*.xlsx;*.csv"), ("Excel Files", "*.xlsx"), ("CSV Files", "*.csv")]
        )
        if not filepath:
            return

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
                return

            current_text = self.txt_emails.get("1.0", tk.END).strip()
            existing = [l.strip().lower() for l in current_text.split("\n") if l.strip()]
            combined = sorted(list(set(existing + imported_emails)))

            self.txt_emails.delete("1.0", tk.END)
            self.txt_emails.insert(tk.END, "\n".join(combined))
            messagebox.showinfo("Imported", f"Successfully imported {len(imported_emails)} distinct email addresses.")
        except Exception as ex:
            messagebox.showerror("Import Error", f"Failed to read file:\n{str(ex)}")
