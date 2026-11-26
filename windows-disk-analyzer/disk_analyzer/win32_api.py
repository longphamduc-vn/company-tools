"""Safe Win32 ctypes wrappers and cross-platform fallbacks for disk analysis."""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import stat
import subprocess
import sys
from typing import List, Optional, Tuple

from .models import DriveInfo, DriveStatus, VssStorageInfo

# Win32 File Attribute constants
FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_SPARSE_FILE = 0x0200
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000

# Drive type map from GetDriveTypeW
_DRIVE_TYPE_LABELS = {
    0: "Unknown",
    1: "No Root",
    2: "Removable",
    3: "Local Disk",
    4: "Network",
    5: "CD-ROM",
    6: "RAM Disk",
}

if sys.platform.startswith("win"):
    from ctypes import wintypes

    _kernel32 = ctypes.windll.kernel32
    _shell32 = ctypes.windll.shell32

    _INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
    _INVALID_FILE_SIZE = 0xFFFFFFFF

    _kernel32.GetLogicalDrives.restype = wintypes.DWORD
    _kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetDriveTypeW.restype = wintypes.UINT

    _kernel32.GetVolumeInformationW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    _kernel32.GetVolumeInformationW.restype = wintypes.BOOL

    _kernel32.GetDiskFreeSpaceExW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64),
    ]
    _kernel32.GetDiskFreeSpaceExW.restype = wintypes.BOOL

    _kernel32.FindFirstFileW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p]
    _kernel32.FindFirstFileW.restype = wintypes.HANDLE
    _kernel32.FindClose.argtypes = [wintypes.HANDLE]
    _kernel32.FindClose.restype = wintypes.BOOL

    _kernel32.GetCompressedFileSizeW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.GetCompressedFileSizeW.restype = wintypes.DWORD

    class _WIN32_FIND_DATAW(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("dwReserved0", wintypes.DWORD),
            ("dwReserved1", wintypes.DWORD),
            ("cFileName", wintypes.WCHAR * 260),
            ("cAlternateFileName", wintypes.WCHAR * 14),
        ]

    class _SHQUERYRBINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("i64Size", ctypes.c_int64),
            ("i64NumItems", ctypes.c_int64),
        ]

    class _SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    _shell32.SHQueryRecycleBinW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(_SHQUERYRBINFO)]
    _shell32.SHQueryRecycleBinW.restype = ctypes.HRESULT

    _shell32.SHEmptyRecycleBinW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.DWORD]
    _shell32.SHEmptyRecycleBinW.restype = ctypes.HRESULT

    _shell32.SHFileOperationW.argtypes = [ctypes.POINTER(_SHFILEOPSTRUCTW)]
    _shell32.SHFileOperationW.restype = ctypes.c_int

    _shell32.IsUserAnAdmin.restype = wintypes.BOOL


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_admin() -> bool:
    """Return True if running with elevated Administrator privileges."""
    if is_windows():
        try:
            return bool(_shell32.IsUserAnAdmin())
        except Exception:
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


def classify_drive_status(total_bytes: int, free_bytes: int) -> DriveStatus:
    """Determine drive health status from free space percentage and absolute free GB."""
    if total_bytes <= 0:
        return DriveStatus.UNREADY
    free_pct = (free_bytes / total_bytes) * 100.0
    free_gb = free_bytes / (1024 ** 3)
    if free_pct < 8.0 or free_gb < 10.0:
        return DriveStatus.CRITICAL
    if free_pct < 20.0 or free_gb < 25.0:
        return DriveStatus.WARNING
    return DriveStatus.HEALTHY


def query_recycle_bin(root_path: Optional[str] = None) -> Tuple[int, int]:
    """Return (size_bytes, item_count) for the Windows Recycle Bin."""
    if not is_windows():
        return (0, 0)
    try:
        info = _SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(_SHQUERYRBINFO)
        hr = _shell32.SHQueryRecycleBinW(root_path, ctypes.byref(info))
        if hr == 0:
            return (max(0, int(info.i64Size)), max(0, int(info.i64NumItems)))
    except Exception:
        pass
    return (0, 0)


