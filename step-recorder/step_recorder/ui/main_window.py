"""
Main floating toolbar application for Step Recorder.
Provides modern, compact controls: Start, Pause, Resume, Add Comment, Review & Edit, Stop & Save.
"""

import os
import sys
import time
import traceback
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional

# Enable standard DPI awareness on Windows compatible with Tkinter
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from ..config import RecorderConfig
from ..recorder import RecordingEngine
from ..exporter import ReportExporter
from .comment_dialog import CommentDialog
from .settings_dialog import SettingsDialog
from .step_editor import StepEditorWindow


def log_error(err_msg: str) -> None:
    """Log error message with timestamp to local error log file."""
    try:
        log_file = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent / "step_recorder_error.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {err_msg}\n")
    except Exception:
        pass


class MainWindow:
    """Floating control bar for the Step Recorder."""

    def __init__(self, root: Optional[tk.Tk] = None):
        self.root = root or tk.Tk()
        self.config = RecorderConfig.load()
        self.engine = RecordingEngine(self.config)
        self.exporter = ReportExporter(self.config)

        self._start_time = 0.0
        self._timer_running = False
        self._flash_job = None

        # Setup global exception handler for Tkinter callbacks
        self.root.report_callback_exception = self._handle_callback_exception

        self._init_window()
        self._build_ui()
        self._bind_events()

        # Connect engine callbacks to UI
        self.engine.on_step_added = self._on_step_added
        self.engine.on_state_changed = self._on_state_changed

    def _handle_callback_exception(self, exc_type, exc_value, exc_traceback):
        """Catch any uncaught exception inside Tkinter events."""
        err_details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        print(f"[StepRecorder Error]\n{err_details}", file=sys.stderr)
        log_error(err_details)
        try:
            messagebox.showerror(
                "Step Recorder Error",
                f"An error occurred in the application:\n\n{exc_value}\n\n(Details saved to step_recorder_error.log)"
            )
        except Exception:
            pass

    def _init_window(self) -> None:
        self.root.title("Python Step Recorder")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#0f172a")

    def _build_ui(self) -> None:
        container = tk.Frame(self.root, bg="#0f172a", padx=12, pady=10)
        container.pack(fill=tk.BOTH, expand=True)

        # Top row: 3 distinct columns (Left: status, Center: steps count, Right: live timer)
        top_row = tk.Frame(container, bg="#0f172a")
        top_row.pack(fill=tk.X, pady=(0, 8))
        top_row.columnconfigure(0, weight=1)
        top_row.columnconfigure(1, weight=1)
        top_row.columnconfigure(2, weight=1)

        # Left: Status Dot & Text
        status_frame = tk.Frame(top_row, bg="#0f172a")
        status_frame.grid(row=0, column=0, sticky="w")

        self.status_dot = tk.Label(
            status_frame,
            text="●",
            font=("Segoe UI", 11),
            bg="#0f172a",
            fg="#94a3b8"
        )
        self.status_dot.pack(side=tk.LEFT, padx=(0, 4))

        self.status_lbl = tk.Label(
            status_frame,
            text="Ready",
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#cbd5e1"
        )
        self.status_lbl.pack(side=tk.LEFT)

        # Center: Steps counter
        self.steps_lbl = tk.Label(
            top_row,
            text=f"Steps: 0 / {self.config.max_steps}",
            font=("Segoe UI", 9),
            bg="#0f172a",
            fg="#94a3b8"
        )
        self.steps_lbl.grid(row=0, column=1)

        # Right: Live timer
        self.timer_lbl = tk.Label(
            top_row,
            text="00:00",
            font=("Consolas", 11, "bold"),
            bg="#0f172a",
            fg="#38bdf8"
        )
        self.timer_lbl.grid(row=0, column=2, sticky="e")

        # Bottom row: 6 responsive buttons sharing width equally via grid
        btn_row = tk.Frame(container, bg="#0f172a")
        btn_row.pack(fill=tk.X, expand=True)
        for col in range(6):
            btn_row.columnconfigure(col, weight=1)

        # Start Record Button
        self.start_btn = tk.Button(
            btn_row,
            text="⏺ Start",
            command=self._cmd_start,
            bg="#059669",
            fg="#ffffff",
            activebackground="#10b981",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            pady=5,
            cursor="hand2"
        )
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=2)

        # Pause / Resume Button
        self.pause_btn = tk.Button(
            btn_row,
            text="⏸ Pause",
            command=self._cmd_toggle_pause,
            state=tk.DISABLED,
            bg="#334155",
            fg="#94a3b8",
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            pady=5,
            cursor="hand2"
        )
        self.pause_btn.grid(row=0, column=1, sticky="ew", padx=2)

        # Add Comment Button
        self.comment_btn = tk.Button(
            btn_row,
            text="💬 Comment",
            command=self._cmd_add_comment,
            state=tk.DISABLED,
            bg="#334155",
            fg="#94a3b8",
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            pady=5,
            cursor="hand2"
        )
        self.comment_btn.grid(row=0, column=2, sticky="ew", padx=2)

        # Review & Edit Steps Button
        self.review_btn = tk.Button(
            btn_row,
            text="📝 Review",
            command=self._cmd_open_editor,
            state=tk.DISABLED,
            bg="#334155",
            fg="#94a3b8",
            activebackground="#0284c7",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            pady=5,
            cursor="hand2"
        )
        self.review_btn.grid(row=0, column=3, sticky="ew", padx=2)

        # Stop & Save Button
        self.stop_btn = tk.Button(
            btn_row,
            text="⏹ Stop",
            command=self._cmd_stop,
            state=tk.DISABLED,
            bg="#334155",
            fg="#94a3b8",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            pady=5,
            cursor="hand2"
        )
        self.stop_btn.grid(row=0, column=4, sticky="ew", padx=2)

        # Settings Button
        self.settings_btn = tk.Button(
            btn_row,
            text="⚙ Settings",
            command=self._cmd_open_settings,
            bg="#1e293b",
            fg="#cbd5e1",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            pady=5,
            cursor="hand2"
        )
        self.settings_btn.grid(row=0, column=5, sticky="ew", padx=2)

        # Auto-compute natural size to ensure NO button or label is ever cut off
        self.root.update_idletasks()
        req_w = max(620, self.root.winfo_reqwidth() + 30)
        req_h = max(100, self.root.winfo_reqheight() + 10)
        self.root.geometry(f"{req_w}x{req_h}+100+100")
        self.root.minsize(540, 95)
        self.root.resizable(True, False)

    def _bind_events(self) -> None:
        """Bind position tracking to ignore toolbar region from clicks."""
        self.root.bind("<Configure>", self._update_ignore_bounds)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _update_ignore_bounds(self, event=None) -> None:
        """Update window bounding box to ignore toolbar clicks in recorder engine."""
        if event is not None and event.widget != self.root:
            return
        try:
            x = self.root.winfo_rootx()
            y = self.root.winfo_rooty()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if x >= 0 and y >= 0 and w > 20 and h > 20:
                self.engine.set_ignore_bounds([(x, y, x + w, y + h)])
        except Exception:
            pass

    # Button Command Handlers
    def _cmd_start(self) -> None:
        self.engine.start_recording()
        self._start_time = time.time()
        self._timer_running = True
        self._tick_timer()

    def _cmd_toggle_pause(self) -> None:
        if self.engine.state == "recording":
            self.engine.pause_recording()
        elif self.engine.state == "paused":
            self.engine.resume_recording()

    def _cmd_add_comment(self) -> None:
        CommentDialog(self.root, on_submit=self._on_comment_submitted)

    def _on_comment_submitted(self, comment_text: str, rect) -> None:
        self.engine.add_comment(comment_text, rect)

    def _cmd_open_editor(self) -> None:
        """Open the interactive Step Reviewer & Editor."""
        if not self.engine.steps:
            messagebox.showinfo("Review Steps", "Chưa có bước nào được ghi lại để chỉnh sửa.")
            return

        StepEditorWindow(
            parent=self.root,
            steps=self.engine.steps,
            metadata=self.engine.metadata,
            config=self.config,
            exporter=self.exporter,
            on_export_complete=self._on_export_completed
        )

    def _on_export_completed(self, results: dict) -> None:
        """Called when export finishes from StepEditor."""
        self._reset_ui()

    def _cmd_stop(self) -> None:
        self._timer_running = False
        self.engine.stop_recording()

        if not self.engine.steps:
            messagebox.showinfo("Step Recorder", "No steps were recorded.")
            self._reset_ui()
            return

        # Automatically open the Step Review & Editor so user can verify, prune, and edit before saving
        self._cmd_open_editor()

    def _cmd_open_settings(self) -> None:
        SettingsDialog(self.root, self.config, on_save=self._on_settings_saved)

    def _on_settings_saved(self, new_config: RecorderConfig) -> None:
        self.config = new_config
        self.engine.config = new_config
        self.exporter.config = new_config
        self.steps_lbl.configure(text=f"Steps: {len(self.engine.steps)} / {self.config.max_steps}")
        self.status_lbl.configure(text="Settings Saved! ✓", fg="#34d399")
        if self._flash_job:
            try:
                self.root.after_cancel(self._flash_job)
            except Exception:
                pass
        self._flash_job = self.root.after(2500, self._revert_status_lbl)

    def _on_step_added(self, step) -> None:
        """Callback from recorder when a new step is recorded."""
        self.root.after(0, self._ui_step_update, step)

    def _ui_step_update(self, step) -> None:
        try:
            count = len(self.engine.steps)
            self.steps_lbl.configure(text=f"Steps: {count} / {self.config.max_steps}")
            
            # Enable Review button as soon as at least 1 step is recorded
            self.review_btn.configure(state=tk.NORMAL, bg="#0284c7", fg="#ffffff")

            verb = "Clicked" if "click" in step.action_type else ("Key" if "key" in step.action_type else "Note")
            self.status_lbl.configure(text=f"Step #{step.step_id} {verb}! 📸", fg="#38bdf8")
            
            if self._flash_job:
                try:
                    self.root.after_cancel(self._flash_job)
                except Exception:
                    pass
                self._flash_job = None

            if self.engine.state == "recording":
                self._flash_job = self.root.after(1400, self._revert_status_lbl)
        except Exception as e:
            log_error(f"Error updating UI on step added: {e}")

    def _revert_status_lbl(self) -> None:
        self._flash_job = None
        if self.engine.state == "recording":
            try:
                self.status_lbl.configure(text="Recording...", fg="#f8fafc")
            except Exception:
                pass

    def _on_state_changed(self, state: str) -> None:
        """Callback from engine when state changes."""
        self.root.after(0, self._ui_state_update, state)

    def _ui_state_update(self, state: str) -> None:
        try:
            if state == "recording":
                self.status_dot.configure(fg="#ef4444")
                self.status_lbl.configure(text="Recording...", fg="#f8fafc")
                self.start_btn.configure(state=tk.DISABLED, bg="#1e293b", fg="#64748b")
                self.pause_btn.configure(
                    state=tk.NORMAL, text="⏸ Pause", bg="#d97706", fg="#ffffff"
                )
                self.comment_btn.configure(
                    state=tk.NORMAL, bg="#0284c7", fg="#ffffff"
                )
                self.stop_btn.configure(
                    state=tk.NORMAL, bg="#dc2626", fg="#ffffff"
                )
                if self.engine.steps:
                    self.review_btn.configure(state=tk.NORMAL, bg="#0284c7", fg="#ffffff")
            elif state == "paused":
                self.status_dot.configure(fg="#f59e0b")
                self.status_lbl.configure(text="Paused", fg="#f59e0b")
                self.pause_btn.configure(
                    text="▶ Resume", bg="#059669", fg="#ffffff"
                )
            elif state in ("stopped", "idle"):
                self._reset_ui()
        except Exception as e:
            log_error(f"Error updating UI state: {e}")

    def _reset_ui(self) -> None:
        try:
            self.status_dot.configure(fg="#94a3b8")
            self.status_lbl.configure(text="Ready", fg="#cbd5e1")
            self.timer_lbl.configure(text="00:00")
            self.steps_lbl.configure(text=f"Steps: 0 / {self.config.max_steps}")

            self.start_btn.configure(state=tk.NORMAL, text="⏺ Start", bg="#059669", fg="#ffffff")
            self.pause_btn.configure(state=tk.DISABLED, text="⏸ Pause", bg="#334155", fg="#94a3b8")
            self.comment_btn.configure(state=tk.DISABLED, bg="#334155", fg="#94a3b8")
            self.review_btn.configure(state=tk.DISABLED, bg="#334155", fg="#94a3b8")
            self.stop_btn.configure(state=tk.DISABLED, bg="#334155", fg="#94a3b8")
        except Exception:
            pass

    def _tick_timer(self) -> None:
        """Periodic timer loop."""
        if self._timer_running and self.engine.state == "recording":
            elapsed = int(time.time() - self._start_time)
            m, s = divmod(elapsed, 60)
            h, m = divmod(m, 60)
            try:
                if h > 0:
                    self.timer_lbl.configure(text=f"{h:02d}:{m:02d}:{s:02d}")
                else:
                    self.timer_lbl.configure(text=f"{m:02d}:{s:02d}")
            except Exception:
                pass

        if self._timer_running:
            self.root.after(1000, self._tick_timer)

    def _on_closing(self) -> None:
        if self.engine.state in ("recording", "paused"):
            if messagebox.askyesno("Exit Step Recorder", "Recording is in progress. Stop and exit?"):
                self.engine.stop_recording()
                self.root.destroy()
        else:
            self.root.destroy()

    def run(self) -> None:
        """Start the GUI main loop."""
        self._update_ignore_bounds()
        self.root.mainloop()
