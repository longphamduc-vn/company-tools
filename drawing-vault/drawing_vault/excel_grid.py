"""
Excel-like Input Grid Widget for QCodes and Device Aliases.
Supports:
- Direct copy & paste from Microsoft Excel / Google Sheets (Tab-separated values / newlines).
- In-place cell editing (Double-click or Enter to edit, Tab to advance).
- Adding / deleting rows.
- Importing from .xlsx, .xls, .csv, and .txt files.
- Exporting to CSV / Excel.
"""

import csv
import logging
import os
import re
import subprocess
import sys
from typing import List, Dict, Optional, Callable

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

from drawing_vault.models import DrawingItem
from drawing_vault.logger_setup import LOG_FILE_PATH

logger = logging.getLogger("drawing_vault.excel_grid")


class ExcelInputGrid(ttk.Frame):
    """Excel-like Table for editing, copying, and pasting drawing input items."""

    def __init__(self, parent, on_change: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(parent, **kwargs)
        self.on_change = on_change
        self.active_entry: Optional[ttk.Entry] = None
        self.editing_cell: Optional[tuple] = None  # (item_id, col_name)
        self.item_error_details: Dict[str, str] = {}  # QCode -> detailed error trace/message

        self._build_toolbar()
        self._build_grid()
        self._bind_events()

        # Seed with initial sample rows
        self.add_row("QCAK09691", "Machine_2018021GC26")
        self.add_row("QCAD69945", "Motor_Assembly")

    def _build_toolbar(self):
        """Action toolbar above the Excel grid."""
        tb = ttk.Frame(self, padding=(0, 2, 0, 4))
        tb.pack(fill=tk.X, side=tk.TOP)

        btn_paste = ttk.Button(
            tb,
            text="📋 Paste (Ctrl+V)",
            style="Accent.TButton",
            command=self.paste_from_clipboard,
        )
        btn_paste.pack(side=tk.LEFT, padx=(0, 2))

        btn_add = ttk.Button(tb, text="➕ Add", width=5, command=lambda: self.add_row("", ""))
        btn_add.pack(side=tk.LEFT, padx=1)

        btn_del = ttk.Button(tb, text="➖ Delete", width=6, command=self.delete_selected_rows)
        btn_del.pack(side=tk.LEFT, padx=1)

        btn_err = ttk.Button(tb, text="🔍 View Error", width=11, command=self.show_selected_error)
        btn_err.pack(side=tk.LEFT, padx=1)

        btn_import = ttk.Button(tb, text="📁 Import", width=8, command=self.import_file)
        btn_import.pack(side=tk.LEFT, padx=1)

        btn_clear = ttk.Button(tb, text="🗑️ Clear", width=7, command=self.clear_all)
        btn_clear.pack(side=tk.LEFT, padx=1)

        self.lbl_count = ttk.Label(tb, text="0 rows", font=("Segoe UI", 9, "bold"), foreground="#0052cc")
        self.lbl_count.pack(side=tk.RIGHT, padx=4)

    def _build_grid(self):
        """The spreadsheet-like Treeview table with vertical & horizontal scrollbars."""
        grid_container = ttk.Frame(self, relief="sunken", borderwidth=1)
        grid_container.pack(fill=tk.BOTH, expand=True)

        columns = ("row_no", "qcode", "custom_name", "status")
        self.tree = ttk.Treeview(
            grid_container,
            columns=columns,
            show="headings",
            selectmode="extended",
            height=8,
        )

        self.tree.heading("row_no", text="#", anchor="center")
        self.tree.heading("qcode", text="QCode *", anchor="w")
        self.tree.heading("custom_name", text="Device Name / Alias", anchor="w")
        self.tree.heading("status", text="Status", anchor="center")

        self.tree.column("row_no", width=40, minwidth=35, stretch=False, anchor="center")
        self.tree.column("qcode", width=130, minwidth=100, stretch=True, anchor="w")
        self.tree.column("custom_name", width=160, minwidth=120, stretch=True, anchor="w")
        self.tree.column("status", width=95, minwidth=80, stretch=False, anchor="center")

        vsb = ttk.Scrollbar(grid_container, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(grid_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        grid_container.grid_rowconfigure(0, weight=1)
        grid_container.grid_columnconfigure(0, weight=1)

        # Bottom hint
        hint_lbl = ttk.Label(
            self,
            text="💡 Tip: Copy columns from Excel and press Ctrl+V to paste directly. Double-click any cell to edit.",
            font=("Segoe UI", 8, "italic"),
            foreground="#6b778c",
        )
        hint_lbl.pack(anchor="w", pady=(3, 0))

    def _bind_events(self):
        """Binds keyboard and mouse interactions."""
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Return>", self._on_enter_pressed)
        self.tree.bind("<Control-v>", lambda e: self.paste_from_clipboard())
        self.tree.bind("<Control-V>", lambda e: self.paste_from_clipboard())
        self.tree.bind("<Control-c>", lambda e: self.copy_selected_to_clipboard())
        self.tree.bind("<Control-C>", lambda e: self.copy_selected_to_clipboard())
        self.tree.bind("<Delete>", lambda e: self.delete_selected_rows())
        self.tree.bind("<BackSpace>", lambda e: self.delete_selected_rows())

        # Context menu
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="🔍 View Error Details", command=self.show_selected_error)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📋 Copy Row (Ctrl+C)", command=self.copy_selected_to_clipboard)
        self.context_menu.add_command(label="📋 Paste (Ctrl+V)", command=self.paste_from_clipboard)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="➕ Add Row", command=lambda: self.add_row("", ""))
        self.context_menu.add_command(label="➖ Delete Row", command=self.delete_selected_rows)

        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Button-2>", self._on_right_click)

    def _on_right_click(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    # ------------------ Cell In-Place Editing ------------------

    def _on_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        column_id = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return

        # Column mapping: #1 -> row_no (read-only), #2 -> qcode, #3 -> custom_name, #4 -> status
        if column_id in ("#2", "#3"):
            self._start_cell_edit(row_id, column_id)
        elif column_id == "#4":
            self.show_error_dialog(row_id)

    def _on_enter_pressed(self, event):
        selected = self.tree.selection()
        if selected:
            self._start_cell_edit(selected[0], "#2")

    def _start_cell_edit(self, item_id: str, col_id: str):
        self._commit_cell_edit()

        # Get cell bounding box
        bbox = self.tree.bbox(item_id, col_id)
        if not bbox:
            return

        x, y, w, h = bbox
        col_index = int(col_id.replace("#", "")) - 1
        current_val = self.tree.item(item_id, "values")[col_index]

        self.editing_cell = (item_id, col_id)
        self.active_entry = ttk.Entry(self.tree, font=("Segoe UI", 9))
        self.active_entry.place(x=x, y=y, width=w, height=h)
        self.active_entry.insert(0, current_val)
        self.active_entry.select_range(0, tk.END)
        self.active_entry.focus_set()

        self.active_entry.bind("<Return>", lambda e: self._commit_cell_edit())
        self.active_entry.bind("<FocusOut>", lambda e: self._commit_cell_edit())
        self.active_entry.bind("<Escape>", lambda e: self._cancel_cell_edit())
        self.active_entry.bind("<Tab>", lambda e: self._advance_cell_edit(item_id, col_id))

    def _commit_cell_edit(self):
        if not self.active_entry or not self.editing_cell:
            return

        item_id, col_id = self.editing_cell
        new_val = self.active_entry.get().strip()

        col_index = int(col_id.replace("#", "")) - 1
        values = list(self.tree.item(item_id, "values"))

        if col_index == 1:  # QCode column
            new_val = new_val.upper()

        values[col_index] = new_val
        self.tree.item(item_id, values=values)

        self._cancel_cell_edit()
        self._notify_change()

    def _cancel_cell_edit(self):
        if self.active_entry:
            self.active_entry.destroy()
            self.active_entry = None
        self.editing_cell = None

    def _advance_cell_edit(self, item_id: str, col_id: str):
        self._commit_cell_edit()
        if col_id == "#2":
            self.after(10, lambda: self._start_cell_edit(item_id, "#3"))
        elif col_id == "#3":
            # Advance to next row
            next_item = self.tree.next(item_id)
            if not next_item:
                # Add a new row automatically like Excel!
                next_item = self.add_row("", "")
            self.after(10, lambda: self._start_cell_edit(next_item, "#2"))

    # ------------------ Clipboard Copy & Paste ------------------

    def paste_from_clipboard(self):
        """
        Parses clipboard content formatted from Excel (tab-delimited, newline-delimited).
        Works seamlessly with single or multiple columns.
        """
        try:
            clipboard_data = self.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("Empty Clipboard", "No data found in clipboard.")
            return

        if not clipboard_data or not clipboard_data.strip():
            return

        lines = [line.strip("\r") for line in clipboard_data.split("\n")]
        parsed_count = 0

        # Check if first row is a header
        first_line = lines[0].lower() if lines else ""
        start_idx = 0
        if "qcode" in first_line or "mã" in first_line or "drawing" in first_line:
            start_idx = 1

        for line in lines[start_idx:]:
            if not line.strip():
                continue

            # Split by Tab (standard Excel copy) or Comma (CSV copy)
            if "\t" in line:
                cols = [c.strip() for c in line.split("\t")]
            elif "," in line:
                cols = [c.strip() for c in line.split(",")]
            else:
                cols = [line.strip()]

            qcode = cols[0].upper()
            alias = cols[1] if len(cols) > 1 else ""

            # Check if this QCode looks like a valid code or token
            if qcode:
                self.add_row(qcode, alias)
                parsed_count += 1

        self._renumber_rows()
        self._notify_change()

        if parsed_count > 0:
            logger.info("Pasted %d items from clipboard into Excel grid", parsed_count)

    def copy_selected_to_clipboard(self):
        """Copies selected rows back to clipboard formatted for Excel."""
        selected = self.tree.selection()
        if not selected:
            return

        lines = []
        for item_id in selected:
            vals = self.tree.item(item_id, "values")
            # Format: QCode \t CustomName
            lines.append(f"{vals[1]}\t{vals[2]}")

        payload = "\n".join(lines)
        self.clipboard_clear()
        self.clipboard_append(payload)

    # ------------------ Row Operations ------------------

    def add_row(self, qcode: str = "", custom_name: str = "", status: str = "Pending") -> str:
        """Appends a new row to the table."""
        count = len(self.tree.get_children()) + 1
        item_id = self.tree.insert(
            "",
            tk.END,
            values=(count, qcode.upper(), custom_name, status),
        )
        self._renumber_rows()
        self._notify_change()
        return item_id

    def delete_selected_rows(self):
        """Deletes selected row(s) from table."""
        selected = self.tree.selection()
        if not selected:
            return
        for item_id in selected:
            self.tree.delete(item_id)
        self._renumber_rows()
        self._notify_change()

    def clear_all(self):
        """Clears all rows."""
        if not self.tree.get_children():
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._renumber_rows()
        self._notify_change()

    def _renumber_rows(self):
        """Updates row numbers (#) sequentially."""
        children = self.tree.get_children()
        for idx, item_id in enumerate(children, 1):
            vals = list(self.tree.item(item_id, "values"))
            vals[0] = str(idx)
            self.tree.item(item_id, values=vals)

        self.lbl_count.configure(text=f"{len(children)} rows")

    def _notify_change(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    # ------------------ Import File Support (.xlsx, .csv, .txt) ------------------

    def import_file(self):
        path = filedialog.askopenfilename(
            title="Import QCodes File",
            filetypes=[
                ("All Supported Formats", "*.xlsx *.xls *.csv *.txt"),
                ("Excel Files", "*.xlsx *.xls"),
                ("CSV Files", "*.csv"),
                ("Text Files", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        ext = os.path.splitext(path)[1].lower()
        imported = 0

        try:
            if ext in (".xlsx", ".xls") and HAS_OPENPYXL:
                wb = openpyxl.load_workbook(path, data_only=True)
                ws = wb.active
                for row in ws.iter_rows(values_only=True):
                    if not row or not any(row):
                        continue
                    first_cell = str(row[0]).strip() if row[0] is not None else ""
                    if not first_cell or first_cell.lower() in ("qcode", "mã", "#", "stt"):
                        continue
                    alias = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
                    self.add_row(first_cell, alias)
                    imported += 1

            elif ext == ".csv":
                with open(path, "r", encoding="utf-8-sig") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if not row or not any(row):
                            continue
                        first_cell = row[0].strip()
                        if not first_cell or first_cell.lower() in ("qcode", "mã", "#", "stt"):
                            continue
                        alias = row[1].strip() if len(row) > 1 else ""
                        self.add_row(first_cell, alias)
                        imported += 1

            else:  # Text file
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = [p.strip() for p in (line.split("\t") if "\t" in line else line.split(",", 1))]
                        qcode = parts[0]
                        alias = parts[1] if len(parts) > 1 else ""
                        if qcode:
                            self.add_row(qcode, alias)
                            imported += 1

            messagebox.showinfo("Import Successful", f"Successfully imported {imported} row(s) into Excel grid.")

        except Exception as e:
            logger.exception("Error importing file %s: %s", path, e)
            messagebox.showerror("Import Error", f"Could not read file: {e}")

    # ------------------ Data Retrieval & Status Updates ------------------

    def get_items(self) -> List[DrawingItem]:
        """Returns all non-empty DrawingItems from the grid."""
        items: List[DrawingItem] = []
        for item_id in self.tree.get_children():
            vals = self.tree.item(item_id, "values")
            qcode = vals[1].strip()
            custom_name = vals[2].strip() if len(vals) > 2 else ""
            if qcode:
                items.append(DrawingItem(qcode=qcode, custom_name=custom_name))
        return items

    def update_item_status(self, qcode: str, status: str):
        """Updates the status column for a given QCode in the grid."""
        for item_id in self.tree.get_children():
            vals = list(self.tree.item(item_id, "values"))
            if vals[1].upper() == qcode.upper():
                vals[3] = status
                self.tree.item(item_id, values=vals)
                break

    def set_item_error(self, qcode: str, error_detail: str):
        """Saves detailed diagnostic error for a given QCode."""
        if qcode:
            self.item_error_details[qcode.upper()] = error_detail

    def get_item_error(self, qcode: str) -> str:
        """Retrieves stored error detail for a given QCode."""
        return self.item_error_details.get(qcode.upper(), "")

    def show_selected_error(self):
        """Shows error dialog for the currently selected row."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please click on a row in the table first.")
            return
        self.show_error_dialog(selected[0])

    def show_error_dialog(self, item_id: str):
        """Displays comprehensive error diagnostics dialog for an item."""
        vals = self.tree.item(item_id, "values")
        if not vals:
            return

        row_no, qcode, alias, status = vals[0], vals[1], vals[2], vals[3]
        error_detail = self.get_item_error(qcode)

        if not error_detail and "error" not in status.lower() and "fail" not in status.lower():
            messagebox.showinfo(
                f"Status: {qcode}",
                f"QCode: {qcode}\nAlias: {alias or 'None'}\nStatus: {status}\n\nNo errors recorded for this item.",
            )
            return

        if not error_detail:
            error_detail = f"Status: {status}\n\nNo extended error trace recorded. Please inspect the main log console or vault_download.log."

        # Create diagnostic modal window
        win = tk.Toplevel(self)
        win.title(f"Diagnostic Error Details - {qcode}")
        win.geometry("700x520")
        win.minsize(550, 400)
        win.transient(self.winfo_toplevel())

        # Top Info Card
        info_frame = ttk.Frame(win, padding=12)
        info_frame.pack(fill=tk.X)

        title_lbl = ttk.Label(
            info_frame,
            text=f"❌ Download Error: {qcode}",
            font=("Segoe UI", 12, "bold"),
            foreground="#de350b",
        )
        title_lbl.pack(anchor="w")

        meta_text = f"Device Alias: {alias or '(None)'}   |   Current Status: {status}\nLog File: {LOG_FILE_PATH}"
        ttk.Label(info_frame, text=meta_text, font=("Segoe UI", 9), foreground="#5e6c84").pack(anchor="w", pady=(2, 0))

        # Text area for detailed error trace
        text_frame = ttk.Frame(win, padding=(12, 0, 12, 12))
        text_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(text_frame, text="Detailed Diagnostic Information & Server Response:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        txt = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#1e1e24",
            fg="#f8f9fa",
            insertbackground="white",
            padx=8,
            pady=8,
            relief="solid",
            borderwidth=1,
        )
        scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)

        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        txt.insert("1.0", error_detail)
        txt.configure(state="disabled")

        # Bottom Button Bar
        btn_bar = ttk.Frame(win, padding=12)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        def copy_to_clipboard():
            self.clipboard_clear()
            self.clipboard_append(f"QCode: {qcode}\nAlias: {alias}\nStatus: {status}\n\n{error_detail}")
            lbl_copied.configure(text="✅ Copied to clipboard!")
            win.after(2500, lambda: lbl_copied.configure(text=""))

        def open_log():
            if not os.path.isfile(LOG_FILE_PATH):
                messagebox.showinfo("Log File", f"Log file does not exist yet:\n{LOG_FILE_PATH}")
                return
            try:
                if sys.platform == "win32":
                    os.startfile(LOG_FILE_PATH)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", LOG_FILE_PATH])
                else:
                    subprocess.Popen(["xdg-open", LOG_FILE_PATH])
            except Exception as e:
                messagebox.showerror("Log File Error", f"Cannot open log file: {e}")

        ttk.Button(btn_bar, text="📋 Copy Error Details", command=copy_to_clipboard).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="📂 Open Full Log File", command=open_log).pack(side=tk.LEFT, padx=4)

        lbl_copied = ttk.Label(btn_bar, text="", font=("Segoe UI", 9, "bold"), foreground="#00875a")
        lbl_copied.pack(side=tk.LEFT, padx=8)

        ttk.Button(btn_bar, text="Close", width=9, command=win.destroy).pack(side=tk.RIGHT)

