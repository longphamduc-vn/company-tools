#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python Builder for Lightweight Standalone Executable.
Can be executed directly on Windows or cross-invoked from WSL:
    python build_exe.py
"""

import os
import sys
import shutil
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SPEC_FILE = os.path.join(PROJECT_DIR, "image_batch_translator.spec")


def check_and_install_pyinstaller():
    try:
        import PyInstaller
        print(f"[*] PyInstaller {PyInstaller.__version__} detected.")
    except ImportError:
        print("[*] PyInstaller not detected. Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller", "--quiet"])


def run_build():
    print("=" * 70)
    print("    COMPILING LIGHTWEIGHT STANDALONE EXECUTABLE (.EXE)")
    print("=" * 70)
    print(f"[*] Working Directory : {PROJECT_DIR}")
    print(f"[*] Python Interpreter: {sys.executable} ({sys.version.split()[0]})")
    print(f"[*] Spec File         : {SPEC_FILE}")
    print()

    check_and_install_pyinstaller()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        SPEC_FILE,
        "--clean",
        "--noconfirm",
    ]

    print(f"[*] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_DIR)

    if result.returncode != 0:
        print(f"\n[ERROR] Build failed with return code {result.returncode}")
        sys.exit(result.returncode)

    # Check output
    exe_name = "SmartBatchExtractor.exe" if sys.platform == "win32" else "SmartBatchExtractor"
    dist_path = os.path.join(PROJECT_DIR, "dist", exe_name)

    if os.path.isfile(dist_path):
        size_bytes = os.path.getsize(dist_path)
        size_mb = size_bytes / (1024 * 1024)
        print("\n" + "=" * 70)
        print("  🎉 BUILD SUCCESSFUL!")
        print(f"  Target File : {dist_path}")
        print(f"  File Size   : {size_mb:.2f} MB ({size_bytes:,} bytes)")
        print("=" * 70)
        print("  Standalone executable is ready for distribution without dependencies!\n")
    else:
        print(f"\n[WARNING] Build finished but {dist_path} not found.")


if __name__ == "__main__":
    run_build()
