"""Windows Disk Full Diagnostic Engine - audits common Windows/App/Dev space hogs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import glob
import os
import platform
import socket
import threading
from typing import Callable, Dict, List, Optional, Tuple

from .formatters import format_bytes
from .models import (
    DiagnosticItem,
    DiagnosticSummary,
    DriveInfo,
    DriveStatus,
    SafetyLevel,
    VssStorageInfo,
)
from .scanner import quick_dir_usage
from .win32_api import (
    get_locked_file_size,
    get_logical_drives,
    is_admin,
    is_windows,
    query_recycle_bin,
    query_vss_shadow_storage,
)


@dataclass(frozen=True)
class _TargetSpec:
    item_id: str
    name: str
    category: str
    description: str
    safety: SafetyLevel
    can_auto_clean: bool
    clean_mode: str
    recommended_action: str
    command_hint: str
    path_resolver: Callable[[Dict[str, str]], List[str]]
    is_file_glob: bool = False
    is_locked_system_file: bool = False


def _env_paths(env_map: Dict[str, str]) -> Dict[str, str]:
    """Resolve standard Windows environment roots with fallback defaults."""
    sys_drive = env_map.get("SystemDrive", "C:").rstrip("\\")
    win_dir = env_map.get("SystemRoot") or env_map.get("windir") or f"{sys_drive}\\Windows"
    user_profile = env_map.get("USERPROFILE") or os.path.expanduser("~")
    local_app = env_map.get("LOCALAPPDATA") or os.path.join(user_profile, "AppData", "Local")
    roaming_app = env_map.get("APPDATA") or os.path.join(user_profile, "AppData", "Roaming")
    program_data = env_map.get("ProgramData") or f"{sys_drive}\\ProgramData"
    temp_dir = env_map.get("TEMP") or env_map.get("TMP") or os.path.join(local_app, "Temp")

    return {
        "sys_drive": sys_drive,
        "win_dir": win_dir,
        "user_profile": user_profile,
        "local_app": local_app,
        "roaming_app": roaming_app,
        "program_data": program_data,
        "temp_dir": temp_dir,
    }


def _dedupe_existing(candidates: List[str], allow_missing: bool = False) -> List[str]:
    seen = set()
    result: List[str] = []
    for raw in candidates:
        if not raw:
            continue
        norm = os.path.normpath(raw)
        key = norm.lower()
        if key in seen:
            continue
        seen.add(key)
        if allow_missing or os.path.exists(norm):
            result.append(norm)
    return result


def _glob_many(patterns: List[str]) -> List[str]:
    matched: List[str] = []
    for pat in patterns:
        matched.extend(glob.glob(pat))
    return _dedupe_existing(matched)


def _build_default_specs() -> List[_TargetSpec]:
    """Declarative catalog of common Windows disk-space culprits."""
    return [
        _TargetSpec(
            item_id="user_temp",
            name="User Temporary Files (%TEMP%)",
            category="Temp & Caches",
            description="Temporary files created by applications and installers in AppData\\Local\\Temp.",
            safety=SafetyLevel.SAFE,
            can_auto_clean=True,
            clean_mode="contents",
            recommended_action="Safe to clean (in-use files are automatically skipped).",
            command_hint="cleanmgr / rd /s /q %TEMP%",
            path_resolver=lambda e: _dedupe_existing([e["temp_dir"]]),
        ),
        _TargetSpec(
            item_id="windows_temp",
            name="Windows Temp (C:\\Windows\\Temp)",
            category="Temp & Caches",
            description="System-wide temporary directory used by Windows and background services.",
            safety=SafetyLevel.SAFE,
            can_auto_clean=True,
            clean_mode="contents",
            recommended_action="Safe to clean; currently locked files will be skipped automatically.",
            command_hint="del /q /f /s C:\\Windows\\Temp\\*",
            path_resolver=lambda e: _dedupe_existing([os.path.join(e["win_dir"], "Temp")]),
        ),
        _TargetSpec(
            item_id="windows_update_cache",
            name="Windows Update Cache (SoftwareDistribution\\Download)",
            category="Windows Update & Upgrades",
            description="Downloaded Windows Update packages kept after installation.",
            safety=SafetyLevel.REVIEW,
            can_auto_clean=True,
            clean_mode="contents",
            recommended_action="Safe to delete once pending updates and restarts are finished.",
            command_hint="net stop wuauserv && del /s /q C:\\Windows\\SoftwareDistribution\\Download\\* && net start wuauserv",
            path_resolver=lambda e: _dedupe_existing(
                [os.path.join(e["win_dir"], "SoftwareDistribution", "Download")]
            ),
        ),
        _TargetSpec(
            item_id="delivery_optimization",
            name="Delivery Optimization Cache",
            category="Windows Update & Upgrades",
            description="Peer-to-peer Windows Update delivery cache files.",
            safety=SafetyLevel.SAFE,
            can_auto_clean=True,
            clean_mode="contents",
            recommended_action="Safe to clean; Windows re-downloads files only when needed.",
            command_hint="Delete-DeliveryOptimizationCache (PowerShell)",
            path_resolver=lambda e: _dedupe_existing(
                [
                    os.path.join(e["win_dir"], "SoftwareDistribution", "DeliveryOptimization", "Cache"),
                    os.path.join(
                        e["win_dir"],
                        "ServiceProfiles",
                        "NetworkService",
                        "AppData",
                        "Local",
                        "Microsoft",
                        "Windows",
                        "DeliveryOptimization",
                        "Cache",
                    ),
                ]
            ),
        ),
        _TargetSpec(
            item_id="windows_old",
            name="Previous Windows Installations (Windows.old / $WINDOWS.~BT)",
            category="Windows Update & Upgrades",
            description="Backup of the previous Windows installation kept after a feature upgrade.",
            safety=SafetyLevel.REVIEW,
            can_auto_clean=False,
            clean_mode="guide",
            recommended_action="Use Windows Disk Cleanup (Clean up system files -> Previous Windows installation(s)) to remove safely.",
            command_hint="cleanmgr.exe /d C",
            path_resolver=lambda e: _dedupe_existing(
                [
                    os.path.join(e["sys_drive"] + "\\", "Windows.old"),
                    os.path.join(e["sys_drive"] + "\\", "$WINDOWS.~BT"),
                    os.path.join(e["sys_drive"] + "\\", "$Windows.~WS"),
                ]
            ),
        ),
        _TargetSpec(
            item_id="wer_reports",
            name="Windows Error Reporting (WER)",
            category="Logs & Crash Dumps",
            description="Accumulated application crash and diagnostic report files.",
            safety=SafetyLevel.SAFE,
            can_auto_clean=True,
            clean_mode="contents",
            recommended_action="Safe to remove completely.",
            command_hint="cleanmgr -> Windows Error Reporting",
            path_resolver=lambda e: _dedupe_existing(
                [
                    os.path.join(e["program_data"], "Microsoft", "Windows", "WER"),
                    os.path.join(e["local_app"], "Microsoft", "Windows", "WER"),
                ]
            ),
        ),
        _TargetSpec(
            item_id="crash_dumps",
            name="Crash Dumps (Minidump / MEMORY.DMP / CrashDumps)",
            category="Logs & Crash Dumps",
            description="Memory dump images generated after a BSOD or application crash.",
            safety=SafetyLevel.REVIEW,
            can_auto_clean=True,
            clean_mode="contents",
            recommended_action="Review first; safe to delete if IT does not need crash dumps for debugging.",
            command_hint="del C:\\Windows\\MEMORY.DMP / cleanmgr -> System error memory dump",
            path_resolver=lambda e: _dedupe_existing(
                [
                    os.path.join(e["win_dir"], "Minidump"),
                    os.path.join(e["win_dir"], "LiveKernelReports"),
                    os.path.join(e["local_app"], "CrashDumps"),
                    os.path.join(e["win_dir"], "MEMORY.DMP"),
                ]
            ),
        ),
        _TargetSpec(
            item_id="thumb_icon_cache",
            name="Explorer Thumbnail & Icon Cache",
            category="Temp & Caches",
            description="thumbcache_*.db and iconcache_*.db preview databases maintained by File Explorer.",
            safety=SafetyLevel.SAFE,
            can_auto_clean=True,
            clean_mode="contents",
            recommended_action="Safe to clean (files locked by Explorer are skipped; Windows rebuilds automatically).",
            command_hint="cleanmgr -> Thumbnails",
            path_resolver=lambda e: _glob_many(
                [
                    os.path.join(e["local_app"], "Microsoft", "Windows", "Explorer", "thumbcache_*.db"),
                    os.path.join(e["local_app"], "Microsoft", "Windows", "Explorer", "iconcache_*.db"),
                ]
            ),
            is_file_glob=True,
        ),
        _TargetSpec(
            item_id="windows_logs",
            name="Windows Logs & Prefetch",
            category="Logs & Crash Dumps",
            description="CBS, DISM, Panther setup logs and Windows Prefetch launch cache.",
            safety=SafetyLevel.REVIEW,
            can_auto_clean=False,
            clean_mode="guide",
            recommended_action="If CBS logs grow unusually large, inspect and delete old CBS*.cab or .log files.",
            command_hint="dir C:\\Windows\\Logs\\CBS",
            path_resolver=lambda e: _dedupe_existing(
                [
                    os.path.join(e["win_dir"], "Logs"),
                    os.path.join(e["win_dir"], "Panther"),
                    os.path.join(e["win_dir"], "Prefetch"),
                ]
            ),
        ),
        _TargetSpec(
            item_id="browser_caches",
            name="Browser Caches (Chrome, Edge, Firefox, Brave)",
            category="Apps & Browsers",
            description="Web Cache, Code Cache, and GPUCache folders — keeps bookmarks, history, and passwords untouched.",
            safety=SafetyLevel.SAFE,
            can_auto_clean=True,
            clean_mode="contents",
            recommended_action="Safe to clean; does not remove passwords, bookmarks, or open tabs.",
            command_hint="Ctrl+Shift+Del in browser (select Cached images and files)",
            path_resolver=lambda e: _glob_many(
                [
                    os.path.join(e["local_app"], "Google", "Chrome", "User Data", "*", "Cache"),
                    os.path.join(e["local_app"], "Google", "Chrome", "User Data", "*", "Code Cache"),
                    os.path.join(e["local_app"], "Google", "Chrome", "User Data", "*", "GPUCache"),
                    os.path.join(e["local_app"], "Microsoft", "Edge", "User Data", "*", "Cache"),
                    os.path.join(e["local_app"], "Microsoft", "Edge", "User Data", "*", "Code Cache"),
                    os.path.join(e["local_app"], "Microsoft", "Edge", "User Data", "*", "GPUCache"),
                    os.path.join(e["local_app"], "BraveSoftware", "Brave-Browser", "User Data", "*", "Cache"),
                    os.path.join(e["local_app"], "CocCoc", "Browser", "User Data", "*", "Cache"),
                    os.path.join(e["local_app"], "Mozilla", "Firefox", "Profiles", "*", "cache2"),
                ]
            ),
        ),
        _TargetSpec(
            item_id="chat_app_caches",
            name="Messaging & Meeting App Caches (Teams, Zalo, Slack, Zoom)",
            category="Apps & Browsers",
            description="Temporary cache and preview data stored by Teams, Zalo PC, Slack, and Zoom.",
            safety=SafetyLevel.REVIEW,
            can_auto_clean=True,
            clean_mode="contents",
            recommended_action="Review first and close the chat app before cleaning.",
            command_hint="Close app -> clear Cache directory",
            path_resolver=lambda e: _glob_many(
                [
                    os.path.join(e["roaming_app"], "Microsoft", "Teams", "Cache"),
                    os.path.join(e["roaming_app"], "Microsoft", "Teams", "Service Worker", "CacheStorage"),
                    os.path.join(e["local_app"], "Packages", "MSTeams_*", "LocalCache", "Microsoft", "MSTeams", "EBWebView", "Default", "Cache"),
                    os.path.join(e["roaming_app"], "ZaloData", "cache"),
                    os.path.join(e["local_app"], "ZaloPC", "Cache"),
                    os.path.join(e["roaming_app"], "Slack", "Cache"),
                    os.path.join(e["roaming_app"], "Slack", "Code Cache"),
                    os.path.join(e["roaming_app"], "Zoom", "logs"),
                ]
            ),
        ),
        _TargetSpec(
            item_id="downloads_folder",
            name="Downloads Folder",
            category="User Data",
            description="Downloaded installers (.exe/.msi), archives (.zip), and documents often left behind.",
            safety=SafetyLevel.REVIEW,
            can_auto_clean=False,
            clean_mode="guide",
            recommended_action="Use the 'Folder Tree' or 'Largest Files' tab to review and delete old downloads (> 30-90 days).",
            command_hint="explorer shell:Downloads",
            path_resolver=lambda e: _dedupe_existing([os.path.join(e["user_profile"], "Downloads")]),
        ),
        _TargetSpec(
            item_id="outlook_data",
            name="Microsoft Outlook Local Data (.ost / .pst)",
            category="User Data",
            description="Offline Outlook cache (.ost) and local archive data files (.pst).",
            safety=SafetyLevel.SYSTEM,
            can_auto_clean=False,
            clean_mode="guide",
            recommended_action="Never delete .ost/.pst directly without backing up; reduce Cached Exchange Mode sync window (e.g., 6-12 months) or move archives to D:\\.",
            command_hint="Outlook -> Account Settings -> Cached Exchange Mode slider",
            path_resolver=lambda e: _dedupe_existing(
                [
                    os.path.join(e["local_app"], "Microsoft", "Outlook"),
                    os.path.join(e["user_profile"], "Documents", "Outlook Files"),
                ]
            ),
        ),
        _TargetSpec(
            item_id="wsl_docker_vhdx",
            name="WSL2 & Docker Desktop Virtual Disks (.vhdx)",
            category="Dev & Virtualization",
            description="Virtual disk images (ext4.vhdx / docker_data.vhdx) that expand dynamically and do not auto-shrink.",
            safety=SafetyLevel.SYSTEM,
            can_auto_clean=False,
            clean_mode="guide",
            recommended_action="Run 'docker system prune -a', then 'wsl --shutdown', and compact via 'Optimize-VHD' or 'diskpart -> compact vdisk'.",
            command_hint="wsl --shutdown && diskpart (select vdisk file=... -> compact vdisk)",
            path_resolver=lambda e: _glob_many(
                [
                    os.path.join(e["local_app"], "Docker", "wsl", "**", "*.vhdx"),
                    os.path.join(e["local_app"], "Packages", "*Ubuntu*", "LocalState", "*.vhdx"),
                    os.path.join(e["local_app"], "Packages", "*Canonical*", "LocalState", "*.vhdx"),
                    os.path.join(e["local_app"], "Packages", "*Debian*", "LocalState", "*.vhdx"),
                    os.path.join(e["local_app"], "wsl", "**", "*.vhdx"),
                ]
            ),
            is_file_glob=True,
        ),
        _TargetSpec(
            item_id="dev_package_caches",
            name="Dev & Package Manager Caches (pip, npm, NuGet, Gradle, Maven, Cargo)",
            category="Dev & Virtualization",
            description="Downloaded package caches for Python pip, Node npm/yarn/pnpm, .NET NuGet, Gradle/Maven, Cargo, and HuggingFace.",
            safety=SafetyLevel.SAFE,
            can_auto_clean=True,
            clean_mode="contents",
            recommended_action="Safe to clean; package managers automatically re-fetch packages when building projects.",
            command_hint="pip cache purge / npm cache clean --force / dotnet nuget locals all --clear",
            path_resolver=lambda e: _dedupe_existing(
                [
                    os.path.join(e["local_app"], "pip", "Cache"),
                    os.path.join(e["local_app"], "npm-cache"),
                    os.path.join(e["roaming_app"], "npm-cache"),
                    os.path.join(e["local_app"], "Yarn", "Cache"),
                    os.path.join(e["local_app"], "pnpm", "store"),
                    os.path.join(e["user_profile"], ".nuget", "packages"),
                    os.path.join(e["user_profile"], ".gradle", "caches"),
                    os.path.join(e["user_profile"], ".m2", "repository"),
                    os.path.join(e["user_profile"], ".cargo", "registry", "cache"),
                    os.path.join(e["user_profile"], ".cache", "huggingface"),
                ]
            ),
        ),
        _TargetSpec(
            item_id="hiberfil_sys",
            name="Windows Hibernation File (hiberfil.sys)",
            category="Windows System Files",
            description="Stores RAM contents for Hibernate & Fast Startup (typically ~40% of installed RAM).",
            safety=SafetyLevel.SYSTEM,
            can_auto_clean=False,
            clean_mode="guide",
            recommended_action="If Hibernate is unused, run 'powercfg /h off' in an elevated Admin terminal (or '/h /type reduced' to halve it).",
            command_hint="powercfg /h off",
            path_resolver=lambda e: [os.path.join(e["sys_drive"] + "\\", "hiberfil.sys")],
            is_locked_system_file=True,
        ),
        _TargetSpec(
            item_id="pagefile_swapfile",
            name="Virtual Memory Files (pagefile.sys & swapfile.sys)",
            category="Windows System Files",
            description="Windows paging and swap files supporting system memory under load.",
            safety=SafetyLevel.SYSTEM,
            can_auto_clean=False,
            clean_mode="guide",
            recommended_action="Do not disable completely; if C:\\ is tight and a fast D:\\ SSD exists, relocate Pagefile in System Properties -> Performance -> Virtual Memory.",
            command_hint="sysdm.cpl -> Advanced -> Performance Settings -> Virtual Memory",
            path_resolver=lambda e: [
                os.path.join(e["sys_drive"] + "\\", "pagefile.sys"),
                os.path.join(e["sys_drive"] + "\\", "swapfile.sys"),
            ],
            is_locked_system_file=True,
        ),
        _TargetSpec(
            item_id="winsxs_store",
            name="Windows Component Store (C:\\Windows\\WinSxS)",
            category="Windows System Files",
            description="Stores Windows OS components and update history (uses NTFS hardlinks, so actual unique footprint is smaller than logical total).",
            safety=SafetyLevel.SYSTEM,
            can_auto_clean=False,
            clean_mode="guide",
            recommended_action="NEVER delete WinSxS manually! Run Microsoft's DISM component cleanup command instead.",
            command_hint="Dism.exe /online /Cleanup-Image /StartComponentCleanup",
            path_resolver=lambda e: _dedupe_existing([os.path.join(e["win_dir"], "WinSxS")]),
        ),
        _TargetSpec(
            item_id="windows_installer_cache",
            name="Windows Installer Cache (C:\\Windows\\Installer)",
            category="Windows System Files",
            description="Cached .msi/.msp installer packages required to repair, patch, or uninstall applications.",
            safety=SafetyLevel.SYSTEM,
            can_auto_clean=False,
            clean_mode="guide",
            recommended_action="Do not delete manually (breaks app repair/uninstall); instead uninstall unused software via Settings -> Installed Apps.",
            command_hint="appwiz.cpl",
            path_resolver=lambda e: _dedupe_existing([os.path.join(e["win_dir"], "Installer")]),
        ),
    ]


class WindowsDiagnostics:
    """Audits drives, Recycle Bin, VSS shadow copies, and known Windows bloat locations."""

    def __init__(self, env_override: Optional[Dict[str, str]] = None) -> None:
        self._env = dict(os.environ)
        if env_override:
            self._env.update(env_override)
        self._roots = _env_paths(self._env)
        self._specs = _build_default_specs()

    def run_audit(
        self,
        cancel_event: Optional[threading.Event] = None,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
        skip_heavy_system_dirs: bool = False,
    ) -> DiagnosticSummary:
        """Execute a complete Windows storage diagnostic audit."""
        drives = get_logical_drives()
        sys_drive = self._roots["sys_drive"]
        vss_info = query_vss_shadow_storage(sys_drive)

        items: List[DiagnosticItem] = []

        # 1. Recycle Bin item (via Win32 SHQueryRecycleBinW)
        rb_total_size = sum(d.recycle_bin_bytes for d in drives if d.is_ready)
        rb_total_count = sum(d.recycle_bin_items for d in drives if d.is_ready)
        if not is_windows() and not rb_total_size:
            rb_total_size, rb_total_count = query_recycle_bin(None)
        items.append(
            DiagnosticItem(
                item_id="recycle_bin",
                name="Windows Recycle Bin",
                category="Temp & Caches",
                description="Deleted files still stored in the Recycle Bin and consuming disk capacity.",
                paths=[f"{d.root_path}$Recycle.Bin" for d in drives if d.is_ready and d.recycle_bin_bytes > 0],
                exists=rb_total_size > 0 or rb_total_count > 0,
                total_bytes=rb_total_size,
                size_on_disk_bytes=rb_total_size,
                file_count=rb_total_count,
                safety=SafetyLevel.SAFE,
                can_auto_clean=True,
                clean_mode="recycle_bin",
                recommended_action="Verify no needed files remain, then empty the Recycle Bin.",
                command_hint="Clear-RecycleBin -Force",
            )
        )

        # 2. Evaluate declarative specs
        total_steps = len(self._specs)
        for idx, spec in enumerate(self._specs, start=1):
            if cancel_event and cancel_event.is_set():
                break
            if progress_cb:
                progress_cb(idx, total_steps, spec.name)

            resolved = spec.path_resolver(self._roots)
            item = self._measure_spec(spec, resolved, skip_heavy=skip_heavy_system_dirs)
            items.append(item)

        # 3. Add VSS item if available or noteworthy
        if vss_info and (vss_info.used_bytes > 0 or vss_info.requires_admin):
            items.append(
                DiagnosticItem(
                    item_id="vss_shadow_storage",
                    name="System Restore & Shadow Copies (VSS)",
                    category="Windows System Files",
                    description="Volume Shadow Copy backups (System Restore / Previous Versions).",
                    paths=[f"{sys_drive}\\System Volume Information"],
                    exists=True,
                    total_bytes=vss_info.used_bytes,
                    size_on_disk_bytes=vss_info.allocated_bytes or vss_info.used_bytes,
                    file_count=0,
                    safety=SafetyLevel.SYSTEM,
                    can_auto_clean=False,
                    clean_mode="guide",
                    recommended_action=(
                        vss_info.note
                        if vss_info.requires_admin
                        else "Adjust max System Restore usage (e.g., 3-5%) in System Protection settings."
                    ),
                    command_hint="vssadmin list shadowstorage / SystemPropertiesProtection.exe",
                )
            )

        items.sort(key=lambda x: (x.size_on_disk_bytes, x.total_bytes), reverse=True)

        reclaimable_safe = sum(
            i.size_on_disk_bytes for i in items if i.safety == SafetyLevel.SAFE and i.can_auto_clean
        )
        reclaimable_review = sum(
            i.size_on_disk_bytes for i in items if i.safety == SafetyLevel.REVIEW and i.can_auto_clean
        )

        health_score, recommendations = self._build_health_and_recommendations(
            drives, items, vss_info, reclaimable_safe
        )

        return DiagnosticSummary(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            computer_name=socket.gethostname(),
            os_version=f"{platform.system()} {platform.release()} ({platform.version()})",
            is_admin=is_admin(),
            drives=drives,
            items=items,
            vss_info=vss_info,
            health_score=health_score,
            reclaimable_safe_bytes=reclaimable_safe,
            reclaimable_review_bytes=reclaimable_review,
            recommendations=recommendations,
        )

    def _measure_spec(
        self, spec: _TargetSpec, paths: List[str], skip_heavy: bool = False
    ) -> DiagnosticItem:
        total_logical = 0
        total_disk = 0
        total_files = 0
        existing_paths: List[str] = []
        errors: List[str] = []

        if spec.is_locked_system_file:
            for p in paths:
                res = get_locked_file_size(p)
                if res is not None:
                    existing_paths.append(p)
                    total_logical += res[0]
                    total_disk += res[1]
                    total_files += 1
        elif spec.is_file_glob:
            for p in paths:
                if os.path.isfile(p):
                    existing_paths.append(p)
                    res = get_locked_file_size(p)
                    if res is not None:
                        total_logical += res[0]
                        total_disk += res[1]
                        total_files += 1
        else:
            max_files = 25000 if (skip_heavy and spec.item_id in ("winsxs_store", "windows_installer_cache")) else None
            for p in paths:
                if not os.path.exists(p):
                    continue
                existing_paths.append(p)
                if os.path.isfile(p):
                    res = get_locked_file_size(p)
                    if res is not None:
                        total_logical += res[0]
                        total_disk += res[1]
                        total_files += 1
                else:
                    l_sz, d_sz, f_cnt, err = quick_dir_usage(p, max_files=max_files)
                    total_logical += l_sz
                    total_disk += d_sz
                    total_files += f_cnt
                    if err:
                        errors.append(err)

        return DiagnosticItem(
            item_id=spec.item_id,
            name=spec.name,
            category=spec.category,
            description=spec.description,
            paths=existing_paths,
            exists=len(existing_paths) > 0,
            total_bytes=total_logical,
            size_on_disk_bytes=total_disk,
            file_count=total_files,
            safety=spec.safety,
            can_auto_clean=spec.can_auto_clean,
            clean_mode=spec.clean_mode,
            recommended_action=spec.recommended_action,
            command_hint=spec.command_hint,
            error=errors[0] if errors else "",
        )

    @staticmethod
    def _build_health_and_recommendations(
        drives: List[DriveInfo],
        items: List[DiagnosticItem],
        vss_info: Optional[VssStorageInfo],
        reclaimable_safe: int,
    ) -> Tuple[int, List[str]]:
        score = 100
        recs: List[str] = []

        ready_drives = [d for d in drives if d.is_ready]

        for drv in ready_drives:
            if drv.status == DriveStatus.CRITICAL:
                penalty = 40 if drv.is_system_drive else 20
                score -= penalty
                recs.append(
                    f"[CRITICAL] Drive {drv.letter} has only {format_bytes(drv.free_bytes)} free "
                    f"({drv.free_percent:.1f}%). Windows performance, updates, and app saves may fail."
                )
            elif drv.status == DriveStatus.WARNING:
                penalty = 20 if drv.is_system_drive else 10
                score -= penalty
                recs.append(
                    f"[WARNING] Drive {drv.letter} is {drv.used_percent:.1f}% full "
                    f"({format_bytes(drv.free_bytes)} free). Consider freeing space soon."
                )

        if reclaimable_safe >= 500 * 1024 ** 2:
            score -= 5
            recs.append(
                f"You can safely reclaim approximately {format_bytes(reclaimable_safe)} right now "
                f"(Temp files, Browser caches, Recycle Bin, WER, Package caches)."
            )

        by_id = {i.item_id: i for i in items}

        win_old = by_id.get("windows_old")
        if win_old and win_old.size_on_disk_bytes >= 512 * 1024 ** 2:
            recs.append(
                f"Detected Windows.old / upgrade remnants using {format_bytes(win_old.size_on_disk_bytes)} — "
                "run Windows Disk Cleanup (cleanmgr) to reclaim this safely."
            )

        hiber = by_id.get("hiberfil_sys")
        if hiber and hiber.size_on_disk_bytes >= 3 * 1024 ** 3:
            recs.append(
                f"Hibernation file hiberfil.sys is using {format_bytes(hiber.size_on_disk_bytes)} — "
                "if Hibernate is not needed, disable via Admin CMD: powercfg /h off."
            )

        vhdx = by_id.get("wsl_docker_vhdx")
        if vhdx and vhdx.size_on_disk_bytes >= 8 * 1024 ** 3:
            recs.append(
                f"WSL2/Docker virtual disks (.vhdx) are using {format_bytes(vhdx.size_on_disk_bytes)} — "
                "run 'docker system prune -a' and compact the .vhdx image."
            )

        downloads = by_id.get("downloads_folder")
        if downloads and downloads.size_on_disk_bytes >= 5 * 1024 ** 3:
            recs.append(
                f"Downloads folder is using {format_bytes(downloads.size_on_disk_bytes)} — "
                "inspect old installers (.exe/.msi/.zip) to delete or archive to another drive."
            )

        if vss_info and vss_info.requires_admin:
            recs.append(
                "Note: Running without Administrator privileges, so System Restore (VSS) storage could not be queried. "
                "Relaunch as Administrator if C:\\ appears unexpectedly full."
            )

        if not recs:
            recs.append("Storage health looks good. No critical low-disk-space issues detected.")

        return (max(5, min(100, score)), recs)
