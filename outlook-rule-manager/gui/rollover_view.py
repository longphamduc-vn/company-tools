"""PST Year Rollover & Data File Management View."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from typing import Dict, List

from core.yaml_manager import YamlConfigManager
from core.outlook_client import BaseOutlookClient
from core.sync_engine import SyncEngine


class RolloverView(ttk.Frame):
    """PST Year Rollover Wizard and Store Health Monitor."""

    def __init__(self, parent, yaml_mgr: YamlConfigManager, outlook: BaseOutlookClient, sync_engine: SyncEngine):
        super().__init__(parent)
        self.yaml_mgr = yaml_mgr
        self.outlook = outlook
        self.sync_engine = sync_engine

        self._build_ui()
        self.refresh_view()

    def _build_ui(self):
        container = ttk.Frame(self, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        lbl_title = ttk.Label(container, text="Yearly PST Rollover Assistant", font=("", 13, "bold"))
        lbl_title.pack(anchor=tk.W, pady=(0, 4))

        lbl_desc = ttk.Label(
            container,
            text="When transitioning to a new year, use this wizard to re-point all Outlook rules to a new PST data file.\n"
                 "Rules will automatically map their destination folders into the new archive.",
            wraplength=650
        )
        lbl_desc.pack(anchor=tk.W, pady=(0, 16))

        # -------------------------------------------------------------
        # Current Active Store Section
        # -------------------------------------------------------------
        frame_current = ttk.LabelFrame(container, text="Current Active Archive Store", padding=12)
        frame_current.pack(fill=tk.X, pady=8)

        grid_cur = ttk.Frame(frame_current)
        grid_cur.pack(fill=tk.X)

        ttk.Label(grid_cur, text="Store Alias / Name:", font=("", 9, "bold")).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.lbl_cur_name = ttk.Label(grid_cur, text="-")
        self.lbl_cur_name.grid(row=0, column=1, sticky=tk.W, padx=8, pady=2)

        ttk.Label(grid_cur, text="File Path:", font=("", 9, "bold")).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.lbl_cur_path = ttk.Label(grid_cur, text="-", wraplength=450)
        self.lbl_cur_path.grid(row=1, column=1, sticky=tk.W, padx=8, pady=2)

        ttk.Label(grid_cur, text="File Size & Status:", font=("", 9, "bold")).grid(row=2, column=0, sticky=tk.W, pady=2)
        self.lbl_cur_size = ttk.Label(grid_cur, text="-")
        self.lbl_cur_size.grid(row=2, column=1, sticky=tk.W, padx=8, pady=2)

        # -------------------------------------------------------------
        # New Store Target Section (Rollover)
        # -------------------------------------------------------------
        frame_new = ttk.LabelFrame(container, text="Rollover to New Yearly PST", padding=12)
        frame_new.pack(fill=tk.X, pady=12)

        grid_new = ttk.Frame(frame_new)
        grid_new.pack(fill=tk.X)

        ttk.Label(grid_new, text="New Store Name (e.g. Archive 2025):").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.ent_new_name = ttk.Entry(grid_new, width=35)
        self.ent_new_name.grid(row=0, column=1, sticky=tk.W, padx=8, pady=4)

        ttk.Label(grid_new, text="New PST File Path:").grid(row=1, column=0, sticky=tk.W, pady=4)
        path_box = ttk.Frame(grid_new)
        path_box.grid(row=1, column=1, sticky=tk.EW, padx=8, pady=4)

        self.ent_new_path = ttk.Entry(path_box, width=40)
        self.ent_new_path.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_browse = ttk.Button(path_box, text="Browse...", command=self._browse_pst)
        btn_browse.pack(side=tk.LEFT, padx=4)

        ttk.Label(grid_new, text="Or Select Mounted Store:").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.cbo_mounted = ttk.Combobox(grid_new, width=38, state="readonly")
        self.cbo_mounted.grid(row=2, column=1, sticky=tk.W, padx=8, pady=4)
        self.cbo_mounted.bind("<<ComboboxSelected>>", self._on_mounted_select)

        # Execution Button (Clean text)
        btn_rollover = ttk.Button(
            frame_new,
            text="Execute 1-Click Rollover to New Store",
            command=self._execute_rollover
        )
        btn_rollover.pack(anchor=tk.E, pady=(12, 4))

    def refresh_view(self):
        active = self.yaml_mgr.stores.get("active_archive")
        if active:
            self.lbl_cur_name.config(text=active.name)
            self.lbl_cur_path.config(text=active.file_path or "(Default Mailbox)")

            if active.file_path and os.path.exists(active.file_path):
                size_bytes = os.path.getsize(active.file_path)
                size_gb = size_bytes / (1024 ** 3)
                if size_gb >= 35:
                    status = f"[CRITICAL] {size_gb:.2f} GB (Recommended to Rollover immediately!)"
                elif size_gb >= 25:
                    status = f"[WARNING] {size_gb:.2f} GB (Notice: Large file size)"
                else:
                    status = f"[OK] {size_gb:.2f} GB (Healthy)"
                self.lbl_cur_size.config(text=status)
            else:
                self.lbl_cur_size.config(text="File not locally indexed / Managed by Outlook")
        else:
            self.lbl_cur_name.config(text="None")
            self.lbl_cur_path.config(text="-")

        stores = self.outlook.get_stores()
        display_options = [f"{s['name']} ({s['file_path'] or 'Primary'})" for s in stores]
        self.cbo_mounted["values"] = display_options
        if display_options:
            self.cbo_mounted.current(0)

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

    def _on_mounted_select(self, event):
        idx = self.cbo_mounted.current()
        stores = self.outlook.get_stores()
        if 0 <= idx < len(stores):
            s = stores[idx]
            self.ent_new_name.delete(0, tk.END)
            self.ent_new_name.insert(0, s["name"])
            self.ent_new_path.delete(0, tk.END)
            self.ent_new_path.insert(0, s["file_path"])

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
