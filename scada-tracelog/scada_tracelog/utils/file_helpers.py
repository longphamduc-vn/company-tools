# -*- coding: utf-8 -*-
import os
import sys
import subprocess

def open_file_in_os(file_or_dir_path: str) -> bool:
    """Mo file hoac thu muc bang chuong trinh mac dinh cua he dieu hanh."""
    if not os.path.exists(file_or_dir_path):
        return False
        
    try:
        if sys.platform.startswith("win"):
            os.startfile(file_or_dir_path)
            return True
        elif sys.platform.startswith("darwin"):
            subprocess.run(["open", file_or_dir_path], check=True)
            return True
        else:
            subprocess.run(["xdg-open", file_or_dir_path], check=True)
            return True
    except Exception:
        return False