def empty_recycle_bin(root_path: Optional[str] = None) -> Tuple[bool, str]:
    """Empty the Windows Recycle Bin silently."""
    if not is_windows():
        return (False, "Emptying the Recycle Bin is only supported on Windows.")
    # SHERB_NOCONFIRMATION (0x1) | SHERB_NOPROGRESSUI (0x2) | SHERB_NOSOUND (0x4)
    flags = 0x1 | 0x2 | 0x4
    try:
        hr = _shell32.SHEmptyRecycleBinW(None, root_path, flags)
        # S_OK (0) or E_UNEXPECTED (-2147418113) when already empty
        if hr == 0:
            return (True, "Recycle Bin emptied.")
        if hr in (-2147418113, -2147024894):
            return (True, "Recycle Bin is already empty.")
        return (False, f"SHEmptyRecycleBinW failed with HRESULT={hr:#x}")
    except Exception as exc:
        return (False, str(exc))


def send_to_recycle_bin(paths: List[str]) -> Tuple[bool, str]:
    """Move one or more files/folders to the Windows Recycle Bin via SHFileOperationW."""
    if not paths:
        return (True, "")
    if not is_windows():
        return (False, "Recycle Bin is only available on Windows.")
    existing = [os.path.abspath(p) for p in paths if os.path.exists(p)]
    if not existing:
        return (True, "")
    # pFrom must be double-null terminated
    p_from = "\0".join(existing) + "\0\0"
    op = _SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = 0x0003  # FO_DELETE
    op.pFrom = p_from
    op.pTo = None
    # FOF_SILENT (0x4) | FOF_NOCONFIRMATION (0x10) | FOF_ALLOWUNDO (0x40) | FOF_NOERRORUI (0x400)
    op.fFlags = 0x0004 | 0x0010 | 0x0040 | 0x0400
    try:
        res = _shell32.SHFileOperationW(ctypes.byref(op))
        if res == 0 and not op.fAnyOperationsAborted:
            return (True, "")
        return (False, f"SHFileOperationW returned error code {res}")
    except Exception as exc:
        return (False, str(exc))


def get_logical_drives() -> List[DriveInfo]:
    """Enumerate all logical drives on Windows (or '/' on POSIX) with health metrics."""
    if not is_windows():
        usage = shutil.disk_usage("/")
        used_pct = (usage.used / usage.total * 100.0) if usage.total else 0.0
        free_pct = (usage.free / usage.total * 100.0) if usage.total else 0.0
        return [
            DriveInfo(
                letter="/",
                root_path="/",
                label="Root",
                drive_type="Local Disk",
                filesystem="POSIX",
                total_bytes=usage.total,
                used_bytes=usage.used,
                free_bytes=usage.free,
                used_percent=used_pct,
                free_percent=free_pct,
                status=classify_drive_status(usage.total, usage.free),
                is_system_drive=True,
                is_ready=True,
            )
        ]

    drives: List[DriveInfo] = []
    system_drive = os.environ.get("SystemDrive", "C:").upper().rstrip("\\")
    bitmask = _kernel32.GetLogicalDrives()

    for idx in range(26):
        if not (bitmask & (1 << idx)):
            continue
        letter = f"{chr(65 + idx)}:"
        root = f"{letter}\\"
        dtype_code = _kernel32.GetDriveTypeW(root)
        dtype_label = _DRIVE_TYPE_LABELS.get(dtype_code, "Unknown")

        vol_buf = ctypes.create_unicode_buffer(261)
        fs_buf = ctypes.create_unicode_buffer(261)
        vol_ok = _kernel32.GetVolumeInformationW(
            root, vol_buf, 261, None, None, None, fs_buf, 261
        )
        label = vol_buf.value.strip() if vol_ok else ""
        filesystem = fs_buf.value.strip() if vol_ok else ""

        free_avail = ctypes.c_uint64(0)
        total_bytes_c = ctypes.c_uint64(0)
        total_free_c = ctypes.c_uint64(0)
        space_ok = _kernel32.GetDiskFreeSpaceExW(
            root,
            ctypes.byref(free_avail),
            ctypes.byref(total_bytes_c),
            ctypes.byref(total_free_c),
        )

        if not space_ok or total_bytes_c.value == 0:
            drives.append(
                DriveInfo(
                    letter=letter,
                    root_path=root,
                    label=label,
                    drive_type=dtype_label,
                    filesystem=filesystem,
                    status=DriveStatus.UNREADY,
                    is_system_drive=(letter.upper() == system_drive),
                    is_ready=False,
                    error="Device is not ready or capacity cannot be read.",
                )
            )
            continue

        total = int(total_bytes_c.value)
        free = int(total_free_c.value)
        used = max(0, total - free)
        used_pct = (used / total) * 100.0 if total else 0.0
        free_pct = (free / total) * 100.0 if total else 0.0
        rb_size, rb_items = query_recycle_bin(root)

        drives.append(
            DriveInfo(
                letter=letter,
                root_path=root,
                label=label or ("System" if letter.upper() == system_drive else "Local Disk"),
                drive_type=dtype_label,
                filesystem=filesystem,
                total_bytes=total,
                used_bytes=used,
                free_bytes=free,
                used_percent=used_pct,
                free_percent=free_pct,
                status=classify_drive_status(total, free),
                recycle_bin_bytes=rb_size,
                recycle_bin_items=rb_items,
                is_system_drive=(letter.upper() == system_drive),
                is_ready=True,
            )
        )

    return drives


