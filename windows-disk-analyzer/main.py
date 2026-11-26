#!/usr/bin/env python3
"""Entry point for Windows Disk Analyzer."""

from __future__ import annotations

import os
import sys

# Ensure UTF-8 stdout/stderr on Windows terminals
for stream in (sys.stdout, sys.stderr):
    if stream and hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from disk_analyzer.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())
