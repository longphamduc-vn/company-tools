"""
Global Hotkeys Manager for Python Step Recorder.
Enables hands-free recording control while interacting with external applications.
"""

import sys
import threading
from typing import Callable, Dict, Optional
from pynput import keyboard


class GlobalHotkeyManager:
    """Manages global hotkeys cross-platform with safe fallback."""

    def __init__(
        self,
        on_start_stop: Optional[Callable[[], None]] = None,
        on_pause_resume: Optional[Callable[[], None]] = None,
        on_comment: Optional[Callable[[], None]] = None,
        on_mark_section: Optional[Callable[[], None]] = None,
        on_open_review: Optional[Callable[[], None]] = None,
        on_open_saved: Optional[Callable[[], None]] = None,
    ):
        self.on_start_stop = on_start_stop
        self.on_pause_resume = on_pause_resume
        self.on_comment = on_comment
        self.on_mark_section = on_mark_section
        self.on_open_review = on_open_review
        self.on_open_saved = on_open_saved

        self._hotkeys_listener: Optional[keyboard.GlobalHotKeys] = None
        self._running = False

    def start(self) -> bool:
        """Start global hotkeys listener in background thread."""
        if self._running:
            return True

        mapping: Dict[str, Callable[[], None]] = {}

        if self.on_start_stop:
            mapping['<ctrl>+<alt>+s'] = self.on_start_stop
            mapping['<f7>'] = self.on_start_stop

        if self.on_pause_resume:
            mapping['<ctrl>+<alt>+p'] = self.on_pause_resume
            mapping['<f8>'] = self.on_pause_resume

        if self.on_comment:
            mapping['<ctrl>+<alt>+c'] = self.on_comment
            mapping['<f9>'] = self.on_comment

        if self.on_mark_section:
            mapping['<ctrl>+<alt>+m'] = self.on_mark_section
            mapping['<f10>'] = self.on_mark_section

        if self.on_open_review:
            mapping['<ctrl>+<alt>+r'] = self.on_open_review
            mapping['<f11>'] = self.on_open_review

        if self.on_open_saved:
            mapping['<ctrl>+<alt>+o'] = self.on_open_saved

        try:
            self._hotkeys_listener = keyboard.GlobalHotKeys(mapping)
            self._hotkeys_listener.daemon = True
            self._hotkeys_listener.start()
            self._running = True
            return True
        except Exception as e:
            # On some platforms (e.g. headless Linux without X11 or Wayland without access),
            # GlobalHotKeys may raise an exception. We fail gracefully.
            self._hotkeys_listener = None
            self._running = False
            return False

    def stop(self) -> None:
        """Stop global hotkeys listener safely."""
        if self._hotkeys_listener:
            try:
                self._hotkeys_listener.stop()
            except Exception:
                pass
            self._hotkeys_listener = None
        self._running = False

