# Windows Disk Analyzer

A standalone desktop and CLI utility to diagnose **Windows low-disk-space issues**, visualize folder sizes with an interactive treemap, locate oversized files, and safely reclaim storage — built with pure Python 3.10+, Tkinter, and native Win32 APIs (zero external runtime dependencies).

---

## Key Features

1. **Drive Health Overview & Windows Space Audit**:
   - Inspects all logical drives (`C:\`, `D:\`, etc.) with status alerts (`HEALTHY`, `WARNING`, `CRITICAL`) and per-drive Recycle Bin usage.
   - Computes a Storage Health Score (`0-100`) and prioritizes actionable recommendations.
   - Audits 20+ common Windows space hogs:
     - **Temp & Caches**: `%TEMP%`, `C:\Windows\Temp`, Explorer Thumbnail/Icon Cache, Windows Error Reporting (`WER`), Recycle Bin (`SHQueryRecycleBinW`).
     - **Windows Update & Upgrades**: `SoftwareDistribution\Download`, Delivery Optimization Cache, `Windows.old`, `$WINDOWS.~BT`.
     - **Logs & Crash Dumps**: `Minidump`, `MEMORY.DMP`, `CrashDumps`, `C:\Windows\Logs`, `Prefetch`.
     - **Apps & Browsers**: Chrome, Edge, Firefox, Brave caches; Teams, Zalo, Slack, Zoom caches; Outlook `.ost/.pst`; `Downloads`.
     - **Dev & Virtualization**: WSL2/Docker `.vhdx` virtual disks, package caches (`pip`, `npm`, `yarn`, `pnpm`, `NuGet`, `Gradle`, `Maven`, `Cargo`, `HuggingFace`).
     - **Windows System Files**: Locked files (`hiberfil.sys`, `pagefile.sys`, `swapfile.sys` via `FindFirstFileW`), `WinSxS`, `C:\Windows\Installer`, and Shadow Copies (`vssadmin list shadowstorage`).

2. **Folder Tree & Interactive Treemap**:
   - Fast recursive scanner via `os.scandir` with instant cancellation and live progress.
   - **NTFS Junction / Symlink Safe**: Prevents infinite loops and double-counting on Windows junctions (e.g., `Documents and Settings`, `Application Data`).
   - **OneDrive Cloud-Only Aware**: Reports `0 B` on disk for cloud-only placeholders (`FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS`) separately from logical size.
   - Interactive **Treemap** canvas with hover inspection and click-to-drill-down navigation.

3. **Largest Files Finder & Extension Breakdown**:
   - Filter top files by keyword, minimum size (`1 MB` - `1024 MB`), file category (`.vhdx/.iso`, `.zip/.7z`, videos, `.exe/.msi`, `.log/.dmp`, `.ost/.pst`), and age (`> 30` to `> 365 days`).
   - Move selected files safely to the Windows Recycle Bin.

4. **Safe Cleanup & Report Exports**:
   - Categorizes findings into **Safe**, **Review**, and **System** levels.
   - Supports **Dry-Run** preview, optional Recycle Bin routing, locked-file skipping, and critical-path protection guards.
   - Exports reports to **HTML**, **Markdown**, **CSV**, and **JSON**.

---

## Quick Start

### Run Standalone Executable
Double-click `dist\WindowsDiskAnalyzer.exe` (after building or downloading).

### Run From Source (GUI)
Double-click `run_app.bat` or run:
```cmd
python main.py
```

### Run via CLI
```cmd
:: Quick drive & Windows bloat audit
python main.py --cli

:: Deep scan a path and show top 25 files >= 50 MB
python main.py --cli --scan C:\Users --min-mb 50 --top 25

:: Preview safe cleanup (Dry-Run)
python main.py --cli --clean-safe

:: Execute safe cleanup
python main.py --cli --clean-safe --execute

:: Export report (HTML, Markdown, CSV, or JSON)
python main.py --cli --scan C:\Users --export disk_report.html
```

---

## Build Standalone Windows EXE

Run `scripts\build_exe.bat` (creates `.build_venv`, installs PyInstaller, and outputs `dist\WindowsDiskAnalyzer.exe`).

---

## Run Unit Tests

```cmd
python -m unittest discover -s tests -v
```
