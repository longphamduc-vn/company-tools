"""Data models for Windows Disk Analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class DriveStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNREADY = "unready"


class SafetyLevel(str, Enum):
    SAFE = "safe"
    REVIEW = "review"
    SYSTEM = "system"


@dataclass
class DriveInfo:
    letter: str
    root_path: str
    label: str = ""
    drive_type: str = "Fixed"
    filesystem: str = ""
    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    used_percent: float = 0.0
    free_percent: float = 0.0
    status: DriveStatus = DriveStatus.HEALTHY
    recycle_bin_bytes: int = 0
    recycle_bin_items: int = 0
    is_system_drive: bool = False
    is_ready: bool = True
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "letter": self.letter,
            "root_path": self.root_path,
            "label": self.label,
            "drive_type": self.drive_type,
            "filesystem": self.filesystem,
            "total_bytes": self.total_bytes,
            "used_bytes": self.used_bytes,
            "free_bytes": self.free_bytes,
            "used_percent": round(self.used_percent, 2),
            "free_percent": round(self.free_percent, 2),
            "status": self.status.value,
            "recycle_bin_bytes": self.recycle_bin_bytes,
            "recycle_bin_items": self.recycle_bin_items,
            "is_system_drive": self.is_system_drive,
            "is_ready": self.is_ready,
            "error": self.error,
        }


@dataclass
class DiagnosticItem:
    item_id: str
    name: str
    category: str
    description: str
    paths: List[str] = field(default_factory=list)
    exists: bool = False
    total_bytes: int = 0
    size_on_disk_bytes: int = 0
    file_count: int = 0
    safety: SafetyLevel = SafetyLevel.REVIEW
    can_auto_clean: bool = False
    clean_mode: str = "guide"  # "contents", "recycle_bin", "guide"
    recommended_action: str = ""
    command_hint: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "paths": list(self.paths),
            "exists": self.exists,
            "total_bytes": self.total_bytes,
            "size_on_disk_bytes": self.size_on_disk_bytes,
            "file_count": self.file_count,
            "safety": self.safety.value,
            "can_auto_clean": self.can_auto_clean,
            "clean_mode": self.clean_mode,
            "recommended_action": self.recommended_action,
            "command_hint": self.command_hint,
            "error": self.error,
        }


@dataclass
class VssStorageInfo:
    available: bool = False
    requires_admin: bool = False
    used_bytes: int = 0
    allocated_bytes: int = 0
    max_bytes: int = 0
    raw_output: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "requires_admin": self.requires_admin,
            "used_bytes": self.used_bytes,
            "allocated_bytes": self.allocated_bytes,
            "max_bytes": self.max_bytes,
            "note": self.note,
        }


@dataclass
class DiagnosticSummary:
    generated_at: str
    computer_name: str
    os_version: str
    is_admin: bool
    drives: List[DriveInfo] = field(default_factory=list)
    items: List[DiagnosticItem] = field(default_factory=list)
    vss_info: Optional[VssStorageInfo] = None
    health_score: int = 100
    reclaimable_safe_bytes: int = 0
    reclaimable_review_bytes: int = 0
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "computer_name": self.computer_name,
            "os_version": self.os_version,
            "is_admin": self.is_admin,
            "health_score": self.health_score,
            "reclaimable_safe_bytes": self.reclaimable_safe_bytes,
            "reclaimable_review_bytes": self.reclaimable_review_bytes,
            "recommendations": list(self.recommendations),
            "drives": [d.to_dict() for d in self.drives],
            "items": [i.to_dict() for i in self.items],
            "vss_info": self.vss_info.to_dict() if self.vss_info else None,
        }


@dataclass
class FolderNode:
    path: str
    name: str
    logical_bytes: int = 0
    disk_bytes: int = 0
    file_count: int = 0
    dir_count: int = 0
    modified_ts: float = 0.0
    children: List["FolderNode"] = field(default_factory=list)
    error: str = ""
    skipped_reparse: bool = False

    def sort_children_desc(self, by_disk: bool = True) -> None:
        key_fn = (lambda c: (c.disk_bytes, c.logical_bytes)) if by_disk else (lambda c: c.logical_bytes)
        self.children.sort(key=key_fn, reverse=True)
        for child in self.children:
            child.sort_children_desc(by_disk=by_disk)

    def to_dict(self, max_depth: int = 3, current_depth: int = 0) -> dict:
        data = {
            "path": self.path,
            "name": self.name,
            "logical_bytes": self.logical_bytes,
            "disk_bytes": self.disk_bytes,
            "file_count": self.file_count,
            "dir_count": self.dir_count,
            "modified_ts": self.modified_ts,
            "error": self.error,
        }
        if current_depth < max_depth:
            data["children"] = [
                c.to_dict(max_depth=max_depth, current_depth=current_depth + 1)
                for c in self.children[:30]
            ]
        return data


@dataclass
class FileEntry:
    path: str
    name: str
    extension: str
    parent_dir: str
    logical_bytes: int
    disk_bytes: int
    modified_ts: float
    is_cloud_only: bool = False

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "extension": self.extension,
            "parent_dir": self.parent_dir,
            "logical_bytes": self.logical_bytes,
            "disk_bytes": self.disk_bytes,
            "modified_ts": self.modified_ts,
            "is_cloud_only": self.is_cloud_only,
        }


@dataclass
class ExtensionStat:
    extension: str
    file_count: int = 0
    logical_bytes: int = 0
    disk_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "extension": self.extension,
            "file_count": self.file_count,
            "logical_bytes": self.logical_bytes,
            "disk_bytes": self.disk_bytes,
        }


@dataclass
class ScanResult:
    target_path: str
    started_at: str
    duration_sec: float = 0.0
    total_logical_bytes: int = 0
    total_disk_bytes: int = 0
    total_files: int = 0
    total_dirs: int = 0
    skipped_reparse_dirs: int = 0
    permission_errors: int = 0
    cloud_only_files: int = 0
    root_node: Optional[FolderNode] = None
    top_files: List[FileEntry] = field(default_factory=list)
    extension_stats: List[ExtensionStat] = field(default_factory=list)
    cancelled: bool = False

    def to_dict(self) -> dict:
        return {
            "target_path": self.target_path,
            "started_at": self.started_at,
            "duration_sec": round(self.duration_sec, 3),
            "total_logical_bytes": self.total_logical_bytes,
            "total_disk_bytes": self.total_disk_bytes,
            "total_files": self.total_files,
            "total_dirs": self.total_dirs,
            "skipped_reparse_dirs": self.skipped_reparse_dirs,
            "permission_errors": self.permission_errors,
            "cloud_only_files": self.cloud_only_files,
            "cancelled": self.cancelled,
            "root_node": self.root_node.to_dict(max_depth=3) if self.root_node else None,
            "top_files": [f.to_dict() for f in self.top_files],
            "extension_stats": [e.to_dict() for e in self.extension_stats],
        }


@dataclass
class CleanupItemResult:
    item_id: str
    label: str
    target_paths: List[str] = field(default_factory=list)
    freed_bytes: int = 0
    deleted_files: int = 0
    deleted_dirs: int = 0
    skipped_files: int = 0
    errors: List[str] = field(default_factory=list)
    dry_run: bool = False
    used_recycle_bin: bool = False


@dataclass
class CleanupSummary:
    dry_run: bool
    started_at: str
    duration_sec: float = 0.0
    items: List[CleanupItemResult] = field(default_factory=list)

    @property
    def total_freed_bytes(self) -> int:
        return sum(i.freed_bytes for i in self.items)

    @property
    def total_deleted_files(self) -> int:
        return sum(i.deleted_files for i in self.items)

    @property
    def total_skipped_files(self) -> int:
        return sum(i.skipped_files for i in self.items)
