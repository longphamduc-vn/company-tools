#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session Persistence & Crash Recovery Manager.
Safeguards extraction results, manual corrections, rules, and configurations
by automatically caching session state to disk to prevent data loss on unexpected exits or crashes.
"""

import os
import json
import hashlib
import datetime
from typing import Optional, Dict, Any


def _get_cache_filepath(folder_path: str) -> str:
    """Returns the primary hidden cache file path in the image directory."""
    if not folder_path or not os.path.isdir(folder_path):
        return ""
    # Hidden file inside the image folder
    primary = os.path.join(folder_path, ".ocr_session_cache.json")
    try:
        # Test write permission
        test_file = os.path.join(folder_path, ".tmp_perm_check")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        return primary
    except Exception:
        # Fallback to user's home cache directory
        home_cache = os.path.expanduser("~/.cache/image_batch_translator")
        os.makedirs(home_cache, exist_ok=True)
        folder_hash = hashlib.md5(folder_path.encode("utf-8")).hexdigest()[:12]
        return os.path.join(home_cache, f"session_{folder_hash}.json")


def save_session(
    folder_path: str,
    rules: list,
    template: str,
    format_val: str,
    preprocess_mode: str,
    upscale_2x: bool,
    ocr_engine: str,
    results_data: list,
) -> bool:
    """
    Atomically saves session data to disk.
    Uses .tmp file + atomic rename to prevent corruption.
    """
    if not folder_path or not results_data:
        return False

    cache_path = _get_cache_filepath(folder_path)
    if not cache_path:
        return False

    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Serialize results_data safely (strip non-serializable objects)
    clean_results = []
    for r in results_data:
        clean_row = {
            "orig_file": r.get("orig_file", ""),
            "field": r.get("field", ""),
            "var_tag": r.get("var_tag", ""),
            "rule_idx": r.get("rule_idx", 0),
            "img_idx": r.get("img_idx", 0),
            "ocr_text": r.get("ocr_text", ""),
            "new_name": r.get("new_name", ""),
            "bbox": r.get("bbox"),
            "manual_bbox": r.get("manual_bbox", False),
            "manual_edited": r.get("manual_edited", False),
        }
        clean_results.append(clean_row)

    payload = {
        "version": "2.1.0",
        "last_saved": now_iso,
        "folder_path": folder_path,
        "rules": rules,
        "template": template,
        "format": format_val,
        "preprocess_mode": preprocess_mode,
        "upscale_2x": upscale_2x,
        "ocr_engine": ocr_engine,
        "results_data": clean_results,
    }

    tmp_path = cache_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, cache_path)
        return True
    except Exception as e:
        print("Session save error:", e)
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False


def has_saved_session(folder_path: str) -> bool:
    """Checks if a valid session cache exists for the given folder."""
    if not folder_path:
        return False
    cache_path = _get_cache_filepath(folder_path)
    if cache_path and os.path.isfile(cache_path):
        try:
            return os.path.getsize(cache_path) > 50
        except Exception:
            return False
    return False


def load_session(folder_path: str) -> Optional[Dict[str, Any]]:
    """Loads session data from disk if available."""
    if not folder_path:
        return None
    cache_path = _get_cache_filepath(folder_path)
    if not cache_path or not os.path.isfile(cache_path):
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "results_data" in data and isinstance(data["results_data"], list):
            return data
    except Exception as e:
        print("Session load error:", e)
    return None


def clear_session(folder_path: str) -> bool:
    """Deletes the session cache file for this folder."""
    if not folder_path:
        return False
    cache_path = _get_cache_filepath(folder_path)
    if cache_path and os.path.isfile(cache_path):
        try:
            os.remove(cache_path)
            return True
        except Exception:
            pass
    return False
