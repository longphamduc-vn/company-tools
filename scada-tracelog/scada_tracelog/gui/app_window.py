# -*- coding: utf-8 -*-
import os
import threading
import queue
from datetime import datetime
from typing import Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from scada_tracelog.core.exceptions import Excel256ColumnLimitError
from scada_tracelog.core.processor import SCADADataProcessor
from scada_tracelog.gui.theme import Theme
from scada_tracelog.utils.config_manager import ConfigManager
from scada_tracelog.utils.file_helpers import open_file_in_os

class MainWindow:
    """
    Cửa sổ chính của ứng dụng SCADA-TraceLog.
    Giao diện 100% Tiếng Anh, font chữ to rõ ràng, hỗ trợ đa luồng (non-blocking),
    tự động lưu và khôi phục thiết lập người dùng.
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SCADA-TraceLog | Industrial Recipe Audit & Data Guard")
        self.root.geometry("960x820")
        self.root.minsize(860, 700)
        
        # Load user saved preferences
        self.saved_cfg = ConfigManager.load_config()
        
        self.mode_var = tk.StringVar(value=self.saved_cfg.get("input_mode", "single"))
        self.path_var = tk.StringVar(value=self.saved_cfg.get("last_path", ""))
        self.include_baseline_var = tk.BooleanVar(value=self.saved_cfg.get("include_baseline", False))
        self.param_format_var = tk.StringVar(value=self.saved_cfg.get("param_format", "Description Only (inside [...])"))
        self.auto_open_var = tk.BooleanVar(value=self.saved_cfg.get("auto_open", True))
        self.output_filename_var = tk.StringVar(value=self.saved_cfg.get("output_filename", "scada_change_log.csv"))
        
        self.is_processing = False
        self.last_output_csv: Optional[str] = None
        self.log_queue: queue.Queue = queue.Queue()
        
        self.processor = SCADADataProcessor(log_callback=self._queue_log)
        
        Theme.apply(self.root)
        self._build_ui()
        self.root.after(100, self._process_log_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _build_ui(self):
        # 1. Header Banner
        header_frame = tk.Frame(self.root, bg=Theme.BG_DARK, height=76)
        header_frame.pack(fill=tk.X, side=tk.TOP)
        header_frame.pack_propagate(False)
        
        title_lbl = ttk.Label(header_frame, text="SCADA-TraceLog", style="Header.TLabel")
        title_lbl.pack(anchor="w", padx=24, pady=(10, 0))
        
        subtitle_lbl = ttk.Label(
            header_frame,
            text="Automated SCADA Recipe Change Tracker & 256-Column Data Loss Guard",
            style="SubHeader.TLabel"
        )
        subtitle_lbl.pack(anchor="w", padx=24, pady=(0, 10))
        
        # 2. Main Body Container
        main_container = tk.Frame(self.root, bg=Theme.BG_LIGHT, padx=20, pady=16)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # 2.1 Section 1: Input Configuration
        mode_frame = ttk.LabelFrame(main_container, text="  1. Input Mode & Source  ", style="Section.TLabelframe", padding=14)
        mode_frame.pack(fill=tk.X, pady=(0, 14))
        
        rb_row = tk.Frame(mode_frame, bg=Theme.BG_CARD)
        rb_row.pack(fill=tk.X, pady=(0, 10))
        
        rb_single = ttk.Radiobutton(
            rb_row,
            text="Process Single File (.xls, .xlsx)",
            variable=self.mode_var,
            value="single",
            command=self._on_mode_change
        )
        rb_single.pack(side=tk.LEFT, padx=(0, 30))
        
        rb_folder = ttk.Radiobutton(
            rb_row,
            text="Process Entire Folder (Batch Processing)",
            variable=self.mode_var,
            value="folder",
            command=self._on_mode_change
        )
        rb_folder.pack(side=tk.LEFT)
        
        path_row = tk.Frame(mode_frame, bg=Theme.BG_CARD)
        path_row.pack(fill=tk.X)
        
        self.path_lbl = ttk.Label(path_row, text="File Path:", width=13)
        self.path_lbl.pack(side=tk.LEFT)
        
        self.path_entry = ttk.Entry(path_row, textvariable=self.path_var, font=(Theme.FONT_FAMILY, 11))
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        
        self.btn_browse = ttk.Button(path_row, text="Browse...", style="Secondary.TButton", command=self._browse_path)
        self.btn_browse.pack(side=tk.LEFT)
        
        # 2.2 Section 2: Conversion Options
        opt_frame = ttk.LabelFrame(main_container, text="  2. Conversion Settings  ", style="Section.TLabelframe", padding=14)
        opt_frame.pack(fill=tk.X, pady=(0, 14))
        
        param_row = tk.Frame(opt_frame, bg=Theme.BG_CARD)
        param_row.pack(fill=tk.X, pady=4)
        
        lbl_param_fmt = ttk.Label(param_row, text="Parameter Name Format:", width=22)
        lbl_param_fmt.pack(side=tk.LEFT)
        
        cb_param_fmt = ttk.Combobox(param_row, textvariable=self.param_format_var, state="readonly", width=34, font=(Theme.FONT_FAMILY, 10))
        cb_param_fmt["values"] = [
            "Description Only (inside [...])",
            "Full Original Tag Name",
            "Device Code + Description"
        ]
        cb_param_fmt.pack(side=tk.LEFT, padx=8)
        
        lbl_hint = ttk.Label(param_row, text="(e.g., 'OuterPeel_FILM_Peel_BLOW_TIME')", font=(Theme.FONT_FAMILY, 9, "italic"), foreground=Theme.TEXT_MUTED)
        lbl_hint.pack(side=tk.LEFT, padx=4)
        
        chk_row = tk.Frame(opt_frame, bg=Theme.BG_CARD)
        chk_row.pack(fill=tk.X, pady=(8, 4))
        
        chk_baseline = ttk.Checkbutton(
            chk_row,
            text="Include Initial Baseline (First record of each Recipe ID)",
            variable=self.include_baseline_var
        )
        chk_baseline.pack(side=tk.LEFT, padx=(0, 25))
        
        chk_open = ttk.Checkbutton(
            chk_row,
            text="Auto-open CSV output when completed",
            variable=self.auto_open_var
        )
        chk_open.pack(side=tk.LEFT)
        
        # 2.3 Section 3: Action Controls
        action_frame = tk.Frame(main_container, bg=Theme.BG_LIGHT)
        action_frame.pack(fill=tk.X, pady=(0, 14))
        
        self.btn_start = ttk.Button(
            action_frame,
            text="START CONVERSION",
            style="Primary.TButton",
            command=self._start_conversion
        )
        self.btn_start.pack(side=tk.LEFT, padx=(0, 12), ipady=3)
        
        self.btn_open_folder = ttk.Button(
            action_frame,
            text="Open Output Directory",
            style="Secondary.TButton",
            command=self._open_output_dir
        )
        self.btn_open_folder.pack(side=tk.LEFT, padx=(0, 12))
        
        self.btn_clear_log = ttk.Button(
            action_frame,
            text="Clear Console Log",
            style="Secondary.TButton",
            command=self._clear_logs
        )
        self.btn_clear_log.pack(side=tk.RIGHT)
        
        self.prog_bar = ttk.Progressbar(main_container, mode="indeterminate")
        self.prog_bar.pack(fill=tk.X, pady=(0, 14))
        
        # 2.4 Section 4: Console Output
        log_frame = ttk.LabelFrame(main_container, text="  3. Real-time Execution Console  ", style="Section.TLabelframe", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=(Theme.FONT_MONO, 11),
            bg=Theme.LOG_BG,
            fg=Theme.LOG_TEXT,
            insertbackground="#FFFFFF",
            borderwidth=0,
            relief="flat",
            height=10
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        self.log_text.tag_config("INFO", foreground=Theme.COLOR_INFO)
        self.log_text.tag_config("SUCCESS", foreground=Theme.COLOR_SUCCESS)
        self.log_text.tag_config("WARNING", foreground=Theme.COLOR_WARNING)
        self.log_text.tag_config("ERROR", foreground=Theme.COLOR_ERROR)
        self.log_text.tag_config("TIMESTAMP", foreground=Theme.COLOR_TIME)
        
        # 3. Status Bar (Bottom)
        status_bar = tk.Frame(self.root, bg=Theme.BORDER, height=30, padx=12)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        status_bar.pack_propagate(False)
        
        self.status_lbl = tk.Label(status_bar, text="Status: Ready", bg=Theme.BORDER,
                                   fg=Theme.TEXT_MAIN, font=(Theme.FONT_FAMILY, 10, "bold"))
        self.status_lbl.pack(side=tk.LEFT)
        
        guard_lbl = tk.Label(status_bar, text="256-Column Guard: Active | UTF-8 BOM Ready",
                             bg=Theme.BORDER, fg=Theme.TEXT_MUTED, font=(Theme.FONT_FAMILY, 9))
        guard_lbl.pack(side=tk.RIGHT)
        
        self._on_mode_change(reset_path=False)
        self._append_log("SCADA-TraceLog system initialized. Ready to process files.", "INFO")

    def _on_mode_change(self, reset_path: bool = True):
        mode = self.mode_var.get()
        if mode == "single":
            self.path_lbl.config(text="File Path:")
        else:
            self.path_lbl.config(text="Folder Path:")
        if reset_path:
            self.path_var.set("")

    def _browse_path(self):
        mode = self.mode_var.get()
        if mode == "single":
            chosen = filedialog.askopenfilename(
                title="Select SCADA Export File",
                filetypes=[
                    ("Excel Files (*.xls;*.xlsx)", "*.xls;*.xlsx"),
                    ("Legacy Excel 97-2003 (*.xls)", "*.xls"),
                    ("Modern Excel (*.xlsx)", "*.xlsx"),
                    ("All Files (*.*)", "*.*")
                ]
            )
        else:
            chosen = filedialog.askdirectory(title="Select Folder Containing SCADA Excel Files")
            
        if chosen:
            normalized = os.path.normpath(chosen)
            self.path_var.set(normalized)
            self._append_log(f"Selected path: {normalized}", "INFO")

    def _queue_log(self, message: str, level: str = "INFO"):
        self.log_queue.put((message, level))

    def _process_log_queue(self):
        while not self.log_queue.empty():
            msg, level = self.log_queue.get_nowait()
            self._append_log(msg, level)
        self.root.after(100, self._process_log_queue)

    def _append_log(self, text: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] ", "TIMESTAMP")
        self.log_text.insert(tk.END, f"[{level}] ", level)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _clear_logs(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _set_ui_processing_state(self, processing: bool):
        self.is_processing = processing
        state = tk.DISABLED if processing else tk.NORMAL
        
        self.btn_start.config(state=state)
        self.btn_browse.config(state=state)
        self.path_entry.config(state=state)
        
        if processing:
            self.prog_bar.start(10)
            self.status_lbl.config(text="Status: Processing...", fg=Theme.PRIMARY)
        else:
            self.prog_bar.stop()

    def _start_conversion(self):
        path = self.path_var.get().strip()
        if not path:
            messagebox.showwarning("Input Required", "Please select a valid file or folder path first!")
            return
            
        if not os.path.exists(path):
            messagebox.showerror("Path Not Found", f"The specified path does not exist:\n{path}")
            return
            
        mode = self.mode_var.get()
        if mode == "single" and not os.path.isfile(path):
            messagebox.showerror("Invalid Input", "Single File mode is active, but the selected path is not a file!")
            return
            
        if mode == "folder" and not os.path.isdir(path):
            messagebox.showerror("Invalid Input", "Folder mode is active, but the selected path is not a directory!")
            return
            
        include_baseline = self.include_baseline_var.get()
        raw_fmt = self.param_format_var.get()
        if "Description" in raw_fmt:
            name_mode = "description"
        elif "Original" in raw_fmt:
            name_mode = "original"
        else:
            name_mode = "both"
            
        parent_dir = os.path.dirname(path) if mode == "single" else path
        output_csv = os.path.join(parent_dir, self.output_filename_var.get().strip())
        
        self._set_ui_processing_state(True)
        worker = threading.Thread(
            target=self._run_conversion_worker,
            args=(mode, path, output_csv, name_mode, include_baseline),
            daemon=True
        )
        worker.start()

    def _run_conversion_worker(self, mode: str, input_path: str, output_csv: str,
                               name_mode: str, include_baseline: bool):
        try:
            self.processor.log(f"--- STARTING EXECUTION [{mode.upper()} MODE] ---", "INFO")
            self.processor.log(f"Baseline Mode: {'Included' if include_baseline else 'Strict Transitions Only'}", "INFO")
            
            if mode == "single":
                self.processor.process_single_file(
                    file_path=input_path,
                    output_csv_path=output_csv,
                    name_mode=name_mode,
                    include_baseline=include_baseline
                )
            else:
                self.processor.process_folder(
                    folder_path=input_path,
                    output_csv_path=output_csv,
                    name_mode=name_mode,
                    include_baseline=include_baseline
                )
                
            self.last_output_csv = output_csv
            self.root.after(0, self._on_conversion_success, output_csv)
            
        except Excel256ColumnLimitError as exc:
            self.processor.log(str(exc), "ERROR")
            self.root.after(0, self._on_256_column_error, exc)
            
        except Exception as exc:
            self.processor.log(f"Conversion failed: {exc}", "ERROR")
            self.root.after(0, self._on_general_error, str(exc))

    def _on_conversion_success(self, output_csv: str):
        self._set_ui_processing_state(False)
        self.status_lbl.config(text="Status: Completed!", fg="#16A34A")
        
        msg = f"Conversion finished successfully!\n\nChange Log CSV created at:\n{output_csv}"
        messagebox.showinfo("Conversion Completed", msg)
        
        if self.auto_open_var.get():
            open_file_in_os(output_csv)

    def _on_256_column_error(self, exc: Excel256ColumnLimitError):
        self._set_ui_processing_state(False)
        self.status_lbl.config(text="Status: Error - Data Loss Warning!", fg="#DC2626")
        messagebox.showerror("DATA LOSS WARNING", exc.message)

    def _on_general_error(self, err_text: str):
        self._set_ui_processing_state(False)
        self.status_lbl.config(text="Status: Error occurred", fg="#DC2626")
        messagebox.showerror("Conversion Error", f"An error occurred during conversion:\n\n{err_text}")

    def _open_output_dir(self):
        target_dir = None
        if self.last_output_csv and os.path.exists(os.path.dirname(self.last_output_csv)):
            target_dir = os.path.dirname(self.last_output_csv)
        else:
            path = self.path_var.get().strip()
            if path and os.path.exists(path):
                target_dir = path if os.path.isdir(path) else os.path.dirname(path)
                
        if target_dir:
            open_file_in_os(target_dir)
        else:
            messagebox.showinfo("Information", "No valid output directory found yet. Please run a conversion first.")

    def _on_closing(self):
        cfg = {
            "input_mode": self.mode_var.get(),
            "last_path": self.path_var.get().strip(),
            "include_baseline": self.include_baseline_var.get(),
            "param_format": self.param_format_var.get(),
            "auto_open": self.auto_open_var.get(),
            "output_filename": self.output_filename_var.get().strip()
        }
        ConfigManager.save_config(cfg)
        self.root.destroy()
