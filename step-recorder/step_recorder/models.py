"""
Data models for recording steps and session state.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import os
import base64


@dataclass
class Step:
    """Represents a single recorded user action / step."""
    step_id: int
    timestamp: datetime
    action_type: str  # "left_click", "right_click", "double_click", "key_press", "comment"
    description: str
    window_title: str = "Unknown Window"
    process_name: str = "Unknown Process"
    pid: Optional[int] = None
    ui_control: Optional[str] = None
    window_rect: Optional[Tuple[int, int, int, int]] = None  # (left, top, width, height)
    relative_cursor: Optional[Tuple[int, int]] = None        # (rel_x, rel_y) within window
    cursor_x: Optional[int] = None
    cursor_y: Optional[int] = None
    highlight_rect: Optional[Tuple[int, int, int, int]] = None
    user_comment: Optional[str] = None
    typed_text: Optional[str] = None  # Aggregated typed text for "type_text" action
    control_rect: Optional[Tuple[int, int, int, int]] = None  # (left, top, width, height) of targeted UI element
    
    # Drag & Drop trajectory coordinates
    drag_start: Optional[Tuple[int, int]] = None  # (x, y) start point of drag
    drag_end: Optional[Tuple[int, int]] = None    # (x, y) release point of drag

    # SOP Section / Chapter markers
    is_section_header: bool = False
    section_title: Optional[str] = None
    section_description: Optional[str] = None

    # Conditional / Branching Workflow (Yes/No Decision Point)
    is_decision_point: bool = False
    condition_question: Optional[str] = None
    yes_branch_text: Optional[str] = None
    yes_next_step: Optional[int] = None
    no_branch_text: Optional[str] = None
    no_next_step: Optional[int] = None
    
    # Image file paths
    raw_image_path: Optional[str] = None
    annotated_image_path: Optional[str] = None
    thumbnail_path: Optional[str] = None

    # In-memory image bytes (for direct HTML embedding and re-annotation)
    raw_image_bytes: Optional[bytes] = None
    annotated_image_bytes: Optional[bytes] = None
    thumbnail_bytes: Optional[bytes] = None
    image_before_bytes: Optional[bytes] = None
    image_after_bytes: Optional[bytes] = None
    focus_crop_bytes: Optional[bytes] = None

    # L2 Disk Spooling paths (Tiered storage)
    spool_raw_path: Optional[str] = None
    spool_annotated_path: Optional[str] = None
    spool_thumb_path: Optional[str] = None
    spool_before_path: Optional[str] = None
    spool_focus_crop_path: Optional[str] = None
    image_mime_type: str = "image/png"

    def get_annotated_bytes(self) -> Optional[bytes]:
        """Get annotated image bytes, reading lazily from disk spool if evicted from RAM."""
        if self.annotated_image_bytes is not None:
            return self.annotated_image_bytes
        if self.spool_annotated_path and os.path.exists(self.spool_annotated_path):
            try:
                with open(self.spool_annotated_path, "rb") as f:
                    return f.read()
            except Exception:
                pass
        if self.annotated_image_path and os.path.exists(self.annotated_image_path):
            try:
                with open(self.annotated_image_path, "rb") as f:
                    return f.read()
            except Exception:
                pass
        return None

    def get_raw_bytes(self) -> Optional[bytes]:
        """Get raw unannotated image bytes, reading lazily from disk spool if evicted from RAM."""
        if self.raw_image_bytes is not None:
            return self.raw_image_bytes
        if self.spool_raw_path and os.path.exists(self.spool_raw_path):
            try:
                with open(self.spool_raw_path, "rb") as f:
                    return f.read()
            except Exception:
                pass
        if self.raw_image_path and os.path.exists(self.raw_image_path):
            try:
                with open(self.raw_image_path, "rb") as f:
                    return f.read()
            except Exception:
                pass
        return None

    def get_thumbnail_bytes(self) -> Optional[bytes]:
        """Get thumbnail bytes."""
        if self.thumbnail_bytes is not None:
            return self.thumbnail_bytes
        if self.spool_thumb_path and os.path.exists(self.spool_thumb_path):
            try:
                with open(self.spool_thumb_path, "rb") as f:
                    return f.read()
            except Exception:
                pass
        if self.thumbnail_path and os.path.exists(self.thumbnail_path):
            try:
                with open(self.thumbnail_path, "rb") as f:
                    return f.read()
            except Exception:
                pass
        return None

    def evict_raw_from_ram(self) -> None:
        """Free raw and annotated full-size bytes from RAM to keep footprint minimal."""
        self.raw_image_bytes = None
        self.annotated_image_bytes = None
        self.image_before_bytes = None

    def get_focus_crop_bytes(self) -> Optional[bytes]:
        """Get focus zoom cropped image bytes."""
        if self.focus_crop_bytes is not None:
            return self.focus_crop_bytes
        if self.spool_focus_crop_path and os.path.exists(self.spool_focus_crop_path):
            try:
                with open(self.spool_focus_crop_path, "rb") as f:
                    return f.read()
            except Exception:
                pass
        return None

    def get_before_bytes(self) -> Optional[bytes]:
        """Get pre-action (before) image bytes if available."""
        if self.image_before_bytes is not None:
            return self.image_before_bytes
        if self.spool_before_path and os.path.exists(self.spool_before_path):
            try:
                with open(self.spool_before_path, "rb") as f:
                    return f.read()
            except Exception:
                pass
        return None

    @property
    def image_filename(self) -> str:
        """Standardized image filename for this step."""
        ext = "webp" if ("webp" in self.image_mime_type or (self.spool_annotated_path and self.spool_annotated_path.endswith(".webp"))) else "png"
        return f"step_{self.step_id:03d}_{self.action_type}.{ext}"

    @property
    def formatted_time(self) -> str:
        """Formatted timestamp string."""
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    @property
    def time_str(self) -> str:
        """Short time string HH:MM:SS."""
        return self.timestamp.strftime("%H:%M:%S")

    @property
    def badge_class(self) -> str:
        """CSS badge class based on action type."""
        mapping = {
            "left_click": "badge-primary",
            "right_click": "badge-secondary",
            "double_click": "badge-accent",
            "drag_and_drop": "badge-warning",
            "key_press": "badge-warning",
            "type_text": "badge-accent",
            "comment": "badge-info",
            "click_result": "badge-success",
            "hover": "badge-info",
            "scroll": "badge-secondary",
            "timer_capture": "badge-default",
        }
        return mapping.get(self.action_type, "badge-default")

    @property
    def action_icon(self) -> str:
        """Unicode or SVG icon for action type."""
        mapping = {
            "left_click": "👆",
            "right_click": "👉",
            "double_click": "✌️",
            "drag_and_drop": "↔️",
            "key_press": "⌨️",
            "type_text": "⌨️",
            "comment": "💬",
            "click_result": "⚡",
            "hover": "👀",
            "scroll": "📜",
            "timer_capture": "⏱️",
        }
        return mapping.get(self.action_type, "📌")

    @property
    def base64_image(self) -> Optional[str]:
        """Return base64 string for embedding annotated image directly into HTML."""
        data = self.get_annotated_bytes()
        if data:
            return base64.b64encode(data).decode("ascii")
        return None

    @property
    def base64_thumbnail(self) -> Optional[str]:
        """Return base64 string for thumbnail."""
        data = self.get_thumbnail_bytes()
        if data:
            return base64.b64encode(data).decode("ascii")
        return self.base64_image

    @property
    def base64_focus_crop(self) -> Optional[str]:
        """Return base64 string for focus zoom cropped image."""
        data = self.get_focus_crop_bytes()
        if data:
            return base64.b64encode(data).decode("ascii")
        return None

    @property
    def focus_crop_data_uri(self) -> Optional[str]:
        """Return full data URI for focus crop."""
        b64 = self.base64_focus_crop
        if not b64:
            return None
        mime = self.image_mime_type or "image/png"
        return f"data:{mime};base64,{b64}"

    @property
    def base64_before(self) -> Optional[str]:
        """Return base64 string for before-action frame."""
        data = self.get_before_bytes()
        if data:
            return base64.b64encode(data).decode("ascii")
        return None

    @property
    def image_before_data_uri(self) -> Optional[str]:
        """Return full data URI for before frame."""
        b64 = self.base64_before
        if not b64:
            return None
        mime = self.image_mime_type or "image/png"
        return f"data:{mime};base64,{b64}"

    @property
    def image_data_uri(self) -> Optional[str]:
        """Return full data URI e.g. data:image/webp;base64,... or data:image/png;base64,..."""
        b64 = self.base64_image
        if not b64:
            return None
        mime = self.image_mime_type or "image/png"
        return f"data:{mime};base64,{b64}"

    @property
    def thumbnail_data_uri(self) -> Optional[str]:
        """Return thumbnail data URI."""
        b64 = self.base64_thumbnail
        if not b64:
            return None
        mime = self.image_mime_type or "image/png"
        return f"data:{mime};base64,{b64}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert step to dictionary for serialization."""
        return {
            "step_id": self.step_id,
            "timestamp": self.formatted_time,
            "action_type": self.action_type,
            "description": self.description,
            "window_title": self.window_title,
            "process_name": self.process_name,
            "pid": self.pid,
            "ui_control": self.ui_control,
            "window_rect": self.window_rect,
            "relative_cursor": self.relative_cursor,
            "cursor_x": self.cursor_x,
            "cursor_y": self.cursor_y,
            "drag_start": self.drag_start,
            "drag_end": self.drag_end,
            "highlight_rect": self.highlight_rect,
            "user_comment": self.user_comment,
            "typed_text": self.typed_text,
            "control_rect": self.control_rect,
            "is_section_header": self.is_section_header,
            "section_title": self.section_title,
            "section_description": self.section_description,
            "is_decision_point": self.is_decision_point,
            "condition_question": self.condition_question,
            "yes_branch_text": self.yes_branch_text,
            "yes_next_step": self.yes_next_step,
            "no_branch_text": self.no_branch_text,
            "no_next_step": self.no_next_step,
            "raw_image_path": self.raw_image_path,
            "annotated_image_path": self.annotated_image_path,
            "spool_raw_path": self.spool_raw_path,
            "spool_annotated_path": self.spool_annotated_path,
            "spool_before_path": self.spool_before_path,
            "spool_focus_crop_path": self.spool_focus_crop_path,
            "image_mime_type": self.image_mime_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Step":
        """Reconstruct Step from dictionary."""
        ts = data.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
            except Exception:
                try:
                    ts = datetime.fromisoformat(ts)
                except Exception:
                    ts = datetime.now()
        elif not isinstance(ts, datetime):
            ts = datetime.now()

        return cls(
            step_id=data.get("step_id", 1),
            timestamp=ts,
            action_type=data.get("action_type", "click"),
            description=data.get("description", ""),
            window_title=data.get("window_title", "Unknown Window"),
            process_name=data.get("process_name", "Unknown Process"),
            pid=data.get("pid"),
            ui_control=data.get("ui_control"),
            window_rect=tuple(data["window_rect"]) if data.get("window_rect") else None,
            relative_cursor=tuple(data["relative_cursor"]) if data.get("relative_cursor") else None,
            cursor_x=data.get("cursor_x"),
            cursor_y=data.get("cursor_y"),
            drag_start=tuple(data["drag_start"]) if data.get("drag_start") else None,
            drag_end=tuple(data["drag_end"]) if data.get("drag_end") else None,
            highlight_rect=tuple(data["highlight_rect"]) if data.get("highlight_rect") else None,
            user_comment=data.get("user_comment"),
            typed_text=data.get("typed_text"),
            control_rect=tuple(data["control_rect"]) if data.get("control_rect") else None,
            is_section_header=data.get("is_section_header", False),
            section_title=data.get("section_title"),
            section_description=data.get("section_description"),
            is_decision_point=data.get("is_decision_point", False),
            condition_question=data.get("condition_question"),
            yes_branch_text=data.get("yes_branch_text"),
            yes_next_step=data.get("yes_next_step"),
            no_branch_text=data.get("no_branch_text"),
            no_next_step=data.get("no_next_step"),
            raw_image_path=data.get("raw_image_path"),
            annotated_image_path=data.get("annotated_image_path"),
            spool_raw_path=data.get("spool_raw_path"),
            spool_annotated_path=data.get("spool_annotated_path"),
            spool_before_path=data.get("spool_before_path"),
            spool_focus_crop_path=data.get("spool_focus_crop_path"),
            image_mime_type=data.get("image_mime_type", "image/png"),
        )


@dataclass
class SessionMetadata:
    """Metadata about a recording session."""
    session_id: str
    title: str = "Problem Steps Recording"
    description: str = ""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    os_name: str = ""
    screen_resolution: str = ""
    monitors_info: str = ""
    total_steps: int = 0
    apps_used: List[str] = field(default_factory=list)

    @property
    def duration_str(self) -> str:
        """Formatted duration string (HH:MM:SS or MM:SS)."""
        if not self.end_time:
            delta = datetime.now() - self.start_time
        else:
            delta = self.end_time - self.start_time
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
