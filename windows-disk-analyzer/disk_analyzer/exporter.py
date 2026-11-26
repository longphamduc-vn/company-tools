"""Report exporters (HTML dashboard, JSON, Markdown, CSV) for diagnostics and folder scans."""

from __future__ import annotations

import csv
import html
import json
import os
from typing import Optional

from .formatters import format_bytes, format_duration, format_timestamp
from .models import DiagnosticSummary, DriveStatus, SafetyLevel, ScanResult


def export_json(
    output_path: str,
    diagnostic: Optional[DiagnosticSummary] = None,
    scan: Optional[ScanResult] = None,
) -> str:
    payload = {
        "diagnostic": diagnostic.to_dict() if diagnostic else None,
        "scan": scan.to_dict() if scan else None,
    }
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return os.path.abspath(output_path)


def export_csv(
    output_path: str,
    diagnostic: Optional[DiagnosticSummary] = None,
    scan: Optional[ScanResult] = None,
) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        if diagnostic:
            writer.writerow(["=== WINDOWS STORAGE DIAGNOSTICS ==="])
            writer.writerow([
                "ID",
                "Item Name",
                "Category",
                "Safety Level",
                "Size on Disk",
                "Logical Size",
                "File Count",
                "Auto Cleanable",
                "Paths",
                "Recommendation",
            ])
            for item in diagnostic.items:
                writer.writerow([
                    item.item_id,
                    item.name,
                    item.category,
                    item.safety.value,
                    format_bytes(item.size_on_disk_bytes),
                    format_bytes(item.total_bytes),
                    item.file_count,
                    "Yes" if item.can_auto_clean else "No",
                    " | ".join(item.paths),
                    item.recommended_action,
                ])
            writer.writerow([])

        if scan:
            writer.writerow([f"=== LARGEST FILES ({scan.target_path}) ==="])
            writer.writerow(["File Name", "Extension", "Size on Disk", "Logical Size", "Modified", "Full Path"])
            for f in scan.top_files:
                writer.writerow([
                    f.name,
                    f.extension,
                    format_bytes(f.disk_bytes),
                    format_bytes(f.logical_bytes),
                    format_timestamp(f.modified_ts, include_time=True),
                    f.path,
                ])
    return os.path.abspath(output_path)


def export_markdown(
    output_path: str,
    diagnostic: Optional[DiagnosticSummary] = None,
    scan: Optional[ScanResult] = None,
) -> str:
    lines = ["# Windows Disk Space Diagnostic Report", ""]

    if diagnostic:
        lines.extend([
            f"- **Computer:** `{diagnostic.computer_name}`",
            f"- **Operating System:** {diagnostic.os_version}",
            f"- **Generated At:** {diagnostic.generated_at}",
            f"- **Administrator Privileges:** {'Yes' if diagnostic.is_admin else 'No (Standard User)'}",
            f"- **Storage Health Score:** **{diagnostic.health_score}/100**",
            f"- **Safe Reclaimable Now:** **{format_bytes(diagnostic.reclaimable_safe_bytes)}**",
            "",
            "## 1. Drive Status",
            "",
            "| Drive | Label | Total | Used | Free | % Free | Status | Recycle Bin |",
            "| :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |",
        ])
        for d in diagnostic.drives:
            if not d.is_ready:
                lines.append(f"| {d.letter} | {d.label or '-'} | - | - | - | - | Not Ready | - |")
            else:
                lines.append(
                    f"| {d.letter} | {d.label} | {format_bytes(d.total_bytes)} | "
                    f"{format_bytes(d.used_bytes)} | {format_bytes(d.free_bytes)} | "
                    f"{d.free_percent:.1f}% | {d.status.value.upper()} | {format_bytes(d.recycle_bin_bytes)} |"
                )

        lines.extend(["", "## 2. Priority Recommendations", ""])
        for rec in diagnostic.recommendations:
            lines.append(f"- {rec}")

        lines.extend([
            "",
            "## 3. Windows Space Consumers Breakdown",
            "",
            "| Item | Category | Safety | Size on Disk | Files | Recommended Action |",
            "| :--- | :--- | :--- | ---: | ---: | :--- |",
        ])
        for item in diagnostic.items:
            if not item.exists and item.size_on_disk_bytes == 0 and not item.error:
                continue
            sz_txt = "Admin Req." if (item.error and item.size_on_disk_bytes == 0 and item.file_count == 0) else format_bytes(item.size_on_disk_bytes)
            lines.append(
                f"| {item.name} | {item.category} | {item.safety.value.upper()} | "
                f"{sz_txt} | {item.file_count:,} | {item.recommended_action} |"
            )
        lines.append("")

    if scan:
        lines.extend([
            f"## 4. Folder Scan Results: `{scan.target_path}`",
            "",
            f"- **Scan Duration:** {format_duration(scan.duration_sec)}",
            f"- **Total Size on Disk:** {format_bytes(scan.total_disk_bytes)} (Logical: {format_bytes(scan.total_logical_bytes)})",
            f"- **Counts:** {scan.total_files:,} files / {scan.total_dirs:,} folders",
            "",
        ])
        if scan.root_node and scan.root_node.children:
            lines.extend([
                "### Largest Subfolders",
                "",
                "| Folder | Size on Disk | Files | Share |",
                "| :--- | ---: | ---: | ---: |",
            ])
            denom = scan.total_disk_bytes or 1
            for child in scan.root_node.children[:20]:
                pct = (child.disk_bytes / denom) * 100.0
                lines.append(
                    f"| `{child.path}` | {format_bytes(child.disk_bytes)} | {child.file_count:,} | {pct:.1f}% |"
                )
            lines.append("")

        if scan.top_files:
            lines.extend([
                "### Largest Files",
                "",
                "| File | Size | Modified | Full Path |",
                "| :--- | ---: | :--- | :--- |",
            ])
            for f in scan.top_files[:30]:
                lines.append(
                    f"| {f.name} | {format_bytes(f.disk_bytes)} | {format_timestamp(f.modified_ts)} | `{f.path}` |"
                )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return os.path.abspath(output_path)


