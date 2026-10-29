#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utility Functions: Filename sanitization, natural sorting, and formatting.
"""

import os
import re
import unicodedata
from string import Formatter


def natural_sort_key(s: str):
    """Sorts strings containing numbers in natural human order (e.g. img2 before img10)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def sanitize_filename(filename: str, max_length: int = 120) -> str:
    """Sanitizes strings for safe, cross-platform file paths."""
    filename = unicodedata.normalize("NFC", str(filename))
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", filename)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(". ")
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned:
        cleaned = "untitled"
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(". ")
    return cleaned


class SafeFormatDict(dict):
    """Dict that preserves unformatted placeholders instead of raising KeyError."""
    def __missing__(self, key):
        return f"{{{key}}}"


def compute_filename(template: str, index: int, orig_stem: str, ocr_texts: list) -> str:
    """Computes sanitized new filename from template and extracted OCR fields."""
    format_vars = {
        "index": index,
        "name": sanitize_filename(orig_stem, max_length=50),
    }
    for i, o_text in enumerate(ocr_texts):
        format_vars[f"o{i+1}"] = sanitize_filename(o_text, max_length=40)

    try:
        raw_formatted = Formatter().vformat(template, (), SafeFormatDict(format_vars))
    except Exception:
        raw_formatted = f"{orig_stem}_renamed"

    return sanitize_filename(raw_formatted)


def get_unique_output_path(output_dir: str, base_name: str, ext: str, used_names: set) -> str:
    """Finds an unused filename in output_dir, appending _2, _3 if necessary."""
    clean_ext = ext.lstrip(".").lower()
    candidate = f"{base_name}.{clean_ext}"
    full_path = os.path.join(output_dir, candidate)
    counter = 2
    while candidate.lower() in used_names or os.path.exists(full_path):
        candidate = f"{base_name}_{counter}.{clean_ext}"
        full_path = os.path.join(output_dir, candidate)
        counter += 1
    used_names.add(candidate.lower())
    return full_path
