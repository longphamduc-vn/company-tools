"""Human-readable formatting utilities for disk sizes, timestamps, and paths."""

from __future__ import annotations

from datetime import datetime
from typing import Optional


def format_bytes(num_bytes: int | float, decimals: int = 2) -> str:
    """Format byte counts using Windows Explorer binary units (1 KB = 1024 B)."""
    if num_bytes is None:
        return "0 B"
    negative = num_bytes < 0
    value = abs(float(num_bytes))
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    idx = 0
    while value >= 1024.0 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    prefix = "-" if negative else ""
    if idx == 0:
        return f"{prefix}{int(value):,} B"
    return f"{prefix}{value:,.{decimals}f} {units[idx]}"


def format_duration(seconds: float) -> str:
    """Format elapsed seconds into a concise readable string."""
    if seconds < 1.0:
        return f"{int(seconds * 1000)} ms"
    if seconds < 60.0:
        return f"{seconds:.1f}s"
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}h {mins}m {secs}s"
    return f"{mins}m {secs}s"


def format_timestamp(ts: Optional[float], include_time: bool = False) -> str:
    """Format a Unix timestamp cleanly."""
    if not ts or ts <= 0:
        return "-"
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M" if include_time else "%Y-%m-%d")
    except (OSError, OverflowError, ValueError):
        return "-"


def make_percent_bar(percent: float, width: int = 12) -> str:
    """Create a compact Unicode progress bar for tables and CLI output."""
    clamped = max(0.0, min(100.0, percent))
    filled = int(round((clamped / 100.0) * width))
    return f"[{'█' * filled}{'░' * (width - filled)}] {clamped:5.1f}%"


def truncate_middle(text: str, max_len: int = 64) -> str:
    """Shorten long file paths from the middle while preserving drive and filename."""
    if len(text) <= max_len or max_len < 10:
        return text
    keep = max_len - 3
    head = keep // 2
    tail = keep - head
    return f"{text[:head]}...{text[-tail:]}"
