"""
Core recording engine: coordinates input listeners (mouse/keyboard),
screen capture, annotations, active window tracking, and step queues.
"""

import time
import threading
import platform
from datetime import datetime
from typing import Optional, List, Callable, Tuple, Set

from pynput import mouse, keyboard

from .models import Step, SessionMetadata
from .config import RecorderConfig
from .capture import ScreenCapture
from .annotator import annotate_screenshot
from .window_info import get_active_window_info


class RecordingEngine:
    """Manages active capture session and event hooks."""

    def __init__(self, config: Optional[RecorderConfig] = None):
        self.config = config or RecorderConfig()
        self.capture = ScreenCapture()
        
        self.state = "idle"  # "idle", "recording", "paused", "stopped"
        self.steps: List[Step] = []
        self.metadata: Optional[SessionMetadata] = None
        
        self._mouse_listener: Optional[mouse.Listener] = None
        self._keyboard_listener: Optional[keyboard.Listener] = None
        
        # Debouncing & double-click tracking
        self._last_click_time = 0.0
        self._last_click_pos = (0, 0)
        self._last_click_button = None
        
        # UI ignore bounds (x1, y1, x2, y2) so recorder doesn't record clicks on its own window
        self._ignore_bounds: List[Tuple[int, int, int, int]] = []
        
        # Callbacks for UI updates
        self.on_step_added: Optional[Callable[[Step], None]] = None
        self.on_state_changed: Optional[Callable[[str], None]] = None
        
        self._lock = threading.Lock()
        self._apps_used: Set[str] = set()

    def set_ignore_bounds(self, bounds: List[Tuple[int, int, int, int]]) -> None:
        """Set window regions where clicks should NOT trigger recordings."""
        with self._lock:
            valid_bounds = []
            for (x1, y1, x2, y2) in bounds:
                if x1 >= 0 and y1 >= 0 and x2 > x1 and y2 > y1:
                    valid_bounds.append((x1, y1, x2, y2))
            self._ignore_bounds = valid_bounds

    def is_in_ignored_region(self, x: int, y: int) -> bool:
        """Check if coordinates fall inside any ignored region (e.g. app toolbar)."""
        with self._lock:
            for (x1, y1, x2, y2) in self._ignore_bounds:
                if x1 <= x <= x2 and y1 <= y <= y2:
                    return True
        return False

    def start_recording(self, title: str = "Problem Steps Recording", description: str = "") -> None:
        """Start a new recording session."""
        if self.state == "recording":
            return

        self.steps.clear()
        self._apps_used.clear()
        
        session_id = datetime.now().strftime("rec_%Y%m%d_%H%M%S")
        self.metadata = SessionMetadata(
            session_id=session_id,
            title=title,
            description=description,
            start_time=datetime.now(),
            os_name=f"{platform.system()} {platform.release()}",
            screen_resolution=self.capture.get_screen_resolution_str(),
            monitors_info=self.capture.get_detailed_monitors_info()
        )
        
        self.state = "recording"
        self._start_listeners()
        
        if self.on_state_changed:
            self.on_state_changed(self.state)

    def pause_recording(self) -> None:
        """Pause active recording."""
        if self.state == "recording":
            self.state = "paused"
            if self.on_state_changed:
                self.on_state_changed(self.state)

    def resume_recording(self) -> None:
        """Resume active recording."""
        if self.state == "paused":
            self.state = "recording"
            if self.on_state_changed:
                self.on_state_changed(self.state)

    def stop_recording(self) -> None:
        """Stop and finalize active recording."""
        if self.state in ("recording", "paused"):
            self.state = "stopped"
            self._stop_listeners()
            if self.metadata:
                self.metadata.end_time = datetime.now()
                self.metadata.total_steps = len(self.steps)
                self.metadata.apps_used = sorted(list(self._apps_used))
            
            if self.on_state_changed:
                self.on_state_changed(self.state)

    def add_comment(self, comment_text: str, highlight_rect: Optional[Tuple[int, int, int, int]] = None) -> None:
        """Manually insert a user comment/note step with a screenshot."""
        if self.state in ("stopped", "idle"):
            return

        try:
            raw_img, mon_left, mon_top = self.capture.capture_full_screen()
            win_details = get_active_window_info()
            if win_details.process_name and win_details.process_name != "Unknown":
                self._apps_used.add(win_details.process_name)

            step_id = len(self.steps) + 1
            
            adj_rect = None
            if highlight_rect:
                rx1, ry1, rx2, ry2 = highlight_rect
                adj_rect = (rx1 - mon_left, ry1 - mon_top, rx2 - mon_left, ry2 - mon_top)

            annotated_img = annotate_screenshot(
                raw_img,
                step_id=step_id,
                highlight_rect=adj_rect,
                color_hex=self.config.highlight_color,
                style=self.config.highlight_style
            )
            
            thumb_img = self.capture.create_thumbnail(annotated_img)
            
            # Cursor pos if available
            try:
                m_ctrl = mouse.Controller()
                cur_x, cur_y = int(m_ctrl.position[0]), int(m_ctrl.position[1])
            except Exception:
                cur_x, cur_y = None, None

            step = Step(
                step_id=step_id,
                timestamp=datetime.now(),
                action_type="comment",
                description=f"User Comment: {comment_text}",
                window_title=win_details.title,
                process_name=win_details.process_name,
                pid=win_details.pid,
                ui_control=win_details.ui_control,
                window_rect=win_details.window_rect,
                relative_cursor=win_details.relative_cursor,
                cursor_x=cur_x,
                cursor_y=cur_y,
                highlight_rect=adj_rect,
                user_comment=comment_text,
                raw_image_bytes=self.capture.image_to_bytes(raw_img),
                annotated_image_bytes=self.capture.image_to_bytes(annotated_img),
                thumbnail_bytes=self.capture.image_to_bytes(thumb_img)
            )

            with self._lock:
                self.steps.append(step)

            print(f"[StepRecorder] Step #{step.step_id} (Comment): {comment_text}")

            if self.on_step_added:
                self.on_step_added(step)
        except Exception as e:
            print(f"[StepRecorder] Error adding comment: {e}")

    # Internal listeners and handlers
    def _start_listeners(self) -> None:
        """Initialize and start input event listeners."""
        if self.config.capture_clicks:
            self._mouse_listener = mouse.Listener(
                on_click=self._on_mouse_click
            )
            self._mouse_listener.daemon = True
            self._mouse_listener.start()

        if self.config.capture_keys:
            self._keyboard_listener = keyboard.Listener(
                on_press=self._on_key_press
            )
            self._keyboard_listener.daemon = True
            self._keyboard_listener.start()

    def _stop_listeners(self) -> None:
        """Stop input listeners."""
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
            self._mouse_listener = None

        if self._keyboard_listener:
            try:
                self._keyboard_listener.stop()
            except Exception:
                pass
            self._keyboard_listener = None

    def _on_mouse_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        """Triggered on mouse click event."""
        if not pressed:
            return
        if self.state != "recording":
            return
        if len(self.steps) >= self.config.max_steps:
            return

        if self.is_in_ignored_region(x, y):
            return

        now = time.time()
        is_double_click = False
        
        if (
            self.config.capture_double_clicks
            and button == self._last_click_button
            and (now - self._last_click_time) < 0.38
            and abs(x - self._last_click_pos[0]) < 8
            and abs(y - self._last_click_pos[1]) < 8
        ):
            is_double_click = True

        self._last_click_time = now
        self._last_click_pos = (x, y)
        self._last_click_button = button

        threading.Thread(
            target=self._process_click_event,
            args=(x, y, button, is_double_click),
            daemon=True
        ).start()

    def _process_click_event(self, x: int, y: int, button: mouse.Button, is_double_click: bool) -> None:
        """Process click in background thread: delay, capture, annotate, log."""
        try:
            if self.config.screenshot_delay_ms > 0:
                time.sleep(self.config.screenshot_delay_ms / 1000.0)

            # Capture full screen
            raw_img, mon_left, mon_top = self.capture.capture_full_screen()
            
            # Rich window and control inspection
            win_details = get_active_window_info(cursor_pos=(x, y))
            window_title = win_details.title
            process_name = win_details.process_name

            if process_name and process_name != "Unknown":
                self._apps_used.add(process_name)

            step_id = len(self.steps) + 1

            rel_x = x - mon_left
            rel_y = y - mon_top

            btn_name = "Left" if button == mouse.Button.left else ("Right" if button == mouse.Button.right else "Middle")
            action_type = "double_click" if is_double_click else (f"{btn_name.lower()}_click")
            action_verb = "Double Click" if is_double_click else f"{btn_name} Click"

            # Enriched action description (PSR style)
            if win_details.ui_control:
                desc = f"User {action_verb} on {win_details.ui_control} at ({x}, {y}) in [{window_title}]"
            else:
                desc = f"User {action_verb} at ({x}, {y}) on [{window_title}]"

            annotated_img = annotate_screenshot(
                raw_img,
                cursor_pos=(rel_x, rel_y),
                step_id=step_id,
                color_hex=self.config.highlight_color,
                radius=self.config.highlight_radius,
                style=self.config.highlight_style,
                show_badge=self.config.show_step_badge_on_screenshot
            )
            thumb_img = self.capture.create_thumbnail(annotated_img)

            step = Step(
                step_id=step_id,
                timestamp=datetime.now(),
                action_type=action_type,
                description=desc,
                window_title=window_title,
                process_name=process_name,
                pid=win_details.pid,
                ui_control=win_details.ui_control,
                window_rect=win_details.window_rect,
                relative_cursor=win_details.relative_cursor,
                cursor_x=x,
                cursor_y=y,
                raw_image_bytes=self.capture.image_to_bytes(raw_img),
                annotated_image_bytes=self.capture.image_to_bytes(annotated_img),
                thumbnail_bytes=self.capture.image_to_bytes(thumb_img)
            )

            with self._lock:
                self.steps.append(step)

            print(f"[StepRecorder] Step #{step_id}: {desc}")

            if self.on_step_added:
                self.on_step_added(step)
        except Exception as e:
            print(f"[StepRecorder] Error processing click: {e}")

    def _on_key_press(self, key) -> None:
        """Triggered on key press event."""
        if self.state != "recording":
            return
        if len(self.steps) >= self.config.max_steps:
            return

        key_name = ""
        is_special = False

        try:
            if isinstance(key, keyboard.Key):
                key_name = key.name
                is_special = True
            elif hasattr(key, "char") and key.char:
                key_name = key.char
        except Exception:
            return

        if self.config.special_keys_only and not is_special:
            return

        if key_name in ("ctrl_l", "ctrl_r", "shift", "shift_r", "alt_l", "alt_r", "cmd", "cmd_r"):
            return

        # Always capture current mouse cursor position so key presses also have coordinates
        try:
            m_ctrl = mouse.Controller()
            cur_x, cur_y = int(m_ctrl.position[0]), int(m_ctrl.position[1])
        except Exception:
            cur_x, cur_y = None, None

        threading.Thread(
            target=self._process_key_event,
            args=(key_name, cur_x, cur_y),
            daemon=True
        ).start()

    def _process_key_event(self, key_name: str, cur_x: Optional[int], cur_y: Optional[int]) -> None:
        """Process keyboard action step."""
        try:
            if self.config.screenshot_delay_ms > 0:
                time.sleep(self.config.screenshot_delay_ms / 1000.0)

            raw_img, mon_left, mon_top = self.capture.capture_full_screen()
            
            cursor_tuple = (cur_x, cur_y) if (cur_x is not None and cur_y is not None) else None
            win_details = get_active_window_info(cursor_pos=cursor_tuple)
            
            if win_details.process_name and win_details.process_name != "Unknown":
                self._apps_used.add(win_details.process_name)

            step_id = len(self.steps) + 1
            desc = f"User pressed [{key_name.upper()}] key in [{win_details.title}]"

            # Annotate with badge
            annotated_img = annotate_screenshot(
                raw_img,
                cursor_pos=(cur_x - mon_left, cur_y - mon_top) if cursor_tuple else None,
                step_id=step_id,
                color_hex=self.config.highlight_color,
                style=self.config.highlight_style
            )
            thumb_img = self.capture.create_thumbnail(annotated_img)

            step = Step(
                step_id=step_id,
                timestamp=datetime.now(),
                action_type="key_press",
                description=desc,
                window_title=win_details.title,
                process_name=win_details.process_name,
                pid=win_details.pid,
                ui_control=win_details.ui_control,
                window_rect=win_details.window_rect,
                relative_cursor=win_details.relative_cursor,
                cursor_x=cur_x,
                cursor_y=cur_y,
                raw_image_bytes=self.capture.image_to_bytes(raw_img),
                annotated_image_bytes=self.capture.image_to_bytes(annotated_img),
                thumbnail_bytes=self.capture.image_to_bytes(thumb_img)
            )

            with self._lock:
                self.steps.append(step)

            print(f"[StepRecorder] Step #{step_id}: {desc}")

            if self.on_step_added:
                self.on_step_added(step)
        except Exception as e:
            print(f"[StepRecorder] Error processing key: {e}")
