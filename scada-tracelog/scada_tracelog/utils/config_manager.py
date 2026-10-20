# -*- coding: utf-8 -*-
import json
import os
from typing import Dict, Any

class ConfigManager:
    """
    Quan ly luu tru va khoi phuc cau hinh nguoi dung (Saved Preferences).
    """
    CONFIG_FILE = os.path.expanduser("~/.scada_tracelog_config.json")

    DEFAULT_CONFIG = {
        "input_mode": "single",
        "last_path": "",
        "include_baseline": False,
        "param_format": "Description Only (inside [...])",
        "auto_open": True,
        "output_filename": "scada_change_log.csv"
    }

    @classmethod
    def load_config(cls) -> Dict[str, Any]:
        if os.path.exists(cls.CONFIG_FILE):
            try:
                with open(cls.CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cfg = cls.DEFAULT_CONFIG.copy()
                    cfg.update(data)
                    return cfg
            except Exception:
                pass
        return cls.DEFAULT_CONFIG.copy()

    @classmethod
    def save_config(cls, config_data: Dict[str, Any]):
        try:
            with open(cls.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
