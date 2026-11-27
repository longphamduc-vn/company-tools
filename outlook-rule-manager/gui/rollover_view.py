"""PST Year Rollover & Multi-Store Deep Scanner View."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from datetime import date
from typing import Any, Callable, Dict, List, Optional

from core.yaml_manager import YamlConfigManager
from core.outlook_client import BaseOutlookClient
from core.sync_engine import SyncEngine
from core.rollover_suggest import suggest_new_pst, suggest_rollover_target, validate_new_pst_path


class RolloverView(ttk.Frame):
    """PST Year Rollover Wizard, Multi-Store Scanner & Account-Tagged Naming."""

    def __init__(
        self,
        parent,
        yaml_mgr: YamlConfigManager,
        outlook: BaseOutlookClient,
        sync_engine: SyncEngine,
        on_rollover_complete: Optional[Callable[[], Any]] = None,
    ):
        super().__init__(parent)
        self.yaml_mgr = yaml_mgr
        self.outlook = outlook
        self.sync_engine = sync_engine
        self.on_rollover_complete = on_rollover_complete

        self.var_new_name = tk.StringVar()
        self.var_new_path = tk.StringVar()
        self._rollover_fields_initialized: bool = False

        self._build_ui()
        self.var_new_path.trace_add("write", self._update_rollover_button_state)
        self.refresh_view()

    def _build_ui(self):
        container = ttk.Frame(self, padding=14)
        container.pack(fill=tk.BOTH, expand=True)

        # Header Info
        header_row = ttk.Frame(container)
        header_row.pack(fill=tk.X, pady=(0, 6))

        lbl_title = ttk.Label(header_row, text="Yearly PST Rollover", font=("", 12, "bold"))
        lbl_title.pack(side=tk.LEFT)

        account = self.outlook.get_current_user_account()
        self.lbl_acc_badge = ttk.Label(
            header_row,
            text=f"Account: {account}",
            foreground="#0284c7",
            font=("", 9, "bold"),
        )
        self.lbl_acc_badge.pack(side=tk.RIGHT)

        lbl_desc = ttk.Label(
            container,
            text="Re-point Companion rules to a new yearly PST: pick one open in Outlook, or create one.",
            wraplength=800
        )
        lbl_desc.pack(anchor=tk.W, pady=(0, 10))

        # -------------------------------------------------------------
        # Section 1: Multi-Store Deep Scanner Table
        # -------------------------------------------------------------
        frame_stores = ttk.LabelFrame(container, text="Outlook Data Files (click one to select it)", padding=8)
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
        frame_current = ttk.LabelFrame(paned_bottom, text="Current Archive", padding=10)
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
        frame_new = ttk.LabelFrame(paned_bottom, text="New Archive", padding=10)
        paned_bottom.add(frame_new, weight=1)

        grid_new = ttk.Frame(frame_new)
        grid_new.pack(fill=tk.X)

        ttk.Label(grid_new, text="New Store Name:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.ent_new_name = ttk.Entry(grid_new, textvariable=self.var_new_name, width=32)
        self.ent_new_name.grid(row=0, column=1, sticky=tk.W, padx=6, pady=3)

        ttk.Label(grid_new, text="PST File Path:").grid(row=1, column=0, sticky=tk.W, pady=3)
        path_box = ttk.Frame(grid_new)
        path_box.grid(row=1, column=1, sticky=tk.EW, padx=6, pady=3)

        self.ent_new_path = ttk.Entry(path_box, textvariable=self.var_new_path, width=24)
        self.ent_new_path.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_browse = ttk.Button(path_box, text="Browse", command=self._browse_pst)
        btn_browse.pack(side=tk.LEFT, padx=2)

        self.btn_create_pst = ttk.Button(grid_new, text="Create new PST...", command=self._create_new_pst)
        self.btn_create_pst.grid(row=2, column=1, sticky=tk.W, padx=6, pady=(4, 0))

        ttk.Label(
            frame_new,
            text="Tip: select a PST that is already open in Outlook in the table above, or click "
                 "'Create new PST...' to make an empty one and open it in Outlook. Rules only change "
                 "when you click Execute.",
            foreground="#475569",
            wraplength=380,
            font=("", 8),
        ).pack(anchor=tk.W, pady=(6, 2))

        action_row = ttk.Frame(frame_new)
        action_row.pack(fill=tk.X, pady=(4, 2))

        self.lbl_rollover_hint = ttk.Label(
            action_row,
            text="",
            foreground="#64748b",
            wraplength=240,
            font=("", 8),
        )
        self.lbl_rollover_hint.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_rollover = ttk.Button(
            action_row,
            text="Execute 1-Click Rollover",
            command=self._execute_rollover
        )
        self.btn_rollover.pack(side=tk.RIGHT)

    def _update_rollover_button_state(self, *_args):
        new_path = self.var_new_path.get().strip()
        active = self.yaml_mgr.stores.get("active_archive")
        cur_path = active.file_path.strip() if active and active.file_path else ""

        if not new_path:
            self.btn_rollover.config(state=tk.DISABLED)
            self.lbl_rollover_hint.config(
                text="Enter or select a mounted PST path to enable rollover.",
                foreground="#64748b",
            )
            return

        if cur_path and os.path.normcase(os.path.normpath(new_path)) == os.path.normcase(os.path.normpath(cur_path)):
            self.btn_rollover.config(state=tk.DISABLED)
            self.lbl_rollover_hint.config(
                text="Disabled: selected path matches current active archive.",
                foreground="#ea580c",
            )
            return

        if not self.outlook.store_exists(new_path):
            self.btn_rollover.config(state=tk.DISABLED)
            self.lbl_rollover_hint.config(
                text="Disabled: store is not currently open/mounted in Outlook.",
                foreground="#dc2626",
            )
            return

        self.btn_rollover.config(state=tk.NORMAL)
        self.lbl_rollover_hint.config(
            text="Ready to rollover to selected Outlook store.",
            foreground="#16a34a",
        )

    def refresh_view(self):
        # Update Active Store info
        active = self.yaml_mgr.stores.get("active_archive")
        if active:
            self.lbl_cur_name.config(text=active.name)
            self.lbl_cur_path.config(text=active.file_path or "(Default Mailbox)")

            if not active.file_path:
                self.lbl_cur_size.config(text="No PST file path configured", foreground="#64748b")
            elif not os.path.exists(active.file_path):
                self.lbl_cur_size.config(text="[MISSING] File not found on disk", foreground="#dc2626")
            elif not self.outlook.store_exists(active.file_path):
                self.lbl_cur_size.config(
                    text="[NOT MOUNTED] File exists but is not open in Outlook",
                    foreground="#ea580c",
                )
            else:
                size_gb = round(os.path.getsize(active.file_path) / (1024 ** 3), 2)
                if size_gb >= 35:
                    status = f"[CRITICAL] {size_gb} GB (Rollover Recommended)"
                    color = "#dc2626"
                elif size_gb >= 25:
                    status = f"[WARNING] {size_gb} GB (Large size)"
                    color = "#ea580c"
                else:
                    status = f"[OK] {size_gb} GB (Healthy)"
                    color = "#16a34a"
                self.lbl_cur_size.config(text=status, foreground=color)
        else:
            self.lbl_cur_name.config(text="None")
            self.lbl_cur_path.config(text="-")
            self.lbl_cur_size.config(text="-", foreground="#64748b")

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

        # Smart next-year suggestion: fill only on first load or when field is empty
        suggested_name, suggested_path = suggest_rollover_target(
            active.name if active else "",
            active.file_path if active else "",
        )
        if not self._rollover_fields_initialized:
            self.var_new_name.set(suggested_name)
            self.var_new_path.set(suggested_path)
            self._rollover_fields_initialized = True
        else:
            if not self.var_new_name.get().strip() and suggested_name:
                self.var_new_name.set(suggested_name)
            if not self.var_new_path.get().strip() and suggested_path:
                self.var_new_path.set(suggested_path)

        self._update_rollover_button_state()

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

    # -- create a brand-new PST (first year) -------------------------------
    def _ask_new_pst_path(self, initial_dir: str, initial_file: str) -> str:
        return filedialog.asksaveasfilename(
            title="Create a new Outlook Data File (.pst)",
            initialdir=initial_dir,
            initialfile=initial_file,
            defaultextension=".pst",
            filetypes=[("Outlook Data Files (*.pst)", "*.pst")],
            confirmoverwrite=False,   # existing files are refused below, never overwritten
        )

    def _create_new_pst(self) -> bool:
        """Create an empty PST, open it in Outlook, and select it as the new archive (no rule changes)."""
        name, path = suggest_new_pst(self.outlook.get_stores(), date.today().year)
        chosen = self._ask_new_pst_path(os.path.dirname(path), os.path.basename(path))
        if not chosen:
            return False
        chosen = os.path.normpath(chosen)
        problem = validate_new_pst_path(chosen) if not self.outlook.is_simulated() else ""
        if problem:
            messagebox.showwarning("Create new PST", problem)
            return False

        typed = self.ent_new_name.get().strip()
        active = self.yaml_mgr.stores.get("active_archive")
        # Keep a name the user typed; otherwise name it after the file (Archive_2027.pst -> Archive 2027)
        if not typed or (active and typed == active.name) or typed == self._suggested_name():
            display = os.path.splitext(os.path.basename(chosen))[0].replace("_", " ")
        else:
            display = typed
        if not messagebox.askyesno(
            "Create new PST",
            f"Create an empty PST and open it in Outlook?\n\n  File: {chosen}\n  Name in Outlook: {display}\n\n"
            "Your rules do not change until you click 'Execute 1-Click Rollover'.",
        ):
            return False

        ok, result = self.outlook.create_pst(chosen, display)
        if not ok:
            messagebox.showerror("Create new PST", result)
            return False
        self.refresh_view()
        self._select_store_by_path(result)
        self.ent_new_name.delete(0, tk.END)
        self.ent_new_name.insert(0, display)
        note = "\n\n[SIMULATION] No file was written." if self.outlook.is_simulated() else ""
        messagebox.showinfo(
            "Create new PST",
            f"Created and opened in Outlook:\n{result}\n\nIt is selected below. Click "
            f"'Execute 1-Click Rollover' to send new mail there.{note}",
        )
        return True

    def _suggested_name(self) -> str:
        active = self.yaml_mgr.stores.get("active_archive")
        return suggest_rollover_target(active.name if active else "", "")[0]

    def _select_store_by_path(self, path: str) -> None:
        want = os.path.normcase(os.path.normpath(path))
        for idx, s in enumerate(self.outlook.get_stores()):
            fp = s.get("file_path", "")
            if fp and os.path.normcase(os.path.normpath(fp)) == want:
                iid = f"store_{idx}"
                if self.tree_stores.exists(iid):
                    self.tree_stores.selection_set(iid)
                    self.tree_stores.see(iid)
                    self._on_store_selected(None)
                return
        self.ent_new_path.delete(0, tk.END)
        self.ent_new_path.insert(0, path)

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
            if self.outlook.is_simulated():
                msg = f"[SIMULATION] No changes were made to Outlook.\n\n{msg}"
            messagebox.showinfo("Rollover Complete", msg)
            self._rollover_fields_initialized = False
            self.refresh_view()
            if self.on_rollover_complete:
                self.on_rollover_complete()
        else:
            messagebox.showerror("Rollover Failed", msg)