def is_reparse_or_junction(entry: os.DirEntry, st: Optional[os.stat_result] = None) -> bool:
    """Detect symlinks, NTFS junctions, and directory mount points to avoid double counting."""
    try:
        if entry.is_symlink():
            return True
    except OSError:
        return True

    is_junction_fn = getattr(entry, "is_junction", None)
    if callable(is_junction_fn):
        try:
            if is_junction_fn():
                return True
        except OSError:
            return True

    if st is not None:
        attrs = getattr(st, "st_file_attributes", 0)
        if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
            return True
    return False


def is_cloud_placeholder(st: os.stat_result) -> bool:
    """Detect OneDrive/cloud-only placeholder files that occupy negligible disk space."""
    attrs = getattr(st, "st_file_attributes", 0)
    if attrs & (FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | FILE_ATTRIBUTE_RECALL_ON_OPEN):
        return True
    if (attrs & FILE_ATTRIBUTE_OFFLINE) and (attrs & FILE_ATTRIBUTE_REPARSE_POINT):
        return True
    return False


def get_allocated_size(path: str, logical_size: int, is_cloud: bool = False) -> int:
    """Return actual physical/compressed bytes on disk via GetCompressedFileSizeW."""
    if is_cloud:
        return 0
    if not is_windows() or logical_size == 0:
        return logical_size
    try:
        high = wintypes.DWORD(0)
        low = _kernel32.GetCompressedFileSizeW(path, ctypes.byref(high))
        if low == _INVALID_FILE_SIZE:
            err = _kernel32.GetLastError()
            if err != 0:
                return logical_size
        return (int(high.value) << 32) | int(low)
    except Exception:
        return logical_size


def get_locked_file_size(path: str) -> Optional[Tuple[int, int]]:
    """Query file size via FindFirstFileW (works on locked files like pagefile.sys/hiberfil.sys)."""
    if not is_windows():
        try:
            st = os.stat(path, follow_symlinks=False)
            return (st.st_size, st.st_size)
        except OSError:
            return None

    try:
        fd = _WIN32_FIND_DATAW()
        handle = _kernel32.FindFirstFileW(path, ctypes.byref(fd))
        if handle == _INVALID_HANDLE_VALUE:
            return None
        try:
            logical = (int(fd.nFileSizeHigh) << 32) | int(fd.nFileSizeLow)
            is_cloud = bool(
                fd.dwFileAttributes
                & (FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | FILE_ATTRIBUTE_RECALL_ON_OPEN)
            )
            disk_sz = get_allocated_size(path, logical, is_cloud=is_cloud)
            return (logical, disk_sz)
        finally:
            _kernel32.FindClose(handle)
    except Exception:
        return None


