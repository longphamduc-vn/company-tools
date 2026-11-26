"""Command-line interface and GUI launcher for Windows Disk Analyzer."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __app_name__, __version__
from .cleaner import SafeCleaner
from .diagnostics import WindowsDiagnostics
from .exporter import export_csv, export_html, export_json, export_markdown
from .formatters import format_bytes, format_duration, make_percent_bar, truncate_middle
from .models import DiagnosticSummary, SafetyLevel, ScanResult
from .scanner import DiskScanner


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="windows-disk-analyzer",
        description=f"{__app_name__} v{__version__} - Inspect and clean Windows disk space",
    )
    parser.add_argument("--cli", action="store_true", help="Run in command-line mode (no GUI)")
    parser.add_argument("--scan", metavar="PATH", help="Deep-scan a drive or folder (e.g., C:\\Users)")
    parser.add_argument("--fast", action="store_true", help="Fast audit mode (caps deep scan of WinSxS/Installer)")
    parser.add_argument("--top", type=int, default=20, help="Number of largest files/folders to show (default: 20)")
    parser.add_argument("--min-mb", type=float, default=10.0, help="Minimum file size in MB for top-files list (default: 10)")
    parser.add_argument("--clean-safe", action="store_true", help="Run safe cleanup (Dry-Run by default)")
    parser.add_argument("--execute", action="store_true", help="Actually delete SAFE items when used with --clean-safe")
    parser.add_argument("--export", metavar="FILE", help="Export report to .html, .md, .csv, or .json")
    parser.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _print_diagnostics(summary: DiagnosticSummary) -> None:
    print("=" * 78)
    print(f"  {__app_name__} v{__version__} | Host: {summary.computer_name}")
    print(f"  OS: {summary.os_version} | Admin: {'Yes' if summary.is_admin else 'No'}")
    print(f"  Storage Health Score: {summary.health_score}/100 | Safe Reclaimable: {format_bytes(summary.reclaimable_safe_bytes)}")
    print("=" * 78)
    print("\n[1] DRIVE STATUS:")
    for d in summary.drives:
        if not d.is_ready:
            print(f"  - {d.letter:<4} ({d.drive_type}): Not ready")
            continue
        bar = make_percent_bar(d.used_percent, width=14)
        print(
            f"  - {d.letter:<3} [{d.label:<12}] {bar}  "
            f"Free: {format_bytes(d.free_bytes):>10} / {format_bytes(d.total_bytes):>10} "
            f"[{d.status.value.upper()}]  Recycle Bin: {format_bytes(d.recycle_bin_bytes)}"
        )

    print("\n[2] PRIORITY RECOMMENDATIONS:")
    for rec in summary.recommendations:
        print(f"  * {rec}")

    print("\n[3] WINDOWS SPACE CONSUMERS:")
    for item in summary.items:
        if not item.exists and item.size_on_disk_bytes == 0 and not item.error:
            continue
        tag = item.safety.value.upper()
        clean_tag = "AutoClean" if item.can_auto_clean else "GuideOnly"
        size_col = "Admin Req." if (item.error and item.size_on_disk_bytes == 0 and item.file_count == 0) else format_bytes(item.size_on_disk_bytes)
        print(
            f"  - [{tag:<6} | {clean_tag:<9}] {size_col:>11}  "
            f"({item.file_count:>7,} files)  {item.name}"
        )


def _print_scan(scan: ScanResult, top_n: int) -> None:
    print("\n" + "=" * 78)
    print(f"  FOLDER SCAN RESULTS: {scan.target_path}")
    print(
        f"  Duration: {format_duration(scan.duration_sec)} | "
        f"Size on disk: {format_bytes(scan.total_disk_bytes)} | "
        f"Files: {scan.total_files:,} | Folders: {scan.total_dirs:,}"
    )
    print("=" * 78)

    if scan.root_node and scan.root_node.children:
        print(f"\n  TOP {min(top_n, len(scan.root_node.children))} LARGEST SUBFOLDERS:")
        denom = scan.total_disk_bytes or 1
        for child in scan.root_node.children[:top_n]:
            pct = (child.disk_bytes / denom) * 100.0
            print(
                f"  {format_bytes(child.disk_bytes):>11}  ({pct:5.1f}%)  "
                f"{child.file_count:>8,} files  {truncate_middle(child.path, 52)}"
            )

    if scan.top_files:
        print(f"\n  TOP {min(top_n, len(scan.top_files))} LARGEST FILES:")
        for fe in scan.top_files[:top_n]:
            cloud_note = " [Cloud]" if fe.is_cloud_only else ""
            print(
                f"  {format_bytes(fe.disk_bytes):>11}  {truncate_middle(fe.path, 62)}{cloud_note}"
            )

    if scan.extension_stats:
        print("\n  TOP FILE EXTENSIONS BY DISK USAGE:")
        for ext in scan.extension_stats[:12]:
            print(
                f"  {ext.extension:<12}  {format_bytes(ext.disk_bytes):>11}  ({ext.file_count:>8,} files)"
            )


def _export_by_extension(
    export_path: str,
    diag: Optional[DiagnosticSummary],
    scan: Optional[ScanResult],
) -> str:
    ext = os.path.splitext(export_path)[1].lower()
    if ext == ".json":
        return export_json(export_path, diagnostic=diag, scan=scan)
    if ext in (".md", ".markdown"):
        return export_markdown(export_path, diagnostic=diag, scan=scan)
    if ext == ".csv":
        return export_csv(export_path, diagnostic=diag, scan=scan)
    return export_html(export_path, diagnostic=diag, scan=scan)


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    run_cli = any([args.cli, args.scan, args.clean_safe, args.export, args.json])
    if not run_cli:
        from gui.main_window import launch_gui
        launch_gui()
        return 0

    diag_engine = WindowsDiagnostics()
    diag_summary = diag_engine.run_audit(skip_heavy_system_dirs=args.fast)

    scan_result: Optional[ScanResult] = None
    if args.scan:
        if not os.path.exists(args.scan):
            print(f"Error: Path not found: '{args.scan}'", file=sys.stderr)
            return 2
        scanner = DiskScanner(
            top_n_files=max(args.top, 50),
            min_top_file_bytes=int(max(0.0, args.min_mb) * 1024 * 1024),
        )
        scan_result = scanner.scan(args.scan)

    if args.clean_safe:
        safe_items = [
            i for i in diag_summary.items
            if i.safety == SafetyLevel.SAFE and i.can_auto_clean and i.exists
        ]
        cleaner = SafeCleaner()
        dry_run = not args.execute
        clean_res = cleaner.clean_diagnostic_items(safe_items, dry_run=dry_run, use_recycle_bin=False)
        mode_lbl = "DRY-RUN (Simulation)" if dry_run else "EXECUTED"
        print(f"\n[SAFE CLEANUP - {mode_lbl}]")
        print(
            f"  Reclaimable/Freed: {format_bytes(clean_res.total_freed_bytes)} | "
            f"Files: {clean_res.total_deleted_files:,} | Skipped (locked): {clean_res.total_skipped_files:,}"
        )
        if dry_run:
            print("  (Pass --execute to actually remove SAFE items)")

    if args.json:
        payload = {
            "diagnostic": diag_summary.to_dict(),
            "scan": scan_result.to_dict() if scan_result else None,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_diagnostics(diag_summary)
        if scan_result:
            _print_scan(scan_result, top_n=args.top)

    if args.export:
        saved = _export_by_extension(args.export, diag_summary, scan_result)
        print(f"\nReport exported to: {saved}")

    return 0
