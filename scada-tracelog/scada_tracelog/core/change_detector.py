# -*- coding: utf-8 -*-
from typing import Optional, Callable
import pandas as pd

class ChangeDetector:
    """
    Bo phat hien bien dong gia tri VALUE theo thoi gian cho tung Recipe va Thong so.
    """

    @classmethod
    def detect_changes(
        cls,
        df_long: pd.DataFrame,
        include_baseline: bool = False,
        logger: Optional[Callable[[str, str], None]] = None
    ) -> pd.DataFrame:
        """
        Chi ghi nhan mot dong log khi gia tri VALUE cua thong so do THAY DOI
        so voi moc thoi gian lien truoc cua cung mot RECIPE ID va PARAMETER NAME.
        """
        if df_long.empty:
            return pd.DataFrame(columns=["RECIPE ID", "TIME", "PARAMETER NAME", "VALUE", "LOWER LIMIT", "UPPER LIMIT"])
            
        if logger:
            logger("Analyzing value transitions to compile Change Log...", "INFO")
            
        df = df_long.copy()
        df["PARSED_TIME"] = pd.to_datetime(df["TIME"], errors="coerce")
        
        # Sap xep tang dan theo RECIPE ID, PARAMETER NAME va thoi gian thuc
        df = df.sort_values(by=["RECIPE ID", "PARAMETER NAME", "PARSED_TIME", "TIME"])
        
        # Lay gia tri VALUE tai moc thoi gian lien ke truoc
        df["PREV_VALUE"] = df.groupby(["RECIPE ID", "PARAMETER NAME"])["VALUE"].shift(1)
        
        if include_baseline:
            # Ghi nhan ca moc ban dau cua Recipe
            mask = df["VALUE"].ne(df["PREV_VALUE"])
        else:
            # Chi ghi nhan cac buoc nhay gia tri (Strict Changes Only)
            mask = df["PREV_VALUE"].notna() & (df["VALUE"] != df["PREV_VALUE"])
            
        filtered_df = df[mask].copy()
        
        # Sap xep lai ket qua theo thu tu thoi gian dien ra su kien (Audit Trail)
        filtered_df = filtered_df.sort_values(by=["PARSED_TIME", "RECIPE ID", "PARAMETER NAME"])
        
        output_cols = ["RECIPE ID", "TIME", "PARAMETER NAME", "VALUE", "LOWER LIMIT", "UPPER LIMIT"]
        final_change_log = filtered_df[output_cols].reset_index(drop=True)
        
        if logger:
            logger(f"Identified {len(final_change_log):,} change event(s) across timeline.", "SUCCESS")
            
        return final_change_log
