# -*- coding: utf-8 -*-
import os
import glob
from typing import Optional, Callable, List
import pandas as pd

from scada_tracelog.core.validator import StructureValidator
from scada_tracelog.core.transformer import DataTransformer
from scada_tracelog.core.change_detector import ChangeDetector
from scada_tracelog.core.exceptions import Excel256ColumnLimitError, SCADAProcessingError

class SCADADataProcessor:
    """
    Bo dieu phoi quy trinh xu ly du lieu SCADA tu file dau vao den file Change Log CSV.
    """

    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self.log_callback = log_callback

    def log(self, message: str, level: str = "INFO"):
        if self.log_callback:
            self.log_callback(message, level)
        else:
            print(f"[{level}] {message}")

    def validate_file_structure(self, file_path: str):
        return StructureValidator.validate(file_path, logger=self.log)

    def read_and_unpivot(self, file_path: str, name_mode: str = "description") -> pd.DataFrame:
        filename = os.path.basename(file_path)
        meta_cols, total_cols = self.validate_file_structure(file_path)
        
        self.log(f"Loading Excel file [{filename}] ({total_cols} columns)...", "INFO")
        df_raw = pd.read_excel(file_path, header=None)
        
        return DataTransformer.transform_horizontal_to_vertical(
            df_raw,
            meta_cols=meta_cols,
            total_cols=total_cols,
            name_mode=name_mode,
            logger=self.log
        )

    def generate_change_log(self, df_long: pd.DataFrame, include_baseline: bool = False) -> pd.DataFrame:
        return ChangeDetector.detect_changes(
            df_long,
            include_baseline=include_baseline,
            logger=self.log
        )

    def process_single_file(
        self,
        file_path: str,
        output_csv_path: str,
        name_mode: str = "description",
        include_baseline: bool = False
    ) -> str:
        """Xu ly mot file don le."""
        df_long = self.read_and_unpivot(file_path, name_mode=name_mode)
        change_log = self.generate_change_log(df_long, include_baseline=include_baseline)
        
        change_log.to_csv(output_csv_path, index=False, encoding="utf-8-sig")
        self.log(f"Exported Change Log CSV: {output_csv_path}", "SUCCESS")
        return output_csv_path

    def process_folder(
        self,
        folder_path: str,
        output_csv_path: str,
        name_mode: str = "description",
        include_baseline: bool = False
    ) -> str:
        """Quet va xu ly tat ca cac file .xls va .xlsx trong thu muc."""
        excel_files: List[str] = []
        for ext in ("*.xls", "*.xlsx"):
            pattern = os.path.join(folder_path, ext)
            excel_files.extend(glob.glob(pattern))
            
        excel_files = [f for f in excel_files if not os.path.basename(f).startswith("~$")]
        
        if not excel_files:
            raise FileNotFoundError(f"No .xls or .xlsx files found in: {folder_path}")
            
        excel_files.sort()
        self.log(f"Found {len(excel_files)} Excel file(s). Starting validation...", "INFO")
        
        all_dfs: List[pd.DataFrame] = []
        for idx, fpath in enumerate(excel_files, start=1):
            fname = os.path.basename(fpath)
            self.log(f"[{idx}/{len(excel_files)}] Inspecting & converting: {fname}", "INFO")
            df_file = self.read_and_unpivot(fpath, name_mode=name_mode)
            if not df_file.empty:
                all_dfs.append(df_file)
                
        if not all_dfs:
            empty_df = pd.DataFrame(columns=["RECIPE ID", "TIME", "PARAMETER NAME", "VALUE", "LOWER LIMIT", "UPPER LIMIT"])
            empty_df.to_csv(output_csv_path, index=False, encoding="utf-8-sig")
            return output_csv_path
            
        self.log("Consolidating timeline across all files...", "INFO")
        combined_all = pd.concat(all_dfs, ignore_index=True)
        
        change_log = self.generate_change_log(combined_all, include_baseline=include_baseline)
        change_log.to_csv(output_csv_path, index=False, encoding="utf-8-sig")
        self.log(f"Consolidated Change Log generated at: {output_csv_path}", "SUCCESS")
        return output_csv_path
