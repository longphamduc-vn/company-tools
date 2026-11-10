"""PST Year Rollover & Multi-Store Deep Scanner View."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from typing import Dict, List, Any

from core.yaml_manager import YamlConfigManager
from core.outlook_client import BaseOutlookClient
from core.sync_engine import SyncEngine


class RolloverView(ttk.Frame):
    """PST Year Rollover Wizard, Multi-Store Scanner & Account-Tagged Naming."""

    def __init__(self, parent, yaml_mgr: YamlConfigManager, outlook: BaseOutlookClient, sync_engine: SyncEngine):
        super().__init__(parent)
        self.yaml_mgr = yaml_mgr
        self.outlook = outlook
        self.sync_engine = sync_engine

        self._build_ui()
        self.refresh_view()

    def _build_ui(self):
        container = ttk.Frame(self, padding=14)
        container.pack(fill=tk.BOTH, expand=True)

        # Header Info
        header_row = ttk.Frame(container)
        header_row.pack(fill=tk.X, pady=(0, 6))

        lbl_title = ttk.Label(header_row, text="Outlook Data Files & Yearly Rollover Manager", font=("", 12, "bold"))
        lbl_title.pack(side=tk.LEFT)

        account = self.outlook.get_current_user_account()
        self.lbl_acc_badge = tk.Label(
            header_row,
            text=f"Active Account: {account}",
            bg="#f1f5f9",
            fg="#0284c7",
            font=("", 9, "bold"),
            padx=8,
            pady=2
        )
        self.lbl_acc_badge.pack(side=tk.RIGHT)

        lbl_desc = ttk.Label(
            container,
            text="Scan all Outlook data files (.pst), prevent multi-account confusion with account-tagged filenames, "
                 "and 1-click re-point rules to a new yearly PST archive.",
            wraplength=800
        )
        lbl_desc.pack(anchor=tk.W, pady=(0, 10))

        # -------------------------------------------------------------
        # Section 1: Multi-Store Deep Scanner Table
        # -------------------------------------------------------------
        frame_stores = ttk.LabelFrame(container, text="All Detected Outlook Data Stores (Scanned across Profile)", padding=8)
        frame_stores.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        cols = ("Name", "Size", "File Path", "Folders")
        self.tree_stores = ttk.Treeview(frame_stores, columns=cols, show="headings", height=4)
        self.tree_stores.heading("Name", text="Store Display Name")
        self.tree_stores.heading("Size", text="Size (GB)")
        self.tree_stores.heading("File Path", text="Physical File Path")
        self.tree_stores.heading("Folders", text="Root Folders")

        self.tree_stores.column("Name", width=180)
        self.tree_stores.column("Size", width=80)
        self.tree_stores.column("File Path", width=280)
        self.tree_stores.column("Folders", width=220)

        scroll_s = ttk.Scrollbar(frame_stores, orient=tk.VERTICAL, command=self.tree_stores.yview)
        self.tree_stores.configure(yscrollcommand=scroll_s.set)
        self.tree_stores.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_s.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree_stores.bind("<<TreeviewSelect>>", self._on_store_selected)

        # -------------------------------------------------------------
        # Section 2: Current Active Archive vs Rollover Action
        # -------------------------------------------------------------
        paned_bottom = ttk.PanedWindow(container, orient=tk.HORIZONTAL)
        paned_bottom.pack(fill=tk.X, pady=4)

        # Left: Current Active Store
        frame_current = ttk.LabelFrame(paned_bottom, text="Active Target Store (Configured in rules.yaml)", padding=10)
        paned_bottom.add(frame_current, weight=1)

        grid_cur = ttk.Frame(frame_current)
        grid_cur.pack(fill=tk.X)

        ttk.Label(grid_cur, text="Alias / Name:", font=("", 9, "bold")).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.lbl_cur_name = ttk.Label(grid_cur, text="-")
        self.lbl_cur_name.grid(row=0, column=1, sticky=tk.W, padx=6, pady=2)

        ttk.Label(grid_cur, text="File Path:", font=("", 9, "bold")).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.lbl_cur_path = ttk.Label(grid_cur, text="-", wraplength=320)
        self.lbl_cur_path.grid(row=1, column=1, sticky=tk.W, padx=6, pady=2)

        ttk.Label(grid_cur, text="Health Status:", font=("", 9, "bold")).grid(row=2, column=0, sticky=tk.W, pady=2)
        self.lbl_cur_size = ttk.Label(grid_cur, text="-")
        self.lbl_cur_size.grid(row=2, column=1, sticky=tk.W, padx=6, pady=2)

        # Right: Rollover to New Store
        frame_new = ttk.LabelFrame(paned_bottom, text="Rollover to New Yearly PST (Account Tagged)", padding=10)
        paned_bottom.add(frame_new, weight=1)

        grid_new = ttk.Frame(frame_new)
        grid_new.pack(fill=tk.X)

        ttk.Label(grid_new, text="New Store Name:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.ent_new_name = ttk.Entry(grid_new, width=32)
        self.ent_new_name.grid(row=0, column=1, sticky=tk.W, padx=6, pady=3)

        ttk.Label(grid_new, text="PST File Path:").grid(row=1, column=0, sticky=tk.W, pady=3)
        path_box = ttk.Frame(grid_new)
        path_box.grid(row=1, column=1, sticky=tk.EW, padx=6, pady=3)

        self.ent_new_path = ttk.Entry(path_box, width=24)
        self.ent_new_path.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_browse = ttk.Button(path_box, text="Browse", command=self._browse_pst)
        btn_browse.pack(side=tk.LEFT, padx=2)

        btn_rollover = ttk.Button(
            frame_new,
            text="Execute 1-Click Rollover",
            command=self._execute_rollover
        )
        btn_rollover.pack(anchor=tk.E, pady=(8, 2))

    def refresh_view(self):
        # Update Active Store info
        active = self.yaml_mgr.stores.get("active_archive")
        if active:
            self.lbl_cur_name.config(text=active.name)
            self.lbl_cur_path.config(text=active.file_path or "(Default Mailbox)")

            if active.file_path and os.path.exists(active.file_path):
                size_gb = round(os.path.getsize(active.file_path) / (1024 ** 3), 2)
                if size_gb >= 35:
                    status = f"[CRITICAL] {size_gb} GB (Rollover Recommended)"
                elif size_gb >= 25:
                    status = f"[WARNING] {size_gb} GB (Large size)"
                else:
                    status = f"[OK] {size_gb} GB (Healthy)"
                self.lbl_cur_size.config(text=status)
            else:
                self.lbl_cur_size.config(text="File managed by Outlook")
        else:
            self.lbl_cur_name.config(text="None")
            self.lbl_cur_path.config(text="-")

        # Scan and populate all mounted stores
        self.tree_stores.delete(*self.tree_stores.get_children())
        stores = self.outlook.get_stores()
        for idx, s in enumerate(stores):
            size_txt = f"{s.get('size_gb', 0.0)} GB" if s.get("size_gb") else "-"
            folders_txt = ", ".join(s.get("folders", [])[:4])
            if len(s.get("folders", [])) > 4:
                folders_txt += "..."
            self.tree_stores.insert(
                "",
                tk.END,
                iid=f"store_{idx}",
                values=(s["name"], size_txt, s.get("file_path", "(Primary Mailbox)"), folders_txt)
            )

        # Smart Default for Rollover (Account Tagged)
        user_clean = self.outlook.get_current_user_account().split("@")[0].replace(".", "_")
        suggested_name = f"{user_clean}_Archive_2025"
        self.ent_new_name.delete(0, tk.END)
        self.ent_new_name.insert(0, suggested_name)

        suggested_path = f"C:\\Outlook_Data\\{user_clean}_Archive_2025.pst"
        self.ent_new_path.delete(0, tk.END)
        self.ent_new_path.insert(0, suggested_path)

    def _on_store_selected(self, event):
        sel = self.tree_stores.selection()
        if not sel:
            return
        idx = int(sel[0].split("_")[1])
        stores = self.outlook.get_stores()
        if 0 <= idx < len(stores):
            s = stores[idx]
            self.ent_new_name.delete(0, tk.END)
            self.ent_new_name.insert(0, s["name"])
            self.ent_new_path.delete(0, tk.END)
            self.ent_new_path.insert(0, s.get("file_path", ""))

    def _browse_pst(self):
        filename = filedialog.askopenfilename(
            title="Select Outlook PST File",
            filetypes=[("Outlook Data Files (*.pst)", "*.pst"), ("All Files", "*.*")]
        )
        if filename:
            self.ent_new_path.delete(0, tk.END)
            self.ent_new_path.insert(0, filename)
            base = os.path.splitext(os.path.basename(filename))[0]
            self.ent_new_name.delete(0, tk.END)
            self.ent_new_name.insert(0, base.replace("_", " "))

    def _execute_rollover(self):
        new_name = self.ent_new_name.get().strip()
        new_path = self.ent_new_path.get().strip()

        if not new_name or not new_path:
            messagebox.showwarning("Notice", "Please specify both the New Store Name and File Path.")
            return

        if "onedrive" in new_path.lower() or "\\\\" in new_path:
            proceed = messagebox.askyesno(
                "Storage Warning",
                "WARNING: Storing Outlook PST files on OneDrive, SharePoint, or Network Shares (SMB) "
                "carries a high risk of database corruption.\n\nAre you sure you want to proceed?",
                icon=messagebox.WARNING
            )
            if not proceed:
                return

        confirm = messagebox.askyesno(
            "Confirm PST Rollover",
            f"Are you sure you want to rollover all active rules to:\n'{new_name}' ({new_path})?\n\n"
            f"This will update rules.yaml and re-point target folders in Outlook."
        )
        if not confirm:
            return

        success, msg = self.sync_engine.perform_rollover(new_name, new_path)
        if success:
            messagebox.showinfo("Rollover Complete", msg)
            self.refresh_view()
        else:
            messagebox.showerror("Rollover Failed", msg)
