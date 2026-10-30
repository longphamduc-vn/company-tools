"""
Comprehensive Logging & Diagnostics Setup for Drawing Vault.
Configures:
- File logger: logs everything (DEBUG, INFO, WARNING, ERROR, TRACEBACK) to vault_download.log.
- Stream logger: logs to stdout/stderr.
- UI Log Queue Handler: allows live Tkinter log consoles to display real-time events.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Callable, Optional, List

from drawing_vault.config import PROJECT_ROOT

LOG_FILE_PATH = str(PROJECT_ROOT / "vault_download.log")

# Standard format for diagnostics
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class QueueLogHandler(logging.Handler):
    """Thread-safe logging handler that dispatches log records to GUI listeners."""

    def __init__(self, callback: Optional[Callable[[str, int], None]] = None):
        super().__init__()
        self.callback = callback
        self.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))

    def set_callback(self, callback: Callable[[str, int], None]):
        self.callback = callback

    def emit(self, record):
        try:
            msg = self.format(record)
            if self.callback:
                self.callback(msg, record.levelno)
        except Exception:
            self.handleError(record)


# Global UI Log Handler instance
ui_log_handler = QueueLogHandler()


def setup_diagnostics_logging(verbose: bool = True, log_file: str = LOG_FILE_PATH) -> logging.Logger:
    """
    Sets up root and application loggers to write detailed logs to file and console.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if called multiple times
    for h in list(root_logger.handlers):
        if getattr(h, "_vault_managed", False):
            root_logger.removeHandler(h)

    # 1. Persistent File Handler (Always DEBUG level)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        file_handler._vault_managed = True
        root_logger.addHandler(file_handler)
    except Exception as e:
        sys.stderr.write(f"Warning: Could not initialize log file at {log_file}: {e}\n")

    # 2. Console Stream Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"))
    console_handler._vault_managed = True
    root_logger.addHandler(console_handler)

    # 3. UI Queue Handler
    ui_log_handler.setLevel(logging.DEBUG)
    ui_log_handler._vault_managed = True
    if ui_log_handler not in root_logger.handlers:
        root_logger.addHandler(ui_log_handler)

    logger = logging.getLogger("drawing_vault")
    logger.info("=== Logging initialized: Log file -> %s ===", log_file)
    return logger


def get_log_file_path() -> str:
    return LOG_FILE_PATH


def read_latest_log_tail(max_lines: int = 150) -> str:
    """Reads the last N lines of vault_download.log."""
    if not os.path.isfile(LOG_FILE_PATH):
        return "(No log file created yet)"
    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:])
    except Exception as e:
        return f"Error reading log file: {e}"
