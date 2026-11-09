"""
Settings configuration dialog for Step Recorder.
Provides comprehensive bilingual configuration: language, output folders,
indicator styles, limits, delays, and export preferences.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox
from pathlib import Path
from typing import Callable, Optional

from ..config import RecorderConfig
from ..window_info import exclude_window_from_capture
from ..i18n import t, I18nManager
from .icon_utils import apply_window_icon


class SettingsDialog:
    """Dialog to customize recording and export preferences."""

    def __init__(self, parent: tk.Tk, config: RecorderConfig, on_save: Optional[Callable[[RecorderConfig], None]] = None):
        self.parent = parent
        self.config = config
        self.on_save = on_save

        # Ensure active language matches config
        I18nManager.set_language(getattr(self.config, "language", "vi"))

        self.window = tk.Toplevel(parent)
        self.window.title(t("settings_win_title"))
        self.window.attributes("-topmost", True)
        self.window.transient(parent)
        self.window.configure(bg="#0f172a")

        apply_window_icon(self.window)

        self._build_ui()
        self._apply_geometry()

        self.window.after(50, lambda: exclude_window_from_capture(self.window))

        # Keyboard shortcuts
        self.window.bind("<Control-s>", lambda e: self._save())
        self.window.bind("<Escape>", lambda e: self.window.destroy())

        try:
            self.window.grab_set()
        except Exception:
            pass

    def _apply_geometry(self) -> None:
        """Calculate responsive geometry to prevent any button clipping on high-DPI displays."""
        self.window.update_idletasks()
        req_w = max(640, self.window.winfo_reqwidth() + 20)
        req_h = max(740, self.window.winfo_reqheight() + 20)

        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        
        final_h = min(req_h, int(screen_h * 0.92))
        final_w = min(req_w, int(screen_w * 0.92))
        
        pos_x = max(20, (screen_w - final_w) // 2)
        pos_y = max(20, (screen_h - final_h) // 2)

        self.window.geometry(f"{final_w}x{final_h}+{pos_x}+{pos_y}")
        self.window.minsize(580, 500)
        self.window.resizable(True, True)

    def _build_ui(self) -> None:
        # 1. FIXED BOTTOM ACTION BAR (Packed FIRST with side=BOTTOM to guarantee visibility)
        bottom_bar = tk.Frame(self.window, bg="#0b1120", padx=20, pady=14, relief=tk.RAISED, bd=1)
        bottom_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_msg_lbl = tk.Label(
            bottom_bar,
            text=t("hotkey_save_hint"),
            font=("Segoe UI", 8),
            bg="#0b1120",
            fg="#64748b"
        )
        self.status_msg_lbl.pack(side=tk.LEFT)

        cancel_btn = tk.Button(
            bottom_bar,
            text=t("btn_cancel_settings"),
            command=self.window.destroy,
            bg="#334155",
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=16,
            pady=6,
            font=("Segoe UI", 9),
            cursor="hand2"
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(10, 0))

        save_btn = tk.Button(
            bottom_bar,
            text=t("btn_save_settings"),
            command=self._save,
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=20,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2"
        )
        save_btn.pack(side=tk.RIGHT)

        # 2. SCROLLABLE CONTENT AREA
        self.canvas = tk.Canvas(self.window, bg="#0f172a", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.window, orient="vertical", command=self.canvas.yview)
        self.scroll_content = tk.Frame(self.canvas, bg="#0f172a", padx=20, pady=16)

        self.scroll_content.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        canvas_window = self.canvas.create_window((0, 0), window=self.scroll_content, anchor="nw")
        
        def _on_canvas_configure(event):
            self.canvas.itemconfig(canvas_window, width=event.width)

        self.canvas.bind("<Configure>", _on_canvas_configure)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):
            try:
                if getattr(self, "canvas", None) and self.canvas.winfo_exists():
                    delta = -1 if event.delta > 0 else 1
                    if event.num == 4:
                        delta = -1
                    elif event.num == 5:
                        delta = 1
                    self.canvas.yview_scroll(delta * 2, "units")
            except Exception:
                pass

        self.window.bind("<MouseWheel>", _on_mousewheel)
        self.window.bind("<Button-4>", _on_mousewheel)
        self.window.bind("<Button-5>", _on_mousewheel)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._render_sections()

    def _render_sections(self) -> None:
        """Render all settings cards into scroll_content."""
        for w in self.scroll_content.winfo_children():
            w.destroy()

        # --- Title ---
        header = tk.Label(
            self.scroll_content,
            text=t("settings_heading"),
            font=("Segoe UI", 12, "bold"),
            bg="#0f172a",
            fg="#f8fafc"
        )
        header.pack(anchor="w", pady=(0, 14))

        # --- SECTION 0: Language Selection ---
        sec_lang = self._create_card(self.scroll_content, t("sec_language"))
        lang_frame = tk.Frame(sec_lang, bg="#1e293b")
        lang_frame.pack(fill=tk.X, pady=6)

        self.lang_var = tk.StringVar(value=getattr(self.config, "language", "vi"))

        rb_vi = tk.Radiobutton(
            lang_frame,
            text="🇻🇳 " + t("lang_vietnamese"),
            value="vi",
            variable=self.lang_var,
            bg="#1e293b", fg="#f8fafc",
            selectcolor="#0f172a",
            activebackground="#1e293b",
            activeforeground="#38bdf8",
            font=("Segoe UI", 9, "bold"),
            command=self._on_language_switched
        )
        rb_vi.pack(side=tk.LEFT, padx=(0, 20))

        rb_en = tk.Radiobutton(
            lang_frame,
            text="🇬🇧 " + t("lang_english"),
            value="en",
            variable=self.lang_var,
            bg="#1e293b", fg="#f8fafc",
            selectcolor="#0f172a",
            activebackground="#1e293b",
            activeforeground="#38bdf8",
            font=("Segoe UI", 9, "bold"),
            command=self._on_language_switched
        )
        rb_en.pack(side=tk.LEFT)

        # --- SECTION 1: Output Folder ---
        sec1 = self._create_card(self.scroll_content, t("sec_output_dir"))
        
        dir_frame = tk.Frame(sec1, bg="#1e293b")
        dir_frame.pack(fill=tk.X, pady=6)

        self.dir_var = tk.StringVar(value=self.config.output_dir)
        dir_entry = tk.Entry(
            dir_frame,
            textvariable=self.dir_var,
            bg="#0f172a",
            fg="#f8fafc",
            insertbackground="#38bdf8",
            relief=tk.FLAT,
            font=("Segoe UI", 9)
        )
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 8))

        browse_btn = tk.Button(
            dir_frame,
            text=t("btn_browse_folder"),
            command=self._browse_dir,
            bg="#334155",
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=10,
            pady=4,
            font=("Segoe UI", 9),
            cursor="hand2"
        )
        browse_btn.pack(side=tk.RIGHT)

        # --- SECTION 2: Highlight & Visual Styling ---
        sec2 = self._create_card(self.scroll_content, t("sec_click_indicator"))
        
        vis_grid = tk.Frame(sec2, bg="#1e293b")
        vis_grid.pack(fill=tk.X, pady=6)
        vis_grid.columnconfigure(1, weight=1)

        # Style dropdown
        tk.Label(
            vis_grid, text=t("lbl_style"), font=("Segoe UI", 9),
            bg="#1e293b", fg="#cbd5e1"
        ).grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))

        self.style_var = tk.StringVar(value=self.config.highlight_style)
        style_cb = ttk.Combobox(
            vis_grid,
            textvariable=self.style_var,
            values=["ring", "glow", "crosshair", "solid"],
            state="readonly",
            width=16
        )
        style_cb.grid(row=0, column=1, sticky="w", pady=4)

        # Color picker
        tk.Label(
            vis_grid, text=t("lbl_color"), font=("Segoe UI", 9),
            bg="#1e293b", fg="#cbd5e1"
        ).grid(row=1, column=0, sticky="w", pady=4, padx=(0, 10))

        color_frame = tk.Frame(vis_grid, bg="#1e293b")
        color_frame.grid(row=1, column=1, sticky="w", pady=4)

        self.color_var = tk.StringVar(value=self.config.highlight_color)
        self.color_preview = tk.Label(
            color_frame,
            text="       ",
            bg=self.color_var.get(),
            relief=tk.SOLID,
            bd=1,
            width=5
        )
        self.color_preview.pack(side=tk.LEFT, padx=(0, 8))

        pick_btn = tk.Button(
            color_frame,
            text=t("btn_pick_color"),
            command=self._pick_color,
            bg="#334155",
            fg="#f8fafc",
            relief=tk.FLAT,
            padx=8,
            pady=2,
            font=("Segoe UI", 9),
            cursor="hand2"
        )
        pick_btn.pack(side=tk.LEFT)

        # Indicator Radius
        tk.Label(
            vis_grid, text=t("lbl_radius"), font=("Segoe UI", 9),
            bg="#1e293b", fg="#cbd5e1"
        ).grid(row=2, column=0, sticky="w", pady=4, padx=(0, 10))

        self.radius_var = tk.IntVar(value=self.config.highlight_radius)
        radius_spin = tk.Spinbox(
            vis_grid,
            from_=12,
            to=64,
            increment=4,
            textvariable=self.radius_var,
            width=8,
            bg="#0f172a",
            fg="#f8fafc",
            relief=tk.FLAT
        )
        radius_spin.grid(row=2, column=1, sticky="w", pady=4)

        # --- SECTION 3: Dedicated Dual Capture Card (Chụp 2 lần: Ngay khi click + Sau ms) ---
        sec_dual = self._create_card(self.scroll_content, t("sec_dual_capture"))

        self.dual_capture_var = tk.BooleanVar(value=getattr(self.config, "dual_capture_on_click", True))
        dual_chk = tk.Checkbutton(
            sec_dual,
            text=t("opt_dual_capture"),
            variable=self.dual_capture_var,
            bg="#1e293b",
            fg="#38bdf8",
            selectcolor="#0f172a",
            activebackground="#1e293b",
            activeforeground="#38bdf8",
            font=("Segoe UI", 9, "bold")
        )
        dual_chk.pack(anchor="w", pady=(2, 4))

        # Smart Auto-Detection checkbox
        self.smart_detect_var = tk.BooleanVar(value=getattr(self.config, "dual_capture_smart_detect", True))
        smart_chk = tk.Checkbutton(
            sec_dual,
            text=t("opt_smart_detect"),
            variable=self.smart_detect_var,
            bg="#1e293b",
            fg="#34d399",
            selectcolor="#0f172a",
            activebackground="#1e293b",
            activeforeground="#34d399",
            font=("Segoe UI", 8, "bold")
        )
        smart_chk.pack(anchor="w", padx=(18, 0), pady=(0, 6))

        # Explanatory bullet points
        hint_box = tk.Frame(sec_dual, bg="#0f172a", padx=10, pady=8, highlightbackground="#334155", highlightthickness=1)
        hint_box.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            hint_box, text=t("hint_smart_detect"),
            font=("Segoe UI", 8), bg="#0f172a", fg="#38bdf8", anchor="w"
        ).pack(fill=tk.X, pady=(0, 3))

        tk.Label(
            hint_box, text=t("hint_dual_capture_1"),
            font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8", anchor="w"
        ).pack(fill=tk.X, pady=(0, 2))

        tk.Label(
            hint_box, text=t("hint_dual_capture_2"),
            font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8", anchor="w"
        ).pack(fill=tk.X)

        # Delay input row + Quick preset buttons
        delay_row = tk.Frame(sec_dual, bg="#1e293b")
        delay_row.pack(fill=tk.X, pady=(2, 4))

        tk.Label(
            delay_row, text=t("lbl_second_delay_ms"), font=("Segoe UI", 9),
            bg="#1e293b", fg="#cbd5e1"
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.second_delay_var = tk.IntVar(value=getattr(self.config, "second_capture_delay_ms", 500))
        second_delay_spin = tk.Spinbox(
            delay_row,
            from_=50,
            to=3000,
            increment=50,
            textvariable=self.second_delay_var,
            width=8,
            bg="#0f172a",
            fg="#f8fafc",
            relief=tk.FLAT
        )
        second_delay_spin.pack(side=tk.LEFT, padx=(0, 10))

        # Preset shortcut buttons
        def _set_delay(val: int):
            self.second_delay_var.set(val)

        btn_fast = tk.Button(
            delay_row, text=t("btn_preset_fast"), font=("Segoe UI", 8, "bold"),
            command=lambda: _set_delay(200),
            bg="#0f172a", fg="#38bdf8", activebackground="#1e293b",
            relief=tk.FLAT, padx=8, pady=2, cursor="hand2"
        )
        btn_fast.pack(side=tk.LEFT, padx=(0, 4))

        btn_std = tk.Button(
            delay_row, text=t("btn_preset_std"), font=("Segoe UI", 8, "bold"),
            command=lambda: _set_delay(500),
            bg="#0f172a", fg="#10b981", activebackground="#1e293b",
            relief=tk.FLAT, padx=8, pady=2, cursor="hand2"
        )
        btn_std.pack(side=tk.LEFT, padx=(0, 4))

        btn_slow = tk.Button(
            delay_row, text=t("btn_preset_slow"), font=("Segoe UI", 8, "bold"),
            command=lambda: _set_delay(1000),
            bg="#0f172a", fg="#f59e0b", activebackground="#1e293b",
            relief=tk.FLAT, padx=8, pady=2, cursor="hand2"
        )
        btn_slow.pack(side=tk.LEFT)

        # --- SECTION 4: Recording Limits & General Delay ---
        sec3 = self._create_card(self.scroll_content, t("sec_limits_delays"))

        lim_grid = tk.Frame(sec3, bg="#1e293b")
        lim_grid.pack(fill=tk.X, pady=6)
        lim_grid.columnconfigure(1, weight=1)

        tk.Label(
            lim_grid, text=t("lbl_max_steps"), font=("Segoe UI", 9),
            bg="#1e293b", fg="#cbd5e1"
        ).grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))

        self.max_steps_var = tk.IntVar(value=self.config.max_steps)
        max_spin = tk.Spinbox(
            lim_grid,
            from_=10,
            to=1000,
            increment=25,
            textvariable=self.max_steps_var,
            width=8,
            bg="#0f172a",
            fg="#f8fafc",
            relief=tk.FLAT
        )
        max_spin.grid(row=0, column=1, sticky="w", pady=4)

        # Single capture delay ms
        tk.Label(
            lim_grid, text=t("lbl_single_delay_ms"), font=("Segoe UI", 9),
            bg="#1e293b", fg="#cbd5e1"
        ).grid(row=1, column=0, sticky="w", pady=4, padx=(0, 10))

        self.delay_var = tk.IntVar(value=self.config.screenshot_delay_ms)
        delay_spin = tk.Spinbox(
            lim_grid,
            from_=0,
            to=500,
            increment=20,
            textvariable=self.delay_var,
            width=8,
            bg="#0f172a",
            fg="#f8fafc",
            relief=tk.FLAT
        )
        delay_spin.grid(row=1, column=1, sticky="w", pady=4)

        # --- SECTION 4: Capture & Export Options ---
        sec4 = self._create_card(self.scroll_content, t("sec_options"))

        self.key_var = tk.BooleanVar(value=self.config.capture_keys)
        self._create_checkbox(sec4, t("opt_capture_keys"), self.key_var)

        # Smart Keystroke Aggregator & UIA
        self.aggregator_var = tk.BooleanVar(value=getattr(self.config, "enable_keystroke_aggregator", True))
        self._create_checkbox(sec4, t("opt_keystroke_aggregator"), self.aggregator_var)

        self.uia_var = tk.BooleanVar(value=getattr(self.config, "enable_ui_automation", True))
        self._create_checkbox(sec4, t("opt_enable_uia"), self.uia_var)

        self.double_click_var = tk.BooleanVar(value=self.config.capture_double_clicks)
        self._create_checkbox(sec4, t("opt_double_clicks"), self.double_click_var)

        # AI Copilot Card
        sec_ai = self._create_card(self.scroll_content, t("sec_ai_copilot"))
        self.ai_enable_var = tk.BooleanVar(value=getattr(self.config, "ai_enabled", True))
        self._create_checkbox(sec_ai, t("opt_enable_ai"), self.ai_enable_var)

        ai_row = tk.Frame(sec_ai, bg="#1e293b")
        ai_row.pack(fill=tk.X, pady=4)
        tk.Label(ai_row, text="AI Provider:", font=("Segoe UI", 9), bg="#1e293b", fg="#cbd5e1").pack(side=tk.LEFT, padx=(0, 8))
        self.ai_provider_var = tk.StringVar(value=getattr(self.config, "ai_provider", "smart_heuristic"))
        ai_combo = ttk.Combobox(
            ai_row,
            textvariable=self.ai_provider_var,
            values=["smart_heuristic", "gemini", "openai"],
            state="readonly",
            width=16
        )
        ai_combo.pack(side=tk.LEFT, padx=(0, 8))

        api_row = tk.Frame(sec_ai, bg="#1e293b")
        api_row.pack(fill=tk.X, pady=4)
        tk.Label(api_row, text="API Key (Optional):", font=("Segoe UI", 8), bg="#1e293b", fg="#94a3b8").pack(side=tk.LEFT, padx=(0, 6))
        self.ai_key_var = tk.StringVar(value=getattr(self.config, "ai_api_key", ""))
        api_entry = tk.Entry(api_row, textvariable=self.ai_key_var, show="•", bg="#0f172a", fg="#f8fafc", relief=tk.FLAT)
        api_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.badge_var = tk.BooleanVar(value=self.config.show_step_badge_on_screenshot)
        self._create_checkbox(sec4, t("opt_step_badge"), self.badge_var)

        self.dark_mode_var = tk.BooleanVar(value=self.config.dark_mode_report)
        self._create_checkbox(sec4, t("opt_dark_mode"), self.dark_mode_var)

        self.embed_var = tk.BooleanVar(value=self.config.embed_images_in_html)
        self._create_checkbox(sec4, t("opt_embed_images"), self.embed_var)

        self.zip_var = tk.BooleanVar(value=self.config.create_zip_package)
        self._create_checkbox(sec4, t("opt_zip_package"), self.zip_var)

        self.open_var = tk.BooleanVar(value=self.config.auto_open_report)
        self._create_checkbox(sec4, t("opt_auto_open"), self.open_var)

        self.exclude_var = tk.BooleanVar(value=getattr(self.config, "exclude_from_screen_capture", True))
        self._create_checkbox(sec4, t("opt_exclude_capture"), self.exclude_var)

        self.topmost_var = tk.BooleanVar(value=getattr(self.config, "always_on_top", True))
        self._create_checkbox(sec4, t("opt_always_on_top"), self.topmost_var)

        self.minimize_var = tk.BooleanVar(value=getattr(self.config, "auto_minimize_on_record", False))
        self._create_checkbox(sec4, t("opt_auto_minimize"), self.minimize_var)

    def _on_language_switched(self) -> None:
        """Called when user changes language radio button."""
        new_lang = self.lang_var.get()
        I18nManager.set_language(new_lang)
        self.config.language = new_lang
        self.window.title(t("settings_win_title"))
        self._render_sections()

    def _create_card(self, parent: tk.Frame, title: str) -> tk.Frame:
        """Create a rounded card-like section with title."""
        card = tk.Frame(parent, bg="#1e293b", padx=14, pady=10, relief=tk.FLAT)
        card.pack(fill=tk.X, pady=(0, 12))

        title_lbl = tk.Label(
            card,
            text=title,
            font=("Segoe UI", 9, "bold"),
            bg="#1e293b",
            fg="#38bdf8"
        )
        title_lbl.pack(anchor="w", pady=(0, 4))
        return card

    def _create_checkbox(self, parent: tk.Frame, text: str, var: tk.BooleanVar) -> tk.Checkbutton:
        """Helper to create standardized dark themed checkbutton."""
        cb = tk.Checkbutton(
            parent,
            text=text,
            variable=var,
            bg="#1e293b",
            fg="#f8fafc",
            selectcolor="#0f172a",
            activebackground="#1e293b",
            activeforeground="#38bdf8",
            font=("Segoe UI", 9)
        )
        cb.pack(anchor="w", pady=2)
        return cb

    def _browse_dir(self) -> None:
        """Browse directory safely with grab management."""
        current_dir = self.dir_var.get().strip()
        init_dir = current_dir if (current_dir and os.path.exists(current_dir)) else str(Path.home())
        
        try:
            self.window.grab_release()
        except Exception:
            pass

        chosen = filedialog.askdirectory(parent=self.window, initialdir=init_dir, title=t("choose_folder_title"))
        
        try:
            self.window.grab_set()
        except Exception:
            pass

        if chosen:
            self.dir_var.set(chosen)

    def _pick_color(self) -> None:
        """Pick highlight color with grab management."""
        try:
            self.window.grab_release()
        except Exception:
            pass

        chosen = colorchooser.askcolor(color=self.color_var.get(), parent=self.window, title=t("choose_color_title"))
        
        try:
            self.window.grab_set()
        except Exception:
            pass

        if chosen and chosen[1]:
            self.color_var.set(chosen[1])
            self.color_preview.configure(bg=chosen[1])

    def _save(self) -> None:
        """Validate, persist settings to JSON, update runtime, and close dialog."""
        try:
            # 0. Language
            self.config.language = self.lang_var.get()
            I18nManager.set_language(self.config.language)

            # 1. Output directory
            out_dir = self.dir_var.get().strip()
            if not out_dir:
                out_dir = str(Path.home() / "StepRecordings")
            p = Path(out_dir)
            p.mkdir(parents=True, exist_ok=True)
            self.config.output_dir = str(p)

            # 2. Styles
            self.config.highlight_style = self.style_var.get()
            self.config.highlight_color = self.color_var.get()

            # 3. Numeric values with robust fallback
            try:
                max_s = int(self.max_steps_var.get())
                if max_s > 0:
                    self.config.max_steps = max_s
            except Exception:
                pass

            try:
                delay = int(self.delay_var.get())
                if delay >= 0:
                    self.config.screenshot_delay_ms = delay
            except Exception:
                pass

            try:
                sec_delay = int(self.second_delay_var.get())
                if sec_delay > 0:
                    self.config.second_capture_delay_ms = sec_delay
            except Exception:
                pass

            try:
                radius = int(self.radius_var.get())
                if radius > 0:
                    self.config.highlight_radius = radius
            except Exception:
                pass

            # 4. Checkbox preferences
            self.config.dual_capture_on_click = bool(self.dual_capture_var.get())
            self.config.dual_capture_smart_detect = bool(self.smart_detect_var.get())
            self.config.capture_keys = bool(self.key_var.get())
            self.config.enable_keystroke_aggregator = bool(self.aggregator_var.get())
            self.config.enable_ui_automation = bool(self.uia_var.get())
            self.config.ai_enabled = bool(self.ai_enable_var.get())
            self.config.ai_provider = str(self.ai_provider_var.get())
            self.config.ai_api_key = str(self.ai_key_var.get()).strip()
            self.config.capture_double_clicks = bool(self.double_click_var.get())
            self.config.show_step_badge_on_screenshot = bool(self.badge_var.get())
            self.config.dark_mode_report = bool(self.dark_mode_var.get())
            self.config.embed_images_in_html = bool(self.embed_var.get())
            self.config.create_zip_package = bool(self.zip_var.get())
            self.config.auto_open_report = bool(self.open_var.get())
            self.config.exclude_from_screen_capture = bool(self.exclude_var.get())
            self.config.always_on_top = bool(self.topmost_var.get())
            self.config.auto_minimize_on_record = bool(self.minimize_var.get())

            # 5. Save to disk
            self.config.save()

            # 6. Notify callback
            if self.on_save:
                self.on_save(self.config)

            self.window.destroy()

        except Exception as e:
            messagebox.showerror(
                "Lỗi Lưu Cài Đặt / Error",
                f"Không thể lưu cấu hình cài đặt:\n\n{e}",
                parent=self.window
            )
