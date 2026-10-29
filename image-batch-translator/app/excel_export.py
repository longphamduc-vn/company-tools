#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel Exporter with Embedded Images & Extraction Data.
Generates polished, professional Excel (.xlsx) workbooks containing:
- Embedded image thumbnails with ROI bounding box highlights
- Original filename, field name, variable tag
- Extracted characters and status (Valid, Empty, Manual Edit)
- Computed new filename
"""

import os
import shutil
import tempfile
from PIL import Image, ImageDraw

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.drawing.image import Image as OpenpyxlImage
    HAVE_OPENPYXL = True
except ImportError:
    HAVE_OPENPYXL = False


def export_results_to_excel(
    results_data: list,
    folder_path: str,
    output_filepath: str,
    progress_callback=None,
) -> bool:
    """
    Exports results_data to a rich Excel spreadsheet with embedded images.
    
    Args:
        results_data: List of dicts with keys (orig_file, field, var_tag, ocr_text, new_name, bbox, etc.)
        folder_path: Path to the folder containing original images.
        output_filepath: Target .xlsx filepath.
        progress_callback: Optional callable(current_idx, total) for progress reporting.
        
    Returns:
        True if successful, False otherwise.
    """
    if not HAVE_OPENPYXL:
        raise RuntimeError("openpyxl is not installed. Please install it with: pip install openpyxl")

    if not results_data:
        raise ValueError("No results data available to export.")

    # Create temporary directory for thumbnails
    temp_dir = tempfile.mkdtemp(prefix="ocr_excel_thumbs_")

    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "OCR Results & Preview"
        ws.views.sheetView[0].showGridLines = True

        # Styles
        font_title = Font(name="Segoe UI", size=15, bold=True, color="1E293B")
        font_meta = Font(name="Segoe UI", size=9, italic=True, color="64748B")
        font_hdr = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        font_cell = Font(name="Segoe UI", size=10, color="0F172A")
        font_cell_bold = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
        font_empty = Font(name="Segoe UI", size=10, bold=True, color="DC2626")

        fill_hdr = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        fill_even = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        fill_odd = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

        fill_valid = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        fill_error = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
        fill_manual = PatternFill(start_color="E0F2FE", end_color="E0F2FE", fill_type="solid")

        align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
        align_right = Alignment(horizontal="right", vertical="center")

        thin_side = Side(border_style="thin", color="CBD5E1")
        cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        # 1. Title Block
        ws.merge_cells("A1:H1")
        ws["A1"] = "🎯 BATCH OCR EXTRACTION & RENAMING REPORT"
        ws["A1"].font = font_title
        ws["A1"].alignment = align_left
        ws.row_dimensions[1].height = 28

        import datetime
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_rows = len(results_data)
        empty_count = sum(1 for r in results_data if not r.get("ocr_text", "").strip())
        valid_count = total_rows - empty_count

        ws.merge_cells("A2:H2")
        ws["A2"] = f"Generated: {now_str} | Total Records: {total_rows} | ✅ Valid: {valid_count} | ⚠️ Empty/Issues: {empty_count}"
        ws["A2"].font = font_meta
        ws["A2"].alignment = align_left
        ws.row_dimensions[2].height = 18

        # 2. Table Headers
        headers = [
            ("A", "No.", 6, align_center),
            ("B", "Original File", 24, align_left),
            ("C", "Image Preview", 24, align_center),
            ("D", "Field", 16, align_left),
            ("E", "Tag", 8, align_center),
            ("F", "Extracted Characters", 30, align_left),
            ("G", "New Filename", 32, align_left),
            ("H", "Status", 16, align_center),
        ]

        hdr_row = 4
        ws.row_dimensions[hdr_row].height = 28

        for col_letter, title, width, align in headers:
            cell = ws[f"{col_letter}{hdr_row}"]
            cell.value = title
            cell.font = font_hdr
            cell.fill = fill_hdr
            cell.alignment = align
            cell.border = cell_border
            ws.column_dimensions[col_letter].width = width

        # 3. Populate Rows
        current_excel_row = 5
        thumb_w, thumb_h = 150, 72

        for idx, row in enumerate(results_data):
            if progress_callback:
                progress_callback(idx + 1, total_rows)

            orig_filename = row.get("orig_file", "")
            field_name = row.get("field", "")
            var_tag = row.get("var_tag", "")
            ocr_text = row.get("ocr_text", "").strip()
            new_name = row.get("new_name", "")
            bbox = row.get("bbox")

            # Determine status
            if not ocr_text:
                status_text = "⚠️ EMPTY"
                status_fill = fill_error
            elif row.get("manual_edited"):
                status_text = "✏️ MANUAL"
                status_fill = fill_manual
            else:
                status_text = "✅ VALID"
                status_fill = fill_valid

            row_fill = fill_even if (idx % 2 == 0) else fill_odd

            # Set Excel Row Height to fit thumbnail cleanly
            ws.row_dimensions[current_excel_row].height = 62

            # Col A: Index
            c_a = ws[f"A{current_excel_row}"]
            c_a.value = idx + 1
            c_a.font = font_cell
            c_a.fill = row_fill
            c_a.alignment = align_center
            c_a.border = cell_border

            # Col B: Original File
            c_b = ws[f"B{current_excel_row}"]
            c_b.value = orig_filename
            c_b.font = font_cell
            c_b.fill = row_fill
            c_b.alignment = align_left
            c_b.border = cell_border

            # Col C: Image Preview Thumbnail
            c_c = ws[f"C{current_excel_row}"]
            c_c.value = ""
            c_c.fill = row_fill
            c_c.alignment = align_center
            c_c.border = cell_border

            full_img_path = os.path.join(folder_path, orig_filename)
            if os.path.isfile(full_img_path):
                try:
                    with Image.open(full_img_path) as raw_img:
                        img_rgb = raw_img.convert("RGB")
                        orig_w, orig_h = img_rgb.size

                        # Draw bounding box on thumbnail if available
                        if bbox and len(bbox) == 4:
                            bx1, by1, bx2, by2 = bbox
                            # Draw vivid neon rectangle on image copy
                            draw = ImageDraw.Draw(img_rgb)
                            line_w = max(2, int(min(orig_w, orig_h) / 150))
                            draw.rectangle([bx1, by1, bx2, by2], outline="#00ff66", width=line_w)

                        # Generate thumbnail preserving aspect ratio
                        scale = min(thumb_w / orig_w, thumb_h / orig_h)
                        nw = max(1, int(orig_w * scale))
                        nh = max(1, int(orig_h * scale))
                        thumb = img_rgb.resize((nw, nh), Image.Resampling.BILINEAR)

                        thumb_filename = f"thumb_{idx}_{orig_filename}.png"
                        thumb_path = os.path.join(temp_dir, thumb_filename)
                        thumb.save(thumb_path, format="PNG")

                        xl_img = OpenpyxlImage(thumb_path)
                        xl_img.width = nw
                        xl_img.height = nh
                        ws.add_image(xl_img, f"C{current_excel_row}")
                except Exception as e:
                    c_c.value = f"(No preview: {e})"
                    c_c.font = font_meta
            else:
                c_c.value = "(File not found)"
                c_c.font = font_meta

            # Col D: Field
            c_d = ws[f"D{current_excel_row}"]
            c_d.value = field_name
            c_d.font = font_cell_bold
            c_d.fill = row_fill
            c_d.alignment = align_left
            c_d.border = cell_border

            # Col E: Tag
            c_e = ws[f"E{current_excel_row}"]
            c_e.value = var_tag
            c_e.font = font_cell
            c_e.fill = row_fill
            c_e.alignment = align_center
            c_e.border = cell_border

            # Col F: Extracted Characters
            c_f = ws[f"F{current_excel_row}"]
            c_f.value = ocr_text if ocr_text else "(Empty)"
            c_f.font = font_cell_bold if ocr_text else font_empty
            c_f.fill = row_fill
            c_f.alignment = align_left
            c_f.border = cell_border

            # Col G: New Filename
            c_g = ws[f"G{current_excel_row}"]
            c_g.value = new_name
            c_g.font = font_cell
            c_g.fill = row_fill
            c_g.alignment = align_left
            c_g.border = cell_border

            # Col H: Status
            c_h = ws[f"H{current_excel_row}"]
            c_h.value = status_text
            c_h.font = font_cell_bold
            c_h.fill = status_fill
            c_h.alignment = align_center
            c_h.border = cell_border

            current_excel_row += 1

        # Enable AutoFilter on Table
        ws.auto_filter.ref = f"A{hdr_row}:H{current_excel_row - 1}"

        # Save workbook
        wb.save(output_filepath)
        return True

    finally:
        # Clean up temporary thumbnail images
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