def _parse_vss_size(value_str: str) -> int:
    """Parse vssadmin size strings like '4.25 GB' or '512 MB' into bytes."""
    m = re.search(r"([\d.,]+)\s*(B|KB|MB|GB|TB)", value_str.strip(), re.IGNORECASE)
    if not m:
        return 0
    num = float(m.group(1).replace(",", ""))
    unit = m.group(2).upper()
    mult = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "TB": 1024 ** 4,
    }.get(unit, 1)
    return int(num * mult)


def query_vss_shadow_storage(drive_letter: str = "C:") -> VssStorageInfo:
    """Query Volume Shadow Copy (System Restore) usage via vssadmin."""
    if not is_windows():
        return VssStorageInfo(available=False, note="VSS applies only to Windows.")

    drive_arg = drive_letter.rstrip("\\")
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            ["vssadmin", "list", "shadowstorage", f"/for={drive_arg}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=6,
            creationflags=creation_flags,
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        lower = output.lower()
        if proc.returncode != 0:
            if "elevated" in lower or "permission" in lower or "access is denied" in lower or "administrator" in lower:
                return VssStorageInfo(
                    available=False,
                    requires_admin=True,
                    raw_output=output.strip(),
                    note="Run as Administrator to inspect System Restore / Shadow Copy (VSS) storage usage.",
                )
            if "no items found" in lower:
                return VssStorageInfo(
                    available=True,
                    used_bytes=0,
                    allocated_bytes=0,
                    max_bytes=0,
                    raw_output=output.strip(),
                    note="No Shadow Copies / Restore Points stored on this drive.",
                )
            return VssStorageInfo(
                available=False,
                requires_admin=not is_admin(),
                raw_output=output.strip(),
                note="Unable to query vssadmin.",
            )

        used = 0
        alloc = 0
        max_sz = 0
        for line in output.splitlines():
            if "used shadow copy storage space" in line.lower():
                used = _parse_vss_size(line.split(":", 1)[-1])
            elif "allocated shadow copy storage space" in line.lower():
                alloc = _parse_vss_size(line.split(":", 1)[-1])
            elif "maximum shadow copy storage space" in line.lower():
                max_sz = _parse_vss_size(line.split(":", 1)[-1])

        return VssStorageInfo(
            available=True,
            used_bytes=used,
            allocated_bytes=alloc,
            max_bytes=max_sz,
            raw_output=output.strip(),
            note="Shadow Copy (VSS) information loaded.",
        )
    except Exception as exc:
        return VssStorageInfo(available=False, note=str(exc))


def open_in_explorer(path: str) -> Tuple[bool, str]:
    """Open a file or folder in Windows File Explorer."""
    if not path:
        return (False, "Empty path.")
    target = os.path.abspath(path)
    if not os.path.exists(target):
        return (False, f"Path does not exist: {target}")
    try:
        if is_windows():
            if os.path.isfile(target):
                subprocess.Popen(["explorer", "/select,", target])
            else:
                subprocess.Popen(["explorer", target])
            return (True, "")
        return (False, "Opening File Explorer is only supported on Windows.")
    except Exception as exc:
        return (False, str(exc))


def launch_disk_cleanup(drive_letter: str = "C:") -> Tuple[bool, str]:
    """Launch built-in Windows Disk Cleanup (cleanmgr.exe) for the given drive."""
    if not is_windows():
        return (False, "cleanmgr is only available on Windows.")
    letter = drive_letter.strip().rstrip(":\\")[:1] or "C"
    try:
        subprocess.Popen(["cleanmgr.exe", "/d", letter])
        return (True, f"Launched Windows Disk Cleanup for drive {letter}:")
    except Exception as exc:
        return (False, str(exc))
