"""
Python Step Recorder
A modern, cross-platform alternative to Windows Steps Recorder (Problem Steps Recorder / PSR).
"""

import sys

# Enable Per-Monitor / System DPI Awareness immediately before any UI or capture calls
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

__version__ = "1.1.0"
__author__ = "Company Tools Team"
