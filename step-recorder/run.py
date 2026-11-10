#!/usr/bin/env python3
"""
Entry point for Python Step Recorder.
Supports native Windows, Linux, macOS, and seamless WSL -> Windows Host execution.
"""

import sys
import os
import shutil
import subprocess

# Ensure UTF-8 stdout/stderr on Windows to avoid UnicodeEncodeError with emojis
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)


def is_wsl() -> bool:
    """Check if currently running inside Windows Subsystem for Linux (WSL)."""
    if sys.platform != "linux":
        return False
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def maybe_forward_to_windows() -> bool:
    """
    If running inside WSL, WSLg cannot capture clicks on native Windows apps
    (Chrome, VS Code, Explorer, etc.).
    Forward to Windows Python host so all clicks and screens are recorded.
    """
    if "--linux" in sys.argv:
        sys.argv.remove("--linux")
        return False

    if is_wsl() and shutil.which("powershell.exe"):
        try:
            win_path = subprocess.check_output(
                ["wslpath", "-w", CURRENT_DIR], text=True
            ).strip()

            args_str = " ".join(f'"{a}"' for a in sys.argv[1:])

            print("=" * 68)
            print("🎬 PYTHON STEP RECORDER (WSL -> Windows Host Bridge)")
            print("=" * 68)
            print("💡 Đang khởi chạy Step Recorder trên Windows Host để ghi nhận mọi click...")
            print("   (Thêm cờ '--linux' nếu bạn chỉ muốn chạy nội bộ trong Linux VM)")
            print("=" * 68)

            ps_cmd = f"Set-Location '{win_path}'; python run.py {args_str}"
            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                stdin=subprocess.DEVNULL
            )
            return True
        except Exception as e:
            print(f"⚠️ Chuyển tiếp Windows không thành công: {e}. Đang chạy trên Linux...")
            return False

    return False


def main():
    if maybe_forward_to_windows():
        return

    try:
        from step_recorder.cli import main as cli_main
        cli_main()
    except ModuleNotFoundError as e:
        print("=" * 68)
        print(f"❌ Thiếu thư viện phụ thuộc: {e}")
        print("💡 Vui lòng cài đặt các thư viện cần thiết:")
        print("   pip install -r requirements.txt")
        print("=" * 68)
        sys.exit(1)


if __name__ == "__main__":
    main()