def export_html(
    output_path: str,
    diagnostic: Optional[DiagnosticSummary] = None,
    scan: Optional[ScanResult] = None,
) -> str:
    """Export a standalone styled HTML diagnostic report."""
    esc = html.escape
    sections = []

    if diagnostic:
        score_color = "#16a34a" if diagnostic.health_score >= 80 else ("#d97706" if diagnostic.health_score >= 55 else "#dc2626")
        drive_cards = []
        for d in diagnostic.drives:
            if not d.is_ready:
                continue
            bar_color = "#dc2626" if d.status == DriveStatus.CRITICAL else ("#d97706" if d.status == DriveStatus.WARNING else "#0284c7")
            drive_cards.append(f"""
            <div class="card">
              <div class="row-between">
                <strong>Drive {esc(d.letter)} ({esc(d.label)})</strong>
                <span class="badge" style="background:{bar_color}">{esc(d.status.value.upper())}</span>
              </div>
              <div class="meta">{esc(d.drive_type)} &bull; {esc(d.filesystem)} &bull; Total: {esc(format_bytes(d.total_bytes))}</div>
              <div class="progress-bg"><div class="progress-fill" style="width:{min(100.0, d.used_percent):.1f}%;background:{bar_color}"></div></div>
              <div class="row-between small">
                <span>Used: <b>{esc(format_bytes(d.used_bytes))}</b> ({d.used_percent:.1f}%)</span>
                <span>Free: <b>{esc(format_bytes(d.free_bytes))}</b> ({d.free_percent:.1f}%)</span>
              </div>
            </div>""")

        rec_items = "".join(f"<li>{esc(r)}</li>" for r in diagnostic.recommendations)
        diag_rows = []
        for item in diagnostic.items:
            if not item.exists and item.size_on_disk_bytes == 0 and not item.error:
                continue
            badge_bg = "#16a34a" if item.safety == SafetyLevel.SAFE else ("#d97706" if item.safety == SafetyLevel.REVIEW else "#475569")
            sz_txt = "Admin Req." if (item.error and item.size_on_disk_bytes == 0 and item.file_count == 0) else format_bytes(item.size_on_disk_bytes)
            diag_rows.append(f"""
            <tr>
              <td><b>{esc(item.name)}</b><br><span class="muted">{esc(item.description)}</span></td>
              <td>{esc(item.category)}</td>
              <td><span class="badge" style="background:{badge_bg}">{esc(item.safety.value.upper())}</span></td>
              <td class="num"><b>{esc(sz_txt)}</b></td>
              <td class="num">{item.file_count:,}</td>
              <td>{esc(item.recommended_action)}</td>
            </tr>""")

        sections.append(f"""
        <div class="summary-grid">
          <div class="kpi"><div class="kpi-label">Computer Name</div><div class="kpi-val">{esc(diagnostic.computer_name)}</div></div>
          <div class="kpi"><div class="kpi-label">Health Score</div><div class="kpi-val" style="color:{score_color}">{diagnostic.health_score}/100</div></div>
          <div class="kpi"><div class="kpi-label">Safe to Reclaim</div><div class="kpi-val" style="color:#16a34a">{esc(format_bytes(diagnostic.reclaimable_safe_bytes))}</div></div>
          <div class="kpi"><div class="kpi-label">Generated At</div><div class="kpi-val" style="font-size:15px">{esc(diagnostic.generated_at)}</div></div>
        </div>
        <h2>1. Drive Status</h2>
        <div class="drive-grid">{''.join(drive_cards)}</div>
        <h2>2. Priority Recommendations</h2>
        <ul class="recs">{rec_items}</ul>
        <h2>3. Windows Storage Breakdown</h2>
        <table>
          <thead><tr><th>Item</th><th>Category</th><th>Safety</th><th>Size on Disk</th><th>Files</th><th>Recommended Action</th></tr></thead>
          <tbody>{''.join(diag_rows)}</tbody>
        </table>""")

    if scan:
        folder_rows = []
        if scan.root_node:
            denom = scan.total_disk_bytes or 1
            for child in scan.root_node.children[:25]:
                pct = (child.disk_bytes / denom) * 100.0
                folder_rows.append(
                    f"<tr><td><code>{esc(child.path)}</code></td><td class='num'><b>{esc(format_bytes(child.disk_bytes))}</b></td>"
                    f"<td class='num'>{child.file_count:,}</td><td class='num'>{pct:.1f}%</td></tr>"
                )
        file_rows = []
        for f in scan.top_files[:50]:
            file_rows.append(
                f"<tr><td><b>{esc(f.name)}</b></td><td>{esc(f.extension)}</td>"
                f"<td class='num'><b>{esc(format_bytes(f.disk_bytes))}</b></td>"
                f"<td>{esc(format_timestamp(f.modified_ts))}</td><td><code>{esc(f.path)}</code></td></tr>"
            )
        sections.append(f"""
        <h2>4. Folder Scan: <code>{esc(scan.target_path)}</code></h2>
        <p class="muted">Duration: {esc(format_duration(scan.duration_sec))} &bull; Size on disk: <b>{esc(format_bytes(scan.total_disk_bytes))}</b> &bull; {scan.total_files:,} files / {scan.total_dirs:,} folders</p>
        <h3>Largest Subfolders</h3>
        <table><thead><tr><th>Folder</th><th>Size on Disk</th><th>Files</th><th>Share</th></tr></thead><tbody>{''.join(folder_rows)}</tbody></table>
        <h3>Largest Files</h3>
        <table><thead><tr><th>File Name</th><th>Ext</th><th>Size on Disk</th><th>Modified</th><th>Full Path</th></tr></thead><tbody>{''.join(file_rows)}</tbody></table>""")

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Windows Disk Analyzer Report</title>
<style>
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f8fafc; color: #1e293b; margin: 0; padding: 24px; }}
  .wrap {{ max-width: 1200px; margin: 0 auto; }}
  header {{ background: #0f172a; color: #f8fafc; padding: 20px 24px; border-radius: 10px; margin-bottom: 20px; }}
  header h1 {{ margin: 0 0 4px 0; font-size: 22px; }}
  header p {{ margin: 0; color: #94a3b8; font-size: 13px; }}
  .summary-grid, .drive-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; margin-bottom: 20px; }}
  .kpi, .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 16px; }}
  .kpi-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; }}
  .kpi-val {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
  .row-between {{ display: flex; justify-content: space-between; align-items: center; }}
  .small {{ font-size: 13px; margin-top: 6px; }}
  .meta {{ font-size: 12px; color: #64748b; margin: 4px 0 8px 0; }}
  .progress-bg {{ height: 10px; background: #e2e8f0; border-radius: 5px; overflow: hidden; }}
  .progress-fill {{ height: 100%; }}
  .badge {{ color: #fff; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; }}
  .recs {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 28px; }}
  .recs li {{ margin: 6px 0; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; margin-bottom: 22px; }}
  th, td {{ padding: 10px 12px; border-bottom: 1px solid #e2e8f0; text-align: left; vertical-align: top; font-size: 13px; }}
  th {{ background: #f1f5f9; font-weight: 600; }}
  td.num, th.num {{ text-align: right; white-space: nowrap; }}
  .muted {{ color: #64748b; font-size: 12px; }}
  code {{ background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Windows Disk Analyzer &mdash; Storage Report</h1>
    <p>Diagnose Windows low-disk-space causes, inspect folder usage, and identify large files</p>
  </header>
  {''.join(sections)}
</div>
</body>
</html>"""

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return os.path.abspath(output_path)
