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
from typing import List, Dict, Optional, Callable

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

from lgd_vault.models import DrawingItem

logger = logging.getLogger("lgd_vault.excel_grid")


class ExcelInputGrid(ttk.Frame):
    """Excel-like Table for editing, copying, and pasting drawing input items."""

    def __init__(self, parent, on_change: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(parent, **kwargs)
        self.on_change = on_change
        self.active_entry: Optional[ttk.Entry] = None
        self.editing_cell: Optional[tuple] = None  # (item_id, col_name)

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
            text="📋 Paste from Excel (Ctrl+V)",
            style="Accent.TButton",
            command=self.paste_from_clipboard,
        )
        btn_paste.pack(side=tk.LEFT, padx=(0, 2))

        btn_add = ttk.Button(tb, text="➕ Add", width=6, command=lambda: self.add_row("", ""))
        btn_add.pack(side=tk.LEFT, padx=1)

        btn_del = ttk.Button(tb, text="➖ Delete", width=7, command=self.delete_selected_rows)
        btn_del.pack(side=tk.LEFT, padx=1)

        btn_import = ttk.Button(tb, text="📁 Import File", width=11, command=self.import_file)
        btn_import.pack(side=tk.LEFT, padx=1)

        btn_clear = ttk.Button(tb, text="🗑️ Clear All", width=9, command=self.clear_all)
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
