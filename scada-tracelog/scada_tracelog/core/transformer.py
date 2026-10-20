# -*- coding: utf-8 -*-
import re
from typing import List, Optional, Callable
import pandas as pd
import numpy as np

from scada_tracelog.core.validator import StructureValidator

class DataTransformer:
    """
    Bo chuyen doi du lieu SCADA tu cau truc mang ngang sang mang doc.
    """

    @staticmethod
    def extract_param_name(raw_name: str, mode: str = "description") -> str:
        """
        Trich xuat ten thong so may:
        - mode='description': Lay phan ben trong ngoac vuong [...]
        - mode='original': Giu nguyen ten goc
        - mode='both': Ma thiet bi + Ten mo ta
        """
        raw_str = str(raw_name).strip()
        match = re.search(r'\[(.*?)\]', raw_str)
        
        if mode == "description" and match:
            extracted = match.group(1).strip()
            return extracted if extracted else raw_str
        elif mode == "both" and match:
            prefix = raw_str[:match.start()].strip()
            desc = match.group(1).strip()
            if prefix and desc:
                return f"{prefix} - {desc}"
            return desc if desc else raw_str
            
        return raw_str

    @classmethod
    def transform_horizontal_to_vertical(
        cls,
        df_raw: pd.DataFrame,
        meta_cols: int,
        total_cols: int,
        name_mode: str = "description",
        logger: Optional[Callable[[str, str], None]] = None
    ) -> pd.DataFrame:
        """
        Chuyen doi vectorized tu ma tran ngang sang bang doc (Unpivot).
        """
        if df_raw.shape[0] <= 2:
            return pd.DataFrame(columns=["RECIPE ID", "TIME", "PARAMETER NAME", "VALUE", "LOWER LIMIT", "UPPER LIMIT"])
            
        recipe_ids = df_raw.iloc[2:, 0].values
        times = df_raw.iloc[2:, 1].values
        
        row0 = df_raw.iloc[0]
        chunks: List[pd.DataFrame] = []
        num_parameters = (total_cols - meta_cols) // 3
        
        if logger:
            logger(f"Transforming {num_parameters} parameters into vertical format...", "INFO")
            
        for col_idx in range(meta_cols, total_cols, 3):
            raw_param = StructureValidator.get_non_empty_header(row0, col_idx)
            clean_param = cls.extract_param_name(raw_param, mode=name_mode)
            
            val_col = pd.to_numeric(df_raw.iloc[2:, col_idx], errors="coerce").values
            lower_col = pd.to_numeric(df_raw.iloc[2:, col_idx + 1], errors="coerce").values
            upper_col = pd.to_numeric(df_raw.iloc[2:, col_idx + 2], errors="coerce").values
            
            sub_df = pd.DataFrame({
                "RECIPE ID": recipe_ids,
                "TIME": times,
                "PARAMETER NAME": clean_param,
                "VALUE": val_col,
                "LOWER LIMIT": lower_col,
                "UPPER LIMIT": upper_col
            })
            chunks.append(sub_df)
            
        combined_df = pd.concat(chunks, ignore_index=True)
        return combined_df
