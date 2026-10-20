# -*- coding: utf-8 -*-
"""
Main launcher for SCADA-TraceLog
"""
import sys
import os

# Ensure current directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scada_tracelog.app import main

if __name__ == "__main__":
    main()
