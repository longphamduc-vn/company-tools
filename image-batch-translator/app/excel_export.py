#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel Exporter with Dual Embedded Images (Focus ROI & Full Overview) & Padded Highlights.
Generates polished, professional Excel (.xlsx) workbooks containing:
- Column C: High-Resolution Focus ROI crop (padded text highlight, 2x Retina DPI Lanczos)
- Column D: High-Resolution Full Image Overview (full view with padded bounding box)
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
    Exports results_data to a rich Excel spreadsheet with dual embedded images:
    1. Focus ROI (high-res zoomed-in text crop with padded highlight box)
    2. Full Overview (full image thumbnail with padded bounding box locator)
    
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
        ws.title = "OCR Results & Previews"
        ws.views.sheetView[0].showGridLines = True

        # Styles
        font_title = Font(name="Segoe UI", size=15, bold=True, color="1E293B")
        font_meta = Font(name="Segoe UI", size=9, italic=True, color="64748B")
        font_hdr = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        font_cell = Font(name="Segoe UI", size=10, color="0F172A")
        font_cell_bold = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
        font_empty = Font(name="Segoe UI", size=10, bold=True, color="DC2626")
        font_no_roi = Font(name="Segoe UI", size=9, italic=True, color="94A3B8")

        fill_hdr = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        fill_even = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        fill_odd = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

        fill_valid = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        fill_error = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
        fill_manual = PatternFill(start_color="E0F2FE", end_color="E0F2FE", fill_type="solid")

        align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)

        thin_side = Side(border_style="thin", color="CBD5E1")
        cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        # 1. Title Block (Merged A1:I1)
        ws.merge_cells("A1:I1")
        ws["A1"] = "🎯 BATCH OCR EXTRACTION & RENAMING REPORT"
        ws["A1"].font = font_title
        ws["A1"].alignment = align_left
        ws.row_dimensions[1].height = 28

        import datetime
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_rows = len(results_data)
        empty_count = sum(1 for r in results_data if not r.get("ocr_text", "").strip())
        valid_count = total_rows - empty_count

        ws.merge_cells("A2:I2")
        ws["A2"] = f"Generated: {now_str} | Total Records: {total_rows} | ✅ Valid: {valid_count} | ⚠️ Empty/Issues: {empty_count}"
        ws["A2"].font = font_meta
        ws["A2"].alignment = align_left
        ws.row_dimensions[2].height = 18

        # 2. Table Headers (Both Focus ROI in Col C and Full Overview in Col D)
        headers = [
            ("A", "No.", 6, align_center),
            ("B", "Original File", 22, align_left),
            ("C", "Focus ROI (Zoom)", 30, align_center),
            ("D", "Full Overview", 28, align_center),
            ("E", "Field", 15, align_left),
            ("F", "Tag", 8, align_center),
            ("G", "Extracted Characters", 28, align_left),
            ("H", "New Filename", 30, align_left),
            ("I", "Status", 15, align_center),
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
        # Cell display limits inside Excel (points)
        disp_roi_w, disp_roi_h = 205, 66
        disp_full_w, disp_full_h = 190, 66
        # High-DPI render limits (2x Retina density for razor-sharp text)
        render_roi_w, render_roi_h = disp_roi_w * 2, disp_roi_h * 2
        render_full_w, render_full_h = disp_full_w * 2, disp_full_h * 2

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

            # Set Excel Row Height to fit high-DPI images cleanly (74 pt)
            ws.row_dimensions[current_excel_row].height = 74

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

            # Col C: Focus ROI (Zoomed text crop with padded highlight box)
            c_c = ws[f"C{current_excel_row}"]
            c_c.value = ""
            c_c.fill = row_fill
            c_c.alignment = align_center
            c_c.border = cell_border

            # Col D: Full Overview (Full image with padded bounding box)
            c_d = ws[f"D{current_excel_row}"]
            c_d.value = ""
            c_d.fill = row_fill
            c_d.alignment = align_center
            c_d.border = cell_border

            full_img_path = os.path.join(folder_path, orig_filename)
            if os.path.isfile(full_img_path):
                try:
                    with Image.open(full_img_path) as raw_img:
                        img_rgb = raw_img.convert("RGB")
                        orig_w, orig_h = img_rgb.size

                        # Highlight Box with PADDING (breathable margins so lines never touch characters)
                        hl_box = None
                        if bbox and len(bbox) == 4:
                            bx1, by1, bx2, by2 = bbox
                            bw = max(1, bx2 - bx1)
                            bh = max(1, by2 - by1)

                            # Box padding: 8% on X, 12% on Y (minimum 5px / 4px)
                            pad_box_x = max(5, int(bw * 0.08))
                            pad_box_y = max(4, int(bh * 0.12))
                            hl_x1 = max(0, bx1 - pad_box_x)
                            hl_y1 = max(0, by1 - pad_box_y)
                            hl_x2 = min(orig_w, bx2 + pad_box_x)
                            hl_y2 = min(orig_h, by2 + pad_box_y)
                            hl_box = [hl_x1, hl_y1, hl_x2, hl_y2]

                        # -------------------------------------------------------------
                        # IMAGE 1: FOCUS ROI (Col C)
                        # -------------------------------------------------------------
                        if hl_box:
                            # Context crop margins (35% on X, 45% on Y for clear surroundings)
                            pad_crop_x = max(35, int(bw * 0.35))
                            pad_crop_y = max(22, int(bh * 0.45))
                            cx1 = max(0, bx1 - pad_crop_x)
                            cy1 = max(0, by1 - pad_crop_y)
                            cx2 = min(orig_w, bx2 + pad_crop_x)
                            cy2 = min(orig_h, by2 + pad_crop_y)

                            crop_img = img_rgb.crop((cx1, cy1, cx2, cy2))
                            cw, ch = crop_img.size

                            # Draw glowing focus border around detected text on crop with padding
                            draw_crop = ImageDraw.Draw(crop_img)
                            tb_x1 = max(0, hl_box[0] - cx1)
                            tb_y1 = max(0, hl_box[1] - cy1)
                            tb_x2 = min(cw, hl_box[2] - cx1)
                            tb_y2 = min(ch, hl_box[3] - cy1)

                            # Double-layer neon outline (Blue outer, Emerald inner)
                            draw_crop.rectangle([tb_x1 - 1, tb_y1 - 1, tb_x2 + 1, tb_y2 + 1], outline="#0284c7", width=2)
                            draw_crop.rectangle([tb_x1, tb_y1, tb_x2, tb_y2], outline="#10b981", width=2)

                            # 2x Retina Lanczos Resampling
                            scale_roi = min(render_roi_w / cw, render_roi_h / ch)
                            roi_w = max(1, int(round(cw * scale_roi)))
                            roi_h = max(1, int(round(ch * scale_roi)))
                            thumb_roi = crop_img.resize((roi_w, roi_h), Image.Resampling.LANCZOS)

                            thumb_roi_fn = f"roi_{idx}_{orig_filename}.png"
                            thumb_roi_p = os.path.join(temp_dir, thumb_roi_fn)
                            thumb_roi.save(thumb_roi_p, format="PNG", optimize=True)

                            xl_roi = OpenpyxlImage(thumb_roi_p)
                            # Display at 1/2 render resolution for crisp 2x Retina density
                            xl_roi.width = int(round(roi_w / 2.0))
                            xl_roi.height = int(round(roi_h / 2.0))
                            ws.add_image(xl_roi, f"C{current_excel_row}")
                        else:
                            c_c.value = "(No ROI - Empty)"
                            c_c.font = font_no_roi

                        # -------------------------------------------------------------
                        # IMAGE 2: FULL OVERVIEW (Col D)
                        # -------------------------------------------------------------
                        full_copy = img_rgb.copy()
                        if hl_box:
                            draw_full = ImageDraw.Draw(full_copy)
                            # Scaled highlight line width based on image size
                            lw = max(3, int(min(orig_w, orig_h) / 130))
                            draw_full.rectangle(
                                [hl_box[0] - 1, hl_box[1] - 1, hl_box[2] + 1, hl_box[3] + 1],
                                outline="#0284c7", width=lw + 1
                            )
                            draw_full.rectangle(hl_box, outline="#10b981", width=lw)

                        scale_full = min(render_full_w / orig_w, render_full_h / orig_h)
                        full_w = max(1, int(round(orig_w * scale_full)))
                        full_h = max(1, int(round(orig_h * scale_full)))
                        thumb_full = full_copy.resize((full_w, full_h), Image.Resampling.LANCZOS)

                        thumb_full_fn = f"full_{idx}_{orig_filename}.png"
                        thumb_full_p = os.path.join(temp_dir, thumb_full_fn)
                        thumb_full.save(thumb_full_p, format="PNG", optimize=True)

                        xl_full = OpenpyxlImage(thumb_full_p)
                        xl_full.width = int(round(full_w / 2.0))
                        xl_full.height = int(round(full_h / 2.0))
                        ws.add_image(xl_full, f"D{current_excel_row}")

                except Exception as e:
                    c_c.value = f"(Error: {e})"
                    c_c.font = font_meta
                    c_d.value = f"(Error: {e})"
                    c_d.font = font_meta
            else:
                c_c.value = "(File not found)"
                c_c.font = font_meta
                c_d.value = "(File not found)"
                c_d.font = font_meta

            # Col E: Field
            c_e = ws[f"E{current_excel_row}"]
            c_e.value = field_name
            c_e.font = font_cell_bold
            c_e.fill = row_fill
            c_e.alignment = align_left
            c_e.border = cell_border

            # Col F: Tag
            c_f = ws[f"F{current_excel_row}"]
            c_f.value = var_tag
            c_f.font = font_cell
            c_f.fill = row_fill
            c_f.alignment = align_center
            c_f.border = cell_border

            # Col G: Extracted Characters
            c_g = ws[f"G{current_excel_row}"]
            c_g.value = ocr_text if ocr_text else "(Empty)"
            c_g.font = font_cell_bold if ocr_text else font_empty
            c_g.fill = row_fill
            c_g.alignment = align_left
            c_g.border = cell_border

            # Col H: New Filename
            c_h = ws[f"H{current_excel_row}"]
            c_h.value = new_name
            c_h.font = font_cell
            c_h.fill = row_fill
            c_h.alignment = align_left
            c_h.border = cell_border

            # Col I: Status
            c_i = ws[f"I{current_excel_row}"]
            c_i.value = status_text
            c_i.font = font_cell_bold
            c_i.fill = status_fill
            c_i.alignment = align_center
            c_i.border = cell_border

            current_excel_row += 1

        # Enable AutoFilter on Table (A4:I{last_row})
        ws.auto_filter.ref = f"A{hdr_row}:I{current_excel_row - 1}"

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
