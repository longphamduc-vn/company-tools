#!/usr/bin/env python3
"""
Main Entry Point for LGD Drawing Vault - Batch Blueprint Downloader & Viewer.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lgd_vault.config import DEFAULT_DOWNLOAD_DIR
from lgd_vault.models import DrawingItem
from lgd_vault.session_manager import SessionManager
from lgd_vault.sso_client import SSOClient
from lgd_vault.drawing_service import DrawingService


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_gui():
    """Launch the Batch Blueprint Viewer GUI."""
    from lgd_vault.viewer_app import launch_gui
    launch_gui()


def cmd_auth(force: bool = False):
    """Authenticate or test connection with local SSO agent on port 28083."""
    mgr = SessionManager()
    client = SSOClient(session_manager=mgr)

    info = mgr.get_session_info()
    if info.get("valid") and not force:
        print("✅ Current SSO session is active and valid:")
        print(f"   Remaining Time: {info.get('remaining_seconds')} seconds")
        print(f"   Cookies: {', '.join(info.get('cookies', []))}")
        return

    print("🔄 Connecting to SSO Local Agent on port 28083 (ws://127.0.0.1:28083/)...")
    try:
        cookies = client.authenticate()
        print("✅ Successfully authenticated via SSO!")
        print(f"   Cookies saved: {list(cookies.keys())}")
    except Exception as e:
        print(f"❌ SSO Authentication failed: {e}")
        sys.exit(1)


def cmd_download(qcode: str, custom_name: str, download_dir: str):
    """Single drawing download via CLI."""
    print(f"📥 Downloading drawing for QCode: {qcode} (Alias: {custom_name or 'None'})...")
    service = DrawingService()
    item = DrawingItem(qcode=qcode, custom_name=custom_name)
    result = service.process_item(item, download_dir=download_dir)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


def cmd_batch(file_path: str, download_dir: str):
    """Batch download from text, csv, or json file."""
    if not os.path.isfile(file_path):
        print(f"❌ File not found: {file_path}")
        sys.exit(1)

    items = []
    if file_path.endswith(".json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            raw_items = data.get("items", []) if isinstance(data, dict) else data
            for raw in raw_items:
                if isinstance(raw, dict) and raw.get("qcode"):
                    items.append(DrawingItem(qcode=raw["qcode"], custom_name=raw.get("custom_name", "")))
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split(",", 1)]
                qcode = parts[0]
                alias = parts[1] if len(parts) > 1 else ""
                items.append(DrawingItem(qcode=qcode, custom_name=alias))

    print(f"📥 Processing batch of {len(items)} item(s) from {file_path}...")
    service = DrawingService()

    def on_progress(cur, total, res):
        print(f"[{cur}/{total}] {res.qcode}: {res.status} ({res.file_name or 'No file'})")

    summary = service.execute_batch(items=items, download_dir=download_dir, progress_callback=on_progress)
    print("\n=== BATCH SUMMARY ===")
    print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="LGD Drawing Vault - Batch Blueprint Downloader & Image Viewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # GUI
    subparsers.add_parser("gui", help="Launch Batch Blueprint Viewer GUI")

    # Auth
    auth_p = subparsers.add_parser("auth", help="Check or re-authenticate SSO session")
    auth_p.add_argument("--force", action="store_true", help="Force new authentication even if valid")

    # Download Single
    dl_p = subparsers.add_parser("download", help="Download drawing by QCode")
    dl_p.add_argument("--qcode", required=True, help="Equipment QCode (e.g. QCAK09691)")
    dl_p.add_argument("--name", default="", help="Optional device alias name")
    dl_p.add_argument("--dir", default=DEFAULT_DOWNLOAD_DIR, help="Target download directory")

    # Batch Download
    batch_p = subparsers.add_parser("batch", help="Batch download drawings from file")
    batch_p.add_argument("--file", required=True, help="Path to .txt, .csv or .json batch file")
    batch_p.add_argument("--dir", default=DEFAULT_DOWNLOAD_DIR, help="Target download directory")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "gui":
        cmd_gui()
    elif args.command == "auth":
        cmd_auth(force=args.force)
    elif args.command == "download":
        cmd_download(args.qcode, args.name, args.dir)
    elif args.command == "batch":
        cmd_batch(args.file, args.dir)
    else:
        # Default fallback: Launch GUI if DISPLAY is available, otherwise show help
        if os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"):
            try:
                cmd_gui()
            except Exception as e:
                print(f"Could not open GUI ({e}). Use --help for command line options.")
                parser.print_help()
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
