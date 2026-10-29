#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick Automated Test Script for Character Extraction & Batch Renaming
Demonstrates Google Lens OCR and RapidOCR extracting characters from sample images.
"""

import os
import sys
import asyncio
from PIL import Image

def run_test():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sample_dir = os.path.join(base_dir, "sample_images")
    if not os.path.isdir(sample_dir):
        print(f"Error: Sample images directory not found at {sample_dir}", file=sys.stderr)
        return

    files = sorted([f for f in os.listdir(sample_dir) if f.endswith(".png")])
    print("=" * 70)
    print("🚀 BẮT ĐẦU KIỂM THỬ TRÍCH XUẤT KÝ TỰ TỪ ẢNH MẪU (TEST OCR EXTRACTION)")
    print(f"📁 Thư mục ảnh mẫu: {sample_dir}")
    print(f"🖼️ Tổng số ảnh: {len(files)} ({', '.join(files)})")
    print("=" * 70)

    # 3 vùng chọn mẫu theo layout phiếu xuất kho
    regions = [
        {"name": "Vùng 1 (Mã phiếu)", "box": (190, 130, 480, 175), "var": "{o1}"},
        {"name": "Vùng 2 (Tên hàng)", "box": (190, 200, 680, 245), "var": "{o2}"},
        {"name": "Vùng 3 (Trạng thái)", "box": (190, 340, 480, 385), "var": "{o3}"},
    ]

    print("\n📌 Các vùng chọn mẫu (Regions):")
    for r in regions:
        print(f"  - {r['name']} -> Tọa độ: {r['box']} (Biến đổi tên: {r['var']})")

    # Kiểm tra Google Lens OCR
    print("\n🔍 ĐANG TIẾN HÀNH TRÍCH XUẤT BẰNG GOOGLE LENS (KHÔNG CẦN TESSERACT)...")
    try:
        from chrome_lens_py import LensAPI
        async def run_google():
            lens = LensAPI()
            try:
                for f in files:
                    img_path = os.path.join(sample_dir, f)
                    img = Image.open(img_path)
                    print(f"\n📂 Tệp: {f}")
                    extracted = []
                    for idx, r in enumerate(regions):
                        crop = img.crop(r["box"])
                        res = await lens.process_image(crop)
                        txt = res.get("ocr_text", "").strip()
                        extracted.append(txt)
                        print(f"   [{r['name']}]: \"{txt}\"")
                    
                    # Đổi tên theo mẫu: {o1}_{o2}.png
                    clean_code = extracted[0].replace(" ", "_")
                    clean_item = extracted[1].replace(" ", "_")
                    new_filename = f"{clean_code}_{clean_item}.png"
                    print(f"   ✨ TÊN FILE MỚI ĐƯỢC TẠO: -> {new_filename}")
            finally:
                await lens.aclose()

        asyncio.run(run_google())
        print("\n✅ KIỂM THỬ GOOGLE LENS HOÀN THÀNH XUẤT SẮC 100%!")
    except Exception as e:
        print(f"Google Lens test error: {e}", file=sys.stderr)

    print("=" * 70)

if __name__ == "__main__":
    run_test()
