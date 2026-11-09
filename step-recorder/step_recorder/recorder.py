"""
Core recording engine: coordinates input listeners (mouse/keyboard),
screen capture, annotations, active window tracking, and step queues.
"""

import os
import sys
import time
import shutil
import tempfile
import threading
import queue
import platform
from datetime import datetime
from typing import Optional, List, Callable, Tuple, Set, Any
from PIL import Image

from pynput import mouse, keyboard

from .models import Step, SessionMetadata
from .config import RecorderConfig
from .capture import ScreenCapture
from .annotator import annotate_screenshot, has_ui_changed
from .window_info import get_active_window_info
from .i18n import t, I18nManager


def safe_print(msg: str) -> None:
    """Print to stdout safely handling any Windows console encoding limitations."""
    try:
        print(msg)
    except Exception:
        try:
            enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
            clean_msg = msg.encode(enc, errors="replace").decode(enc)
            print(clean_msg)
        except Exception:
            pass


class RecordingEngine:
    """Manages active capture session and event hooks."""

    def __init__(self, config: Optional[RecorderConfig] = None):
        self.config = config or RecorderConfig()
        I18nManager.set_language(getattr(self.config, "language", "vi"))
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
        self._click_counter = 0
        self._step_counter = 0

        # Sequential background worker queue for strictly monotonic FIFO step execution
        self._event_queue: queue.Queue = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_stop_event = threading.Event()

        # Smart Keystroke Aggregator
        self._text_buffer: List[str] = []
        self._text_buffer_lock = threading.Lock()
        self._text_flush_timer: Optional[threading.Timer] = None
        self._typing_win_details = None
        self._typing_cursor_pos: Optional[Tuple[int, int]] = None

        # Tiered Storage & L2 Disk Spooling
        self._spool_dir: Optional[str] = None

    def _reserve_step_id(self) -> Optional[int]:
        """Atomically reserve the next monotonic step_id if within max_steps."""
        with self._lock:
            if self.state not in ("recording", "stopped"):
                return None
            if self._step_counter >= self.config.max_steps:
                return None
            self._step_counter += 1
            return self._step_counter

    def _worker_loop(self) -> None:
        """Background worker processing events strictly sequentially in FIFO order."""
        while not self._worker_stop_event.is_set() or not self._event_queue.empty():
            try:
                task = self._event_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if callable(task):
                    task()
            except Exception as e:
                safe_print(f"[StepRecorder] Worker error processing step: {e}")
            finally:
                self._event_queue.task_done()

    def drain_queue(self, timeout: float = 10.0) -> None:
        """Wait until all queued capture processing tasks are completed."""
        start = time.time()
        while self._event_queue.unfinished_tasks > 0:
            if time.time() - start > timeout:
                safe_print("[StepRecorder] Warning: Timed out waiting for processing queue to drain.")
                break
            time.sleep(0.01)

    def _enqueue_or_execute(self, task_fn: Callable[[], Any], sync: bool = False) -> Any:
        """If worker thread is active, enqueue task; if sync requested, wait for queue. Otherwise run immediately."""
        if self._worker_thread and self._worker_thread.is_alive():
            self._event_queue.put(task_fn)
            if sync:
                self.drain_queue()
            return None
        else:
            return task_fn()

    def _commit_step(
        self,
        step_id: int,
        action_type: str,
        description: str,
        window_title: str,
        process_name: str,
        pid: Optional[int],
        ui_control: Optional[str],
        control_rect: Optional[Tuple[int, int, int, int]],
        window_rect: Optional[Tuple[int, int, int, int]],
        relative_cursor: Optional[Tuple[int, int]],
        cursor_x: Optional[int],
        cursor_y: Optional[int],
        raw_img: Image.Image,
        rel_cursor: Optional[Tuple[int, int]] = None,
        highlight_rect: Optional[Tuple[int, int, int, int]] = None,
        typed_text: Optional[str] = None,
        user_comment: Optional[str] = None,
        is_section_header: bool = False,
        section_title: Optional[str] = None,
        section_description: Optional[str] = None,
        log_tag: str = ""
    ) -> Step:
        """
        Unified step commit pipeline:
        Annotate screenshot, generate thumbnail, spool to disk/RAM,
        append final Step to self.steps, print log, and notify listeners.
        """
        if process_name and process_name != "Unknown":
            self._apps_used.add(process_name)

        # 1. Annotate
        annotated_img = annotate_screenshot(
            raw_img,
            cursor_pos=rel_cursor,
            step_id=step_id,
            highlight_rect=highlight_rect,
            color_hex=self.config.highlight_color,
            radius=self.config.highlight_radius,
            style=self.config.highlight_style,
            show_badge=self.config.show_step_badge_on_screenshot
        )

        # 2. Thumbnail
        thumb_img = self.capture.create_thumbnail(annotated_img)

        # 3. Spool images
        spool_raw, spool_ann, spool_thumb, raw_b, ann_b, thumb_b, mime = self._spool_step_images(
            step_id, raw_img, annotated_img, thumb_img
        )

        step = Step(
            step_id=step_id,
            timestamp=datetime.now(),
            action_type=action_type,
            description=description,
            window_title=window_title,
            process_name=process_name,
            pid=pid,
            ui_control=ui_control,
            control_rect=control_rect,
            window_rect=window_rect,
            relative_cursor=relative_cursor,
            cursor_x=cursor_x,
            cursor_y=cursor_y,
            highlight_rect=highlight_rect,
            typed_text=typed_text,
            user_comment=user_comment,
            is_section_header=is_section_header,
            section_title=section_title,
            section_description=section_description,
            spool_raw_path=spool_raw,
            spool_annotated_path=spool_ann,
            spool_thumb_path=spool_thumb,
            raw_image_bytes=raw_b,
            annotated_image_bytes=ann_b,
            thumbnail_bytes=thumb_b,
            image_mime_type=mime
        )

        with self._lock:
            self.steps.append(step)

        tag_str = f" ({log_tag})" if log_tag else ""
        safe_print(f"[StepRecorder] Step #{step_id}{tag_str}: {description}")

        if self.on_step_added:
            self.on_step_added(step)

        return step

    def _spool_step_images(
        self,
        step_id: int,
        raw_img: Image.Image,
        annotated_img: Image.Image,
        thumb_img: Image.Image
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[bytes], Optional[bytes], Optional[bytes], str]:
        """
        Handle Tiered Storage for step screenshots:
        - If disk spooling enabled: save raw & annotated to SSD temp files; step keeps only thumbnail bytes in RAM.
        - If disk spooling disabled: keep all bytes in RAM (legacy mode).
        Returns (spool_raw_path, spool_ann_path, spool_thumb_path, raw_bytes, ann_bytes, thumb_bytes, mime_type).
        """
        fmt = getattr(self.config, "image_format", "WEBP").upper()
        ext = "webp" if fmt == "WEBP" else "png"
        mime_type = "image/webp" if fmt == "WEBP" else "image/png"
        quality = getattr(self.config, "image_quality", 85)

        thumb_bytes = self.capture.image_to_bytes(thumb_img, format=fmt, quality=quality)

        if self._spool_dir and getattr(self.config, "enable_disk_spooling", True):
            raw_path = os.path.join(self._spool_dir, f"raw_step_{step_id:04d}.{ext}")
            ann_path = os.path.join(self._spool_dir, f"annotated_step_{step_id:04d}.{ext}")

            self.capture.save_image_to_file(raw_img, raw_path, format=fmt, quality=quality)
            self.capture.save_image_to_file(annotated_img, ann_path, format=fmt, quality=quality)

            return (raw_path, ann_path, None, None, None, thumb_bytes, mime_type)
        else:
            raw_bytes = self.capture.image_to_bytes(raw_img, format=fmt, quality=quality)
            ann_bytes = self.capture.image_to_bytes(annotated_img, format=fmt, quality=quality)
            return (None, None, None, raw_bytes, ann_bytes, thumb_bytes, mime_type)

    def cleanup_spool(self, force: bool = False) -> None:
        """Clean up temporary disk spool directory."""
        if self._spool_dir and os.path.exists(self._spool_dir):
            try:
                shutil.rmtree(self._spool_dir, ignore_errors=True)
                self._spool_dir = None
            except Exception as e:
                safe_print(f"[StepRecorder] Warning cleaning spool dir: {e}")

    def close(self) -> None:
        """Release capture driver, drain worker queue, and clean up temporary spool resources."""
        self._stop_listeners()
        self.flush_text_buffer()
        self.drain_queue(timeout=5.0)
        self._worker_stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
            self._worker_thread = None
        if hasattr(self, "capture") and self.capture:
            try:
                self.capture.close()
            except Exception:
                pass
        self.cleanup_spool()

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
        """Start a new recording session and start sequential background worker."""
        if self.state == "recording":
            return

        self.steps.clear()
        self._apps_used.clear()
        self._click_counter = 0
        self._step_counter = 0

        # Reset and start the sequential processing worker
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
                self._event_queue.task_done()
            except Exception:
                break

        self._worker_stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="StepRecorderWorker",
            daemon=True
        )
        self._worker_thread.start()

        session_id = datetime.now().strftime("rec_%Y%m%d_%H%M%S")
        if getattr(self.config, "enable_disk_spooling", True):
            base_dir = self.config.disk_spool_dir or tempfile.gettempdir()
            self._spool_dir = os.path.join(base_dir, f"steprec_spool_{session_id}_{os.getpid()}")
            os.makedirs(self._spool_dir, exist_ok=True)
        else:
            self._spool_dir = None

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
            self.flush_text_buffer()
            self.drain_queue(timeout=5.0)
            if self.on_state_changed:
                self.on_state_changed(self.state)

    def resume_recording(self) -> None:
        """Resume active recording."""
        if self.state == "paused":
            self.state = "recording"
            if self.on_state_changed:
                self.on_state_changed(self.state)

    def stop_recording(self) -> None:
        """Stop and finalize active recording, draining sequential worker queue."""
        if self.state in ("recording", "paused"):
            self.state = "stopped"
            self.flush_text_buffer()
            self._stop_listeners()

            # Ensure all queued frames are fully processed and saved before returning
            self.drain_queue(timeout=10.0)
            self._worker_stop_event.set()
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=2.0)
                self._worker_thread = None

            if self.metadata:
                self.metadata.end_time = datetime.now()
                self.metadata.total_steps = len(self.steps)
                self.metadata.apps_used = sorted(list(self._apps_used))
            
            if self.on_state_changed:
                self.on_state_changed(self.state)

    def add_comment(
        self,
        comment_text: str,
        highlight_rect: Optional[Tuple[int, int, int, int]] = None,
        is_section_header: bool = False,
        section_title: Optional[str] = None,
        section_description: Optional[str] = None
    ) -> None:
        """Manually insert a user comment/note step with a screenshot and optional section header."""
        if self.state in ("stopped", "idle"):
            return

        try:
            # Cursor pos if available
            try:
                m_ctrl = mouse.Controller()
                cur_x, cur_y = int(m_ctrl.position[0]), int(m_ctrl.position[1])
            except Exception:
                cur_x, cur_y = None, None

            win_details = get_active_window_info(cursor_pos=(cur_x, cur_y) if (cur_x is not None and cur_y is not None) else None)
            raw_img, mon_left, mon_top = self.capture.capture_for_event(
                cursor_pos=(cur_x, cur_y) if (cur_x is not None and cur_y is not None) else None,
                window_rect=win_details.window_rect,
                scope=getattr(self.config, "capture_scope", "cursor_monitor"),
                padding=getattr(self.config, "active_window_padding", 24)
            )

            step_id = self._reserve_step_id()
            if step_id is None:
                return
            
            adj_rect = None
            if highlight_rect:
                rx1, ry1, rx2, ry2 = highlight_rect
                adj_rect = (rx1 - mon_left, ry1 - mon_top, rx2 - mon_left, ry2 - mon_top)

            task = lambda: self._commit_step(
                step_id=step_id,
                action_type="comment",
                description=f"User Comment: {comment_text}",
                window_title=win_details.title,
                process_name=win_details.process_name,
                pid=win_details.pid,
                ui_control=win_details.ui_control,
                control_rect=getattr(win_details, "control_rect", None),
                window_rect=win_details.window_rect,
                relative_cursor=win_details.relative_cursor,
                cursor_x=cur_x,
                cursor_y=cur_y,
                raw_img=raw_img,
                highlight_rect=adj_rect,
                user_comment=comment_text,
                is_section_header=is_section_header,
                section_title=section_title,
                section_description=section_description,
                log_tag="Comment"
            )
            self._enqueue_or_execute(task, sync=True)
        except Exception as e:
            safe_print(f"[StepRecorder] Error adding comment: {e}")

    def flush_text_buffer(self, trigger_key: Optional[str] = None) -> None:
        """Flush any aggregated typing into a unified 'type_text' step."""
        with self._text_buffer_lock:
            if self._text_flush_timer:
                try:
                    self._text_flush_timer.cancel()
                except Exception:
                    pass
                self._text_flush_timer = None

            if not self._text_buffer:
                return

            typed_str = "".join(self._text_buffer).strip()
            self._text_buffer.clear()
            win_details = self._typing_win_details
            cursor_pos = self._typing_cursor_pos
            self._typing_win_details = None
            self._typing_cursor_pos = None

        if not typed_str:
            return

        if self.state not in ("recording", "stopped"):
            return

        threading.Thread(
            target=self._process_type_text_step,
            args=(typed_str, trigger_key, win_details, cursor_pos),
            daemon=True
        ).start()

    def _process_type_text_step(
        self,
        typed_str: str,
        trigger_key: Optional[str],
        win_details: Optional[Any],
        cursor_pos: Optional[Tuple[int, int]],
        sync: bool = False
    ) -> None:
        """Create and record an aggregated type_text step."""
        try:
            if not win_details:
                win_details = get_active_window_info(cursor_pos)

            is_pwd = getattr(win_details, "is_password", False)
            display_text = "••••••••" if is_pwd else typed_str

            step_id = self._reserve_step_id()
            if step_id is None:
                return

            raw_img, mon_left, mon_top = self.capture.capture_for_event(
                cursor_pos=cursor_pos,
                window_rect=win_details.window_rect,
                scope=getattr(self.config, "capture_scope", "cursor_monitor"),
                padding=getattr(self.config, "active_window_padding", 24)
            )

            control_label = win_details.ui_control
            key_suffix = f" ({trigger_key.upper()})" if trigger_key in ("enter", "tab") else ""
            if control_label:
                desc = t("action_type_text_control", text=display_text + key_suffix, control=control_label, window=win_details.title)
            else:
                desc = t("action_type_text", text=display_text + key_suffix, window=win_details.title)

            adj_rect = None
            ctrl_rect = getattr(win_details, "control_rect", None)
            if ctrl_rect:
                rx, ry, rw, rh = ctrl_rect
                adj_rect = (rx - mon_left, ry - mon_top, rx + rw - mon_left, ry + rh - mon_top)

            rel_cursor = (cursor_pos[0] - mon_left, cursor_pos[1] - mon_top) if cursor_pos else None

            task = lambda: self._commit_step(
                step_id=step_id,
                action_type="type_text",
                description=desc,
                window_title=win_details.title,
                process_name=win_details.process_name,
                pid=win_details.pid,
                ui_control=win_details.ui_control,
                control_rect=ctrl_rect,
                window_rect=win_details.window_rect,
                relative_cursor=win_details.relative_cursor,
                cursor_x=cursor_pos[0] if cursor_pos else None,
                cursor_y=cursor_pos[1] if cursor_pos else None,
                raw_img=raw_img,
                rel_cursor=rel_cursor,
                highlight_rect=adj_rect,
                typed_text=display_text,
                log_tag="Type Text"
            )
            self._enqueue_or_execute(task, sync=sync)
        except Exception as e:
            safe_print(f"[StepRecorder] Error processing type text: {e}")

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
        with self._lock:
            if self._step_counter >= self.config.max_steps:
                return

        if self.is_in_ignored_region(x, y):
            return

        # Flush any pending text before processing mouse click
        self.flush_text_buffer()

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

        self._click_counter += 1
        click_id = self._click_counter

        # Launch fast capture dispatcher (takes raw screen, sleeps 20ms, takes 2nd raw screen, enqueues to worker)
        threading.Thread(
            target=self._process_click_event,
            args=(x, y, button, is_double_click, click_id),
            kwargs={"sync": False},
            daemon=True
        ).start()

    def _process_click_event(
        self,
        x: int,
        y: int,
        button: mouse.Button,
        is_double_click: bool,
        click_id: int = 0,
        sync: bool = True
    ) -> None:
        """Fast capture dispatcher: immediate screen grab, delayed 2nd grab if enabled, then enqueue to sequential worker."""
        try:
            # 1. Single capture mode delay if dual capture is disabled
            if not getattr(self.config, "dual_capture_on_click", True):
                if self.config.screenshot_delay_ms > 0:
                    time.sleep(self.config.screenshot_delay_ms / 1000.0)

            # Rich window and control inspection at click moment
            win_details = get_active_window_info(cursor_pos=(x, y))
            window_title = win_details.title
            process_name = win_details.process_name

            # 2. First capture: Immediate screen at the moment of click
            raw_img, mon_left, mon_top = self.capture.capture_for_event(
                cursor_pos=(x, y),
                window_rect=win_details.window_rect,
                scope=getattr(self.config, "capture_scope", "cursor_monitor"),
                padding=getattr(self.config, "active_window_padding", 24)
            )

            # Atomically reserve step ID
            step_id = self._reserve_step_id()
            if step_id is None:
                return

            rel_x = x - mon_left
            rel_y = y - mon_top

            btn_name = "Left" if button == mouse.Button.left else ("Right" if button == mouse.Button.right else "Middle")
            action_type = "double_click" if is_double_click else (f"{btn_name.lower()}_click")

            # Localized enriched action description (PSR style)
            if is_double_click:
                if win_details.ui_control:
                    desc = t("action_double_click_control", control=win_details.ui_control, x=x, y=y, window=window_title)
                else:
                    desc = t("action_double_click", x=x, y=y, window=window_title)
            elif button == mouse.Button.right:
                if win_details.ui_control:
                    desc = t("action_right_click_control", control=win_details.ui_control, x=x, y=y, window=window_title)
                else:
                    desc = t("action_right_click", x=x, y=y, window=window_title)
            else:
                if win_details.ui_control:
                    desc = t("action_left_click_control", control=win_details.ui_control, x=x, y=y, window=window_title)
                else:
                    desc = t("action_left_click", x=x, y=y, window=window_title)

            task1 = lambda: self._commit_step(
                step_id=step_id,
                action_type=action_type,
                description=desc,
                window_title=window_title,
                process_name=process_name,
                pid=win_details.pid,
                ui_control=win_details.ui_control,
                control_rect=getattr(win_details, "control_rect", None),
                window_rect=win_details.window_rect,
                relative_cursor=win_details.relative_cursor,
                cursor_x=x,
                cursor_y=y,
                raw_img=raw_img,
                rel_cursor=(rel_x, rel_y),
                log_tag="Click 1/2 - Chụp ngay"
            )

            # If dual capture is disabled, enqueue task1 and return
            if not getattr(self.config, "dual_capture_on_click", True):
                self._enqueue_or_execute(task1, sync=sync)
                return
            else:
                self._enqueue_or_execute(task1, sync=False)

            # 3. Second capture: If dual_capture_on_click is enabled, wait delay_ms and capture result
            delay_ms = getattr(self.config, "second_capture_delay_ms", 20)
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)

            # Check if recording is still active after delay
            if self.state != "recording":
                if sync:
                    self.drain_queue()
                return

            # If user clicked again during the sleep, skip this intermediate delayed shot
            if click_id > 0 and self._click_counter > click_id:
                if sync:
                    self.drain_queue()
                return

            # Capture 2: Result screen after delay
            win_details2 = get_active_window_info(cursor_pos=(x, y))
            win2_title = win_details2.title
            proc2_name = win_details2.process_name

            raw_img2, mon_left2, mon_top2 = self.capture.capture_for_event(
                cursor_pos=(x, y),
                window_rect=win_details2.window_rect,
                scope=getattr(self.config, "capture_scope", "cursor_monitor"),
                padding=getattr(self.config, "active_window_padding", 24)
            )

            # Smart Auto-Detection: Check if UI actually changed
            if getattr(self.config, "dual_capture_smart_detect", True):
                if not has_ui_changed(
                    raw_img, raw_img2,
                    click_pos=(rel_x, rel_y),
                    win1=window_title,
                    win2=win2_title
                ):
                    safe_print(f"[StepRecorder] Giao diện không đổi -> Tự động giữ 1 ảnh cho Bước #{step_id}.")
                    if sync:
                        self.drain_queue()
                    return

            step_id2 = self._reserve_step_id()
            if step_id2 is None:
                if sync:
                    self.drain_queue()
                return

            if win2_title and win2_title != window_title:
                desc2 = t("action_click_result_switched", delay=delay_ms, window=win2_title)
            else:
                desc2 = t("action_click_result", delay=delay_ms, window=window_title)

            task2 = lambda: self._commit_step(
                step_id=step_id2,
                action_type="click_result",
                description=desc2,
                window_title=win2_title,
                process_name=proc2_name,
                pid=win_details2.pid,
                ui_control=win_details2.ui_control,
                control_rect=None,
                window_rect=win_details2.window_rect,
                relative_cursor=win_details2.relative_cursor,
                cursor_x=None,
                cursor_y=None,
                raw_img=raw_img2,
                rel_cursor=None,
                log_tag=f"Click 2/2 - Kết quả sau {delay_ms}ms"
            )
            self._enqueue_or_execute(task2, sync=sync)

        except Exception as e:
            safe_print(f"[StepRecorder] Error processing click: {e}")

    def _on_key_press(self, key) -> None:
        """Triggered on key press event."""
        if self.state != "recording":
            return
        with self._lock:
            if self._step_counter >= self.config.max_steps:
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

        if key_name in ("ctrl_l", "ctrl_r", "shift", "shift_r", "alt_l", "alt_r", "cmd", "cmd_r"):
            return

        # Always capture current mouse cursor position so key presses also have coordinates
        try:
            m_ctrl = mouse.Controller()
            cur_x, cur_y = int(m_ctrl.position[0]), int(m_ctrl.position[1])
        except Exception:
            cur_x, cur_y = None, None

        # Smart Keystroke Aggregator
        if getattr(self.config, "enable_keystroke_aggregator", True):
            # Normal printable characters or space
            if not is_special or key == keyboard.Key.space:
                char_to_add = " " if key == keyboard.Key.space else key_name
                with self._text_buffer_lock:
                    if self._text_flush_timer:
                        try:
                            self._text_flush_timer.cancel()
                        except Exception:
                            pass
                    if not self._text_buffer:
                        cursor_tuple = (cur_x, cur_y) if (cur_x is not None and cur_y is not None) else None
                        self._typing_win_details = get_active_window_info(cursor_pos=cursor_tuple)
                        self._typing_cursor_pos = cursor_tuple
                    self._text_buffer.append(char_to_add)
                    timeout_sec = getattr(self.config, "keystroke_flush_timeout_ms", 1200) / 1000.0
                    self._text_flush_timer = threading.Timer(timeout_sec, lambda: self.flush_text_buffer())
                    self._text_flush_timer.daemon = True
                    self._text_flush_timer.start()
                return

            # Backspace inside buffer
            if key == keyboard.Key.backspace:
                with self._text_buffer_lock:
                    if self._text_buffer:
                        self._text_buffer.pop()
                        if self._text_flush_timer:
                            try:
                                self._text_flush_timer.cancel()
                            except Exception:
                                pass
                        timeout_sec = getattr(self.config, "keystroke_flush_timeout_ms", 1200) / 1000.0
                        self._text_flush_timer = threading.Timer(timeout_sec, lambda: self.flush_text_buffer())
                        self._text_flush_timer.daemon = True
                        self._text_flush_timer.start()
                        return

            # Enter / Tab commits typed text with suffix
            if key in (keyboard.Key.enter, keyboard.Key.tab):
                with self._text_buffer_lock:
                    has_buffered = len(self._text_buffer) > 0
                if has_buffered:
                    self.flush_text_buffer(trigger_key=key_name)
                    return

        # Flush any remaining buffer before special standalone keys
        self.flush_text_buffer()

        if self.config.special_keys_only and not is_special:
            return

        threading.Thread(
            target=self._process_key_event,
            args=(key_name, cur_x, cur_y),
            kwargs={"sync": False},
            daemon=True
        ).start()

    def _process_key_event(self, key_name: str, cur_x: Optional[int], cur_y: Optional[int], sync: bool = True) -> None:
        """Process keyboard action step."""
        try:
            if self.config.screenshot_delay_ms > 0:
                time.sleep(self.config.screenshot_delay_ms / 1000.0)

            cursor_tuple = (cur_x, cur_y) if (cur_x is not None and cur_y is not None) else None
            win_details = get_active_window_info(cursor_pos=cursor_tuple)

            raw_img, mon_left, mon_top = self.capture.capture_for_event(
                cursor_pos=cursor_tuple,
                window_rect=win_details.window_rect,
                scope=getattr(self.config, "capture_scope", "cursor_monitor"),
                padding=getattr(self.config, "active_window_padding", 24)
            )

            step_id = self._reserve_step_id()
            if step_id is None:
                return

            desc = t("action_key_press", key=key_name.upper(), window=win_details.title)
            rel_cursor = (cur_x - mon_left, cur_y - mon_top) if cursor_tuple else None

            task = lambda: self._commit_step(
                step_id=step_id,
                action_type="key_press",
                description=desc,
                window_title=win_details.title,
                process_name=win_details.process_name,
                pid=win_details.pid,
                ui_control=win_details.ui_control,
                control_rect=getattr(win_details, "control_rect", None),
                window_rect=win_details.window_rect,
                relative_cursor=win_details.relative_cursor,
                cursor_x=cur_x,
                cursor_y=cur_y,
                raw_img=raw_img,
                rel_cursor=rel_cursor
            )
            self._enqueue_or_execute(task, sync=sync)
        except Exception as e:
            safe_print(f"[StepRecorder] Error processing key: {e}")
