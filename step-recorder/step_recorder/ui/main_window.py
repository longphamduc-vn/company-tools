"""
Main floating toolbar application for Step Recorder.
Provides modern, compact controls: Start, Pause, Resume, Add Comment, Review & Edit, Stop & Save.
"""

import os
import sys
import time
import json
import traceback
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
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
from ..models import Step, SessionMetadata
from ..recorder import RecordingEngine
from ..exporter import ReportExporter
from ..window_info import exclude_window_from_capture
from ..i18n import t, I18nManager
from ..hotkeys import GlobalHotkeyManager
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
        I18nManager.set_language(getattr(self.config, "language", "vi"))
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
        self._init_hotkeys()

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
        self.root.title(t("app_title"))
        self.root.attributes("-topmost", getattr(self.config, "always_on_top", True))
        self.root.configure(bg="#0f172a")

        # Exclude this toolbar from screen captures using Windows WDA_EXCLUDEFROMCAPTURE API
        self.root.after(80, self._apply_capture_exclusion)
        self.root.bind("<Map>", lambda e: self.root.after(40, self._apply_capture_exclusion))

    def _apply_capture_exclusion(self) -> None:
        if getattr(self.config, "exclude_from_screen_capture", True):
            exclude_window_from_capture(self.root)

    def _toggle_always_on_top(self) -> None:
        """Toggle floating toolbar between Always-On-Top and normal desktop window."""
        new_val = not getattr(self.config, "always_on_top", True)
        self.config.always_on_top = new_val
        self.root.attributes("-topmost", new_val)
        if new_val:
            self.pin_btn.configure(text=t("pin_on_top"), fg="#38bdf8")
        else:
            self.pin_btn.configure(text=t("pin_normal"), fg="#94a3b8")
        try:
            self.config.save()
        except Exception:
            pass

    def _toggle_language(self) -> None:
        """Toggle UI between Vietnamese and English."""
        curr = I18nManager.get_language()
        new_lang = "en" if curr == "vi" else "vi"
        I18nManager.set_language(new_lang)
        self.config.language = new_lang
        self.engine.config.language = new_lang
        self.exporter.config.language = new_lang
        try:
            self.config.save()
        except Exception:
            pass
        self._update_ui_language()

    def _update_ui_language(self) -> None:
        """Update all text in toolbar to match active language."""
        self.root.title(t("app_title"))
        curr_lang = I18nManager.get_language()
        self.lang_btn.configure(text="🇻🇳 VI" if curr_lang == "vi" else "🇬🇧 EN")
        self.pin_btn.configure(text=t("pin_on_top") if getattr(self.config, "always_on_top", True) else t("pin_normal"))

        # State label
        if self.engine.state == "recording":
            self.status_lbl.configure(text=t("status_recording"))
        elif self.engine.state == "paused":
            self.status_lbl.configure(text=t("status_paused"))
        elif self.engine.state == "stopped":
            self.status_lbl.configure(text=t("status_stopped"))
        else:
            self.status_lbl.configure(text=t("status_ready"))

        self.steps_lbl.configure(text=t("steps_count", count=len(self.engine.steps), max=self.config.max_steps))
        self.start_btn.configure(text=t("btn_start"))
        self.pause_btn.configure(text=t("btn_resume") if self.engine.state == "paused" else t("btn_pause"))
        self.comment_btn.configure(text=t("btn_comment"))
        self.review_btn.configure(text=t("btn_review"))
        self.open_btn.configure(text=t("btn_open"))
        self.stop_btn.configure(text=t("btn_stop"))
        self.settings_btn.configure(text=t("btn_settings"))
        self.hotkey_hint_lbl.configure(text=t("hotkey_bar_hint"))

    def _build_ui(self) -> None:
        container = tk.Frame(self.root, bg="#0f172a", padx=12, pady=10)
        container.pack(fill=tk.BOTH, expand=True)

        # Top row: 3 distinct columns (Left: status, Center: steps count, Right: lang, pin toggle & live timer)
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
            text=t("status_ready"),
            font=("Segoe UI", 9, "bold"),
            bg="#0f172a",
            fg="#cbd5e1"
        )
        self.status_lbl.pack(side=tk.LEFT)

        # Center: Steps counter
        self.steps_lbl = tk.Label(
            top_row,
            text=t("steps_count", count=0, max=self.config.max_steps),
            font=("Segoe UI", 9),
            bg="#0f172a",
            fg="#94a3b8"
        )
        self.steps_lbl.grid(row=0, column=1)

        # Right: Language toggle, Pin toggle & Live timer
        right_box = tk.Frame(top_row, bg="#0f172a")
        right_box.grid(row=0, column=2, sticky="e")

        self.lang_btn = tk.Button(
            right_box,
            text="🇻🇳 VI" if I18nManager.get_language() == "vi" else "🇬🇧 EN",
            command=self._toggle_language,
            bg="#1e293b",
            fg="#38bdf8",
            activebackground="#334155",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=5,
            pady=0,
            cursor="hand2"
        )
        self.lang_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.pin_btn = tk.Button(
            right_box,
            text=t("pin_on_top") if getattr(self.config, "always_on_top", True) else t("pin_normal"),
            command=self._toggle_always_on_top,
            bg="#1e293b",
            fg="#38bdf8" if getattr(self.config, "always_on_top", True) else "#94a3b8",
            activebackground="#334155",
            relief=tk.FLAT,
            font=("Segoe UI", 8),
            padx=5,
            pady=0,
            cursor="hand2"
        )
        self.pin_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.timer_lbl = tk.Label(
            right_box,
            text="00:00",
            font=("Consolas", 11, "bold"),
            bg="#0f172a",
            fg="#38bdf8"
        )
        self.timer_lbl.pack(side=tk.LEFT)

        # Bottom row: 7 responsive buttons sharing width equally via grid
        btn_row = tk.Frame(container, bg="#0f172a")
        btn_row.pack(fill=tk.X, expand=True)
        for col in range(7):
            btn_row.columnconfigure(col, weight=1)

        # Start Record Button
        self.start_btn = tk.Button(
            btn_row,
            text=t("btn_start"),
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
            text=t("btn_pause"),
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
            text=t("btn_comment"),
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
            text=t("btn_review"),
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

        # Open Saved Session Button
        self.open_btn = tk.Button(
            btn_row,
            text=t("btn_open"),
            command=self._cmd_open_saved_session,
            bg="#1e293b",
            fg="#38bdf8",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            pady=5,
            cursor="hand2"
        )
        self.open_btn.grid(row=0, column=4, sticky="ew", padx=2)

        # Stop & Save Button
        self.stop_btn = tk.Button(
            btn_row,
            text=t("btn_stop"),
            command=self._cmd_stop,
            state=tk.DISABLED,
            bg="#334155",
            fg="#94a3b8",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            pady=5,
            cursor="hand2"
        )
        self.stop_btn.grid(row=0, column=5, sticky="ew", padx=2)

        # Settings Button
        self.settings_btn = tk.Button(
            btn_row,
            text=t("btn_settings"),
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
        self.settings_btn.grid(row=0, column=6, sticky="ew", padx=2)

        # Global Hotkey bar hint
        hint_frame = tk.Frame(container, bg="#0f172a")
        hint_frame.pack(fill=tk.X, pady=(6, 0))
        self.hotkey_hint_lbl = tk.Label(
            hint_frame,
            text=t("hotkey_bar_hint"),
            font=("Segoe UI", 7),
            bg="#0f172a",
            fg="#64748b"
        )
        self.hotkey_hint_lbl.pack(anchor="center")

        # Auto-compute natural size to ensure NO button or label is ever cut off
        self.root.update_idletasks()
        req_w = max(720, self.root.winfo_reqwidth() + 30)
        req_h = max(115, self.root.winfo_reqheight() + 10)
        self.root.geometry(f"{req_w}x{req_h}+100+100")
        self.root.minsize(600, 105)
        self.root.resizable(True, False)

    def _bind_events(self) -> None:
        """Bind position tracking to ignore toolbar region from clicks and local hotkeys."""
        self.root.bind("<Configure>", self._update_ignore_bounds)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Local window hotkeys for convenience
        self.root.bind("<F7>", lambda e: self._hotkey_toggle_start_stop())
        self.root.bind("<F8>", lambda e: self._cmd_toggle_pause())
        self.root.bind("<F9>", lambda e: self._cmd_add_comment())
        self.root.bind("<F10>", lambda e: self._hotkey_add_section())
        self.root.bind("<F11>", lambda e: self._cmd_open_editor())
        self.root.bind("<Control-o>", lambda e: self._cmd_open_saved_session())

    def _init_hotkeys(self) -> None:
        """Start background global hotkeys listener."""
        self.hotkey_mgr = GlobalHotkeyManager(
            on_start_stop=lambda: self.root.after(0, self._hotkey_toggle_start_stop),
            on_pause_resume=lambda: self.root.after(0, self._cmd_toggle_pause),
            on_comment=lambda: self.root.after(0, self._cmd_add_comment),
            on_mark_section=lambda: self.root.after(0, self._hotkey_add_section),
            on_open_review=lambda: self.root.after(0, self._cmd_open_editor),
            on_open_saved=lambda: self.root.after(0, self._cmd_open_saved_session),
        )
        self.hotkey_mgr.start()

    def _hotkey_toggle_start_stop(self) -> None:
        if self.engine.state in ("idle", "stopped"):
            self._cmd_start()
        elif self.engine.state in ("recording", "paused"):
            self._cmd_stop()

    def _hotkey_add_section(self) -> None:
        self.root.deiconify()
        dlg = CommentDialog(self.root, on_submit=self._on_comment_submitted)
        dlg.is_section_var.set(True)
        dlg._on_section_chk_toggled()

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

        if getattr(self.config, "auto_minimize_on_record", False):
            self.root.after(200, self.root.iconify)

    def _cmd_toggle_pause(self) -> None:
        self.root.deiconify()
        if self.engine.state == "recording":
            self.engine.pause_recording()
        elif self.engine.state == "paused":
            self.engine.resume_recording()

    def _cmd_add_comment(self) -> None:
        self.root.deiconify()
        CommentDialog(self.root, on_submit=self._on_comment_submitted)

    def _on_comment_submitted(
        self,
        comment_text: str,
        rect,
        is_section: bool = False,
        section_title: Optional[str] = None
    ) -> None:
        self.engine.add_comment(
            comment_text,
            rect,
            is_section_header=is_section,
            section_title=section_title
        )

    def _cmd_open_editor(self) -> None:
        """Open the interactive Step Reviewer & Editor."""
        self.root.deiconify()
        if not self.engine.steps:
            messagebox.showinfo(t("btn_review"), t("no_steps_to_review"))
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

    def _cmd_open_saved_session(self, filepath: Optional[str] = None) -> None:
        """Open a previously saved recording session for review and editing."""
        self.root.deiconify()
        if not filepath:
            filepath = filedialog.askopenfilename(
                title=t("open_session_title"),
                filetypes=[("Session JSON", "session.json"), ("JSON Files", "*.json"), ("All Files", "*.*")],
                parent=self.root
            )
        if not filepath or not os.path.exists(filepath):
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            sess_info = data.get("session", {})
            metadata = SessionMetadata(
                session_id=sess_info.get("id", "saved_session"),
                title=sess_info.get("title", "Saved Session"),
                description=sess_info.get("description", ""),
                os_name=sess_info.get("os", ""),
                screen_resolution=sess_info.get("screen_resolution", ""),
                total_steps=sess_info.get("total_steps", 0),
                apps_used=sess_info.get("apps_used", [])
            )

            steps_data = data.get("steps", [])
            loaded_steps = [Step.from_dict(s) for s in steps_data]
            base_folder = Path(filepath).parent

            for s in loaded_steps:
                target_p = None
                if s.annotated_image_path:
                    p = Path(s.annotated_image_path)
                    if not p.is_absolute():
                        p = base_folder / p
                    if p.exists():
                        target_p = p
                if not target_p and s.raw_image_path:
                    p = Path(s.raw_image_path)
                    if not p.is_absolute():
                        p = base_folder / p
                    if p.exists():
                        target_p = p

                if target_p and target_p.exists():
                    s.annotated_image_path = str(target_p)
                    with open(target_p, "rb") as imf:
                        s.annotated_image_bytes = imf.read()
                        if not s.raw_image_bytes:
                            s.raw_image_bytes = s.annotated_image_bytes

            StepEditorWindow(
                parent=self.root,
                steps=loaded_steps,
                metadata=metadata,
                config=self.config,
                exporter=self.exporter,
                on_export_complete=self._on_export_completed
            )
        except Exception as e:
            messagebox.showerror(t("editor_title"), f"Error opening session: {e}", parent=self.root)

    def _cmd_stop(self) -> None:
        self.root.deiconify()
        self._timer_running = False
        self.engine.stop_recording()

        if not self.engine.steps:
            messagebox.showinfo(t("app_title"), t("no_steps_recorded"))
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
        I18nManager.set_language(getattr(new_config, "language", "vi"))
        self._update_ui_language()
        self.status_lbl.configure(text=t("settings_saved"), fg="#34d399")
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
            self.steps_lbl.configure(text=t("steps_count", count=count, max=self.config.max_steps))
            
            # Enable Review button as soon as at least 1 step is recorded
            self.review_btn.configure(state=tk.NORMAL, bg="#0284c7", fg="#ffffff")

            self.status_lbl.configure(text=t("step_recorded_flash", id=step.step_id), fg="#38bdf8")
            
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
                self.status_lbl.configure(text=t("status_recording"), fg="#f8fafc")
            except Exception:
                pass

    def _on_state_changed(self, state: str) -> None:
        """Callback from engine when state changes."""
        self.root.after(0, self._ui_state_update, state)

    def _ui_state_update(self, state: str) -> None:
        try:
            if state == "recording":
                self.status_dot.configure(fg="#ef4444")
                self.status_lbl.configure(text=t("status_recording"), fg="#f8fafc")
                self.start_btn.configure(state=tk.DISABLED, bg="#1e293b", fg="#64748b")
                self.pause_btn.configure(
                    state=tk.NORMAL, text=t("btn_pause"), bg="#d97706", fg="#ffffff"
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
                self.status_lbl.configure(text=t("status_paused"), fg="#fbbf24")
                self.pause_btn.configure(
                    text=t("btn_resume"), bg="#059669", fg="#ffffff"
                )
            elif state in ("stopped", "idle"):
                self._reset_ui()
        except Exception as e:
            log_error(f"Error updating UI state: {e}")

    def _reset_ui(self) -> None:
        try:
            self.status_dot.configure(fg="#94a3b8")
            self.status_lbl.configure(text=t("status_ready"), fg="#cbd5e1")
            self.timer_lbl.configure(text="00:00")
            self.steps_lbl.configure(text=t("steps_count", count=0, max=self.config.max_steps))

            self.start_btn.configure(state=tk.NORMAL, text=t("btn_start"), bg="#059669", fg="#ffffff")
            self.pause_btn.configure(state=tk.DISABLED, text=t("btn_pause"), bg="#334155", fg="#94a3b8")
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
        if hasattr(self, "hotkey_mgr"):
            try:
                self.hotkey_mgr.stop()
            except Exception:
                pass
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
