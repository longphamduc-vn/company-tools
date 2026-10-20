# -*- coding: utf-8 -*-
"""
Lop ngoai le tuy chinh cho he thong SCADA-TraceLog.
"""

class SCADAProcessingError(Exception):
    """Lop ngoai le co so cho cac loi xu ly SCADA."""
    pass

class Excel256ColumnLimitError(SCADAProcessingError):
    """
    Lop ngoai le phat hien cat cut du lieu do cham gioi han 256 cot
    trong cac tap tin Excel dinh dang cu (.xls).
    """
    def __init__(self, filename: str, parameter_name: str, missing_info: str = ""):
        self.filename = filename
        self.parameter_name = parameter_name
        self.missing_info = missing_info
        self.message = (
            f"DATA LOSS WARNING: File [{filename}] is missing column data "
            f"due to Excel 256-column limit at parameter [{parameter_name}]!"
        )
        super().__init__(self.message)
