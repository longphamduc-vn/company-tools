#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR Engine Interfaces & Preprocessing Algorithms.
Supports RapidOCR (local offline) and Google Lens (cloud AI).
Includes CLAHE, Invert, Otsu Binarization, and Lanczos Upscaling.
"""

import sys
import asyncio
from PIL import Image, ImageOps, ImageFilter
import numpy as np
from .config import HAVE_CV2, HAVE_RAPIDOCR, HAVE_LENS

if HAVE_CV2:
    import cv2

if HAVE_RAPIDOCR:
    from rapidocr_onnxruntime import RapidOCR

if HAVE_LENS:
    from chrome_lens_py import LensAPI


def preprocess_for_ocr(img_pil: Image.Image, mode: str = "none", upscale: bool = False) -> Image.Image:
    """
    Applies image preprocessing to dramatically improve OCR accuracy on glass,
    faint laser etching, reflective glare, low-contrast ink, and noisy backgrounds.
    """
    if not mode or mode.lower().startswith("none"):
        if upscale:
            w, h = img_pil.size
            return img_pil.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
        return img_pil.convert("RGB")

    mode_key = mode.lower()

    if HAVE_CV2:
        img_np = np.array(img_pil)
        if img_np.ndim == 2:
            gray = img_np
        elif img_np.shape[2] == 4:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGBA2GRAY)
        else:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        if upscale:
            h, w = gray.shape[:2]
            gray = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_LANCZOS4)

        if "clahe" in mode_key:
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            processed = clahe.apply(gray)
        elif "invert" in mode_key:
            processed = cv2.bitwise_not(gray)
        elif "binarize" in mode_key or "otsu" in mode_key:
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            _, processed = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        elif "enhance" in mode_key:
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            eq = clahe.apply(gray)
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
            processed = cv2.filter2D(eq, -1, kernel)
        elif "sharpen" in mode_key:
            kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
            processed = cv2.filter2D(gray, -1, kernel)
        else:
            processed = gray

        return Image.fromarray(processed).convert("RGB")
    else:
        # Pure PIL Fallback
        gray = img_pil.convert("L")
        if upscale:
            w, h = gray.size
            gray = gray.resize((w * 2, h * 2), Image.Resampling.LANCZOS)

        if "invert" in mode_key:
            processed = ImageOps.invert(gray)
        elif "enhance" in mode_key or "clahe" in mode_key:
            eq = ImageOps.autocontrast(gray, cutoff=2)
            processed = eq.filter(ImageFilter.SHARPEN)
        elif "sharpen" in mode_key:
            processed = gray.filter(ImageFilter.SHARPEN)
        elif "binarize" in mode_key or "otsu" in mode_key:
            processed = gray.point(lambda p: 255 if p > 128 else 0)
        else:
            processed = gray

        return processed.convert("RGB")


def run_rapidocr(img_pil: Image.Image, engine=None):
    """
    Executes RapidOCR on a PIL image.
    Returns:
        (full_text: str, ocr_results: list)
        where ocr_results is a list of [box, text, confidence]
    """
    if not HAVE_RAPIDOCR:
        return "", []

    if engine is None:
        engine = RapidOCR()

    try:
        img_arr = np.array(img_pil)

        res, _ = engine(img_arr)
        if not res:
            return "", []

        lines = [line[1].strip() for line in res]
        full_text = "\n".join(lines)
        return full_text, res
    except Exception as e:
        print(f"RapidOCR execution error: {e}", file=sys.stderr)
        return "", []


async def run_lens_full_text(img_pil: Image.Image, lens_api=None):
    """
    Executes Google Lens on a PIL image.
    Returns:
        full_text: str
    """
    if not HAVE_LENS:
        return ""

    close_after = False
    if lens_api is None:
        lens_api = LensAPI()
        close_after = True

    try:
        res = await lens_api.process_image(img_pil, output_format="full_text")
        return res.get("ocr_text", "")
    except Exception as e:
        print(f"Google Lens execution error: {e}", file=sys.stderr)
        return ""
    finally:
        if close_after:
            await lens_api.aclose()
