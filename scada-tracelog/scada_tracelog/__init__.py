# -*- coding: utf-8 -*-
"""
SCADA-TraceLog: Industrial SCADA Recipe Audit & 256-Column Data Loss Guard
"""

__version__ = "1.0.0"
__app_name__ = "SCADA-TraceLog"
__author__ = "SCADA Data Optimization Team"

from scada_tracelog.core.exceptions import Excel256ColumnLimitError, SCADAProcessingError
from scada_tracelog.core.processor import SCADADataProcessor

__all__ = [
    "__version__",
    "__app_name__",
    "Excel256ColumnLimitError",
    "SCADAProcessingError",
    "SCADADataProcessor"
]
