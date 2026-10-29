#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extraction Algorithms & Bounding Box Localization.
Supports Keyword Anchor Extraction, Regex Capturing Groups,
Ratio Coordinate Bounding Boxes, and Automatic Text ROI Localization.
"""

import re
import sys
import asyncio
from PIL import Image
from .config import HAVE_RAPIDOCR, HAVE_LENS
from .ocr_engine import preprocess_for_ocr, run_rapidocr

if HAVE_RAPIDOCR:
    from rapidocr_onnxruntime import RapidOCR
    import numpy as np


def extract_by_keyword(full_text: str, keyword: str) -> str:
    """
    Extracts text associated with a keyword across full text.
    Resilient to:
    - Same line with colon: 'Mã phiếu: PXK-2026-001', 'GlassID: DLLLLLL1'
    - Same line with space: 'GlassID DLLLLLL1'
    - Same line fused: 'GlassIDDLLLLLL1'
    - Multi-line with colon or break: 'Mã phiếu:\nPXK-2026-001'
    Works even if images are cropped, shifted or scaled!
    """
    if not keyword.strip() or not full_text:
        return ""
    kw = re.escape(keyword.strip())

    # 1. Try same line (with optional separator or fused)
    m1 = re.search(rf"(?i){kw}[:\s\-_–—]*([^\n\r]+)", full_text)
    if m1 and m1.group(1).strip():
        return m1.group(1).strip()

    # 2. Try next line
    m2 = re.search(rf"(?i){kw}[:\s\-_–—]*\n+([^\n\r]+)", full_text)
    if m2 and m2.group(1).strip():
        return m2.group(1).strip()

    # 3. Line by line matching
    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
    for idx, line in enumerate(lines):
        if re.search(rf"(?i){kw}", line):
            rem = re.sub(rf"(?i)^.*?{kw}[:\s\-_–—]*", "", line).strip()
            if rem:
                return rem
            elif idx + 1 < len(lines):
                return lines[idx + 1].strip()

    return ""


def extract_by_pattern(full_text: str, pattern: str) -> str:
    """Extracts text matching a regex pattern from full text (returns group 1 if capturing group exists)."""
    if not pattern.strip() or not full_text:
        return ""
    try:
        m = re.search(pattern.strip(), full_text)
        if m:
            return m.group(1).strip() if m.groups() else m.group(0).strip()
        return ""
    except Exception:
        return ""


def extract_by_box(img: Image.Image, box: tuple, engine_name: str, lens_api=None, rapid_engine=None) -> str:
    """Crops by ratio coordinates and OCRs just that box."""
    orig_w, orig_h = img.size
    rx1, ry1, rx2, ry2 = box
    x1 = max(0, min(orig_w - 1, int(round(rx1 * orig_w))))
    y1 = max(0, min(orig_h - 1, int(round(ry1 * orig_h))))
    x2 = max(x1 + 1, min(orig_w, int(round(rx2 * orig_w))))
    y2 = max(y1 + 1, min(orig_h, int(round(ry2 * orig_h))))

    crop = img.crop((x1, y1, x2, y2))
    if "Google" in engine_name and lens_api:
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(lens_api.process_image(crop))
            return res.get("ocr_text", "").strip()
        finally:
            loop.close()
    elif rapid_engine:
        res, _ = rapid_engine(np.array(crop))
        return " ".join([l[1] for l in res]).strip() if res else ""
    return ""


def find_bounding_box_for_rule(
    ocr_results: list,
    rule: dict,
    extracted_text: str,
    orig_size: tuple,
    proc_size: tuple = None,
) -> list:
    """
    Locates the pixel bounding box [x1, y1, x2, y2] on the original image for a given rule.
    Maps coordinates from processed/upscaled image back to original image dimensions.
    """
    orig_w, orig_h = orig_size
    if proc_size:
        proc_w, proc_h = proc_size
        scale_x = orig_w / max(1, proc_w)
        scale_y = orig_h / max(1, proc_h)
    else:
        scale_x, scale_y = 1.0, 1.0

    # 1. If rule is coordinate box
    if rule.get("type") == "box" and rule.get("box"):
        b = rule["box"]
        return [
            int(round(b["rx1"] * orig_w)),
            int(round(b["ry1"] * orig_h)),
            int(round(b["rx2"] * orig_w)),
            int(round(b["ry2"] * orig_h)),
        ]

    if not ocr_results:
        return None

    # Helper to convert polygon to bbox in original image coordinates
    def poly_to_orig_bbox(poly):
        xs = [pt[0] * scale_x for pt in poly]
        ys = [pt[1] * scale_y for pt in poly]
        x1 = max(0, int(min(xs)))
        y1 = max(0, int(min(ys)))
        x2 = min(orig_w, int(max(xs)))
        y2 = min(orig_h, int(max(ys)))
        return [x1, y1, x2, y2]

    clean_target = extracted_text.strip().lower() if extracted_text else ""

    # Priority A: Line contains the extracted value
    if clean_target:
        for item in ocr_results:
            poly, line_text, _ = item
            clean_line = line_text.strip().lower()
            if clean_target in clean_line:
                return poly_to_orig_bbox(poly)

    # Priority B: Keyword match
    if rule.get("type") == "keyword" and rule.get("keyword"):
        kw = rule["keyword"].strip().lower()
        for item in ocr_results:
            poly, line_text, _ = item
            clean_line = line_text.strip().lower()
            if kw in clean_line:
                return poly_to_orig_bbox(poly)

    # Priority C: Regex pattern match
    if rule.get("type") == "regex" and rule.get("pattern"):
        pat = rule["pattern"].strip()
        try:
            for item in ocr_results:
                poly, line_text, _ = item
                if re.search(pat, line_text):
                    return poly_to_orig_bbox(poly)
        except Exception:
            pass

    return None


def auto_detect_bbox_for_image(
    img_pil: Image.Image,
    rule: dict,
    extracted_text: str,
    prep_mode: str = "none",
    upscale: bool = False,
    engine=None,
) -> list:
    """
    On-demand detection of field bounding box directly on an image.
    Useful for Review Focus dialog when full-scan bboxes were not cached.
    """
    orig_w, orig_h = img_pil.size

    # Rule is coordinate box
    if rule.get("type") == "box" and rule.get("box"):
        b = rule["box"]
        return [
            int(round(b["rx1"] * orig_w)),
            int(round(b["ry1"] * orig_h)),
            int(round(b["rx2"] * orig_w)),
            int(round(b["ry2"] * orig_h)),
        ]

    if not HAVE_RAPIDOCR:
        return None

    try:
        prep_img = preprocess_for_ocr(img_pil, mode=prep_mode, upscale=upscale)
        full_text, ocr_results = run_rapidocr(prep_img, engine=engine)
        return find_bounding_box_for_rule(
            ocr_results,
            rule,
            extracted_text,
            orig_size=(orig_w, orig_h),
            proc_size=prep_img.size,
        )
    except Exception as e:
        print(f"Auto-detect bbox error: {e}", file=sys.stderr)
        return None
