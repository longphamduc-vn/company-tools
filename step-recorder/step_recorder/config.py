"""
Configuration management for Step Recorder.
"""

import os
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, List


DEFAULT_CONFIG_PATH = Path.home() / ".step_recorder" / "config.json"


@dataclass
class RecorderConfig:
    """User configuration settings."""
    output_dir: str = str(Path.home() / "StepRecordings")
    max_steps: int = 200  # Default 200 (unlike PSR which defaults to 25)
    screenshot_delay_ms: int = 60  # ms delay after click before capturing screen (single-capture mode)
    
    # Dual capture on click (Chụp 2 lần: ngay sau khi click + sau độ trễ ms)
    dual_capture_on_click: bool = True
    second_capture_delay_ms: int = 500  # ms delay before capturing second result screenshot
    dual_capture_smart_detect: bool = True  # Auto-detect: only capture 2nd shot if UI genuinely changed
    
    # Event capture triggers
    capture_clicks: bool = True
    capture_double_clicks: bool = True
    capture_keys: bool = True
    special_keys_only: bool = True  # If True, records only Enter, Tab, Esc, shortcuts, etc.
    enable_keystroke_aggregator: bool = True  # Automatically aggregate consecutive typing into input fields
    keystroke_flush_timeout_ms: int = 1200  # Debounce delay (ms) to flush typing buffer into 1 step
    enable_ui_automation: bool = True  # Deep control inspection via Windows UI Automation (UIA)
    
    # AI Copilot & SOP Intelligence
    ai_enabled: bool = True  # AI Copilot enabled for SOP polishing and summaries
    ai_provider: str = "smart_heuristic"  # "smart_heuristic" (offline/zero-cost), "gemini", "openai"
    ai_api_key: str = ""
    ai_api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    ai_model: str = "gemini-2.5-flash"
    ai_auto_chaptering: bool = True
    ai_generate_summary: bool = True
    
    # Interactive Guide Player
    enable_interactive_player: bool = True
    
    # Highlight & visual styling
    highlight_style: str = "ring"  # "ring", "glow", "crosshair", "solid"
    highlight_color: str = "#FF3366"  # Vibrant coral/red
    highlight_radius: int = 24
    highlight_border_width: int = 3
    show_step_badge_on_screenshot: bool = True
    
    # Output and export
    export_format: str = "html"  # "html", "markdown", "zip", "all"
    embed_images_in_html: bool = True  # Self-contained single file HTML
    save_raw_screenshots: bool = True
    create_zip_package: bool = True
    auto_open_report: bool = True
    dark_mode_report: bool = True
    
    # Window behavior and capture exclusion
    exclude_from_screen_capture: bool = True  # Automatically exclude toolbar from screenshots using Windows API
    always_on_top: bool = True  # Keep toolbar always on top of other windows
    auto_minimize_on_record: bool = False  # Minimize toolbar to taskbar when recording begins

    # Language & Localization
    language: str = "vi"  # "vi" (Tiếng Việt) or "en" (English)

    # Hotkeys
    hotkey_start_pause: str = "<F8>"
    hotkey_stop: str = "<F10>"
    hotkey_comment: str = "<F9>"

    def save(self, filepath: Optional[str] = None) -> None:
        """Save settings to JSON file."""
        target = Path(filepath) if filepath else DEFAULT_CONFIG_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write to temporary file first then replace to avoid corruption
        temp_target = target.with_suffix(".tmp")
        with open(temp_target, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)
        temp_target.replace(target)

    @classmethod
    def load(cls, filepath: Optional[str] = None) -> "RecorderConfig":
        """Load settings from JSON file or return default."""
        target = Path(filepath) if filepath else DEFAULT_CONFIG_PATH
        if target.exists():
            try:
                with open(target, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Filter only fields known to RecorderConfig
                    valid_keys = {f for f in cls.__dataclass_fields__}
                    filtered = {k: v for k, v in data.items() if k in valid_keys}
                    return cls(**filtered)
            except Exception:
                pass
        return cls()

