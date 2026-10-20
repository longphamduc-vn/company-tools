# -*- coding: utf-8 -*-
import os
from typing import Tuple, Callable, Optional
import pandas as pd

from scada_tracelog.core.exceptions import Excel256ColumnLimitError, SCADAProcessingError

class StructureValidator:
    """
    Bo kiem tra cau truc cot va phat hien hien tuong mat mat du lieu do gioi han 256 cot.
    """

    @staticmethod
    def get_non_empty_header(row0: pd.Series, target_idx: int) -> str:
        """
        Lay ten thong so tai target_idx. Neu o bi merge (NaN), quet nguoc lai.
        """
        val = row0.iloc[target_idx]
        if pd.notna(val) and str(val).strip() != "" and str(val).strip().lower() != "nan":
            return str(val).strip()
            
        for back_idx in range(target_idx - 1, -1, -1):
            back_val = row0.iloc[back_idx]
            if pd.notna(back_val) and str(back_val).strip() != "" and str(back_val).strip().lower() != "nan":
                return str(back_val).strip()
                
        return f"Parameter_Col_{target_idx}"

    @staticmethod
    def find_metadata_columns_count(row0: pd.Series, row1: pd.Series) -> int:
        """
        Xac dinh so cot metadata (RECIPE ID, TIME...).
        Dung row1 kiem tra noi cot dau tien chua 'VALUE'.
        """
        for idx, val in enumerate(row1):
            if str(val).strip().upper() == "VALUE":
                return idx
        return 2

    @classmethod
    def validate(cls, file_path: str, logger: Optional[Callable[[str, str], None]] = None) -> Tuple[int, int]:
        """
        Kiem tra cau truc cua file Excel:
        - Doc nhanh 2 dong header dau tien.
        - Xac dinh so cot thong so.
        - Kiem tra bo 3 cot [VALUE, Gia tri duoi, Gia tri tren].
        - Neu thong so cuoi bi thieu: DUNG XU LY va nem ngoai le Excel256ColumnLimitError.
        """
        filename = os.path.basename(file_path)
        df_header = pd.read_excel(file_path, header=None, nrows=2)
        total_cols = df_header.shape[1]
        
        if total_cols < 3:
            raise SCADAProcessingError(f"File [{filename}] has fewer than 3 columns. Invalid SCADA format.")
            
        row0 = df_header.iloc[0]
        row1 = df_header.iloc[1]
        
        meta_cols = cls.find_metadata_columns_count(row0, row1)
        param_cols_count = total_cols - meta_cols
        
        remainder = param_cols_count % 3
        if remainder != 0:
            last_param_col_idx = total_cols - remainder
            last_param_name = cls.get_non_empty_header(row0, last_param_col_idx)
            
            missing_count = 3 - remainder
            missing_desc = "Upper Limit ('Gia tri tren')" if missing_count == 1 else "Lower & Upper Limits"
            
            if logger:
                logger(
                    f"CRITICAL: File [{filename}] has {total_cols} columns! "
                    f"Parameter [{last_param_name}] at col {last_param_col_idx} is truncated ({remainder}/3 cols). "
                    f"Missing: {missing_desc}. Aborting process!",
                    "ERROR"
                )
            raise Excel256ColumnLimitError(filename, last_param_name, missing_info=missing_desc)
            
        return meta_cols, total_cols
