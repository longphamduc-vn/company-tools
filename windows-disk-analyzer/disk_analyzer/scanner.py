"""Fast, junction-safe recursive disk scanner with top-files and extension breakdown."""

from __future__ import annotations

from datetime import datetime
import heapq
import os
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from .models import ExtensionStat, FileEntry, FolderNode, ScanResult
from .win32_api import (
    FILE_ATTRIBUTE_REPARSE_POINT,
    FILE_ATTRIBUTE_SPARSE_FILE,
    get_allocated_size,
    is_cloud_placeholder,
    is_reparse_or_junction,
)

FILE_ATTRIBUTE_COMPRESSED = 0x0800
ProgressCallback = Callable[[int, int, int, str], None]


class DiskScanner:
    """Scans a directory or drive recursively while respecting Windows junctions and cloud files."""

    def __init__(
        self,
        top_n_files: int = 200,
        min_top_file_bytes: int = 1024 * 1024,  # 1 MB default
        max_tree_depth: int = 6,
        exact_disk_size: bool = False,
    ) -> None:
        self.top_n_files = max(10, top_n_files)
        self.min_top_file_bytes = max(0, min_top_file_bytes)
        self.max_tree_depth = max(1, max_tree_depth)
        self.exact_disk_size = exact_disk_size

    def scan(
        self,
        target_path: str,
        cancel_event: Optional[threading.Event] = None,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> ScanResult:
        """Scan target_path and return a populated ScanResult."""
        started_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        t0 = time.perf_counter()
        norm_root = os.path.abspath(target_path)
        if len(norm_root) == 2 and norm_root[1] == ":":
            norm_root += "\\"

        root_name = norm_root if len(norm_root) <= 3 else os.path.basename(norm_root) or norm_root
        root_node = FolderNode(path=norm_root, name=root_name)

        top_heap: List[Tuple[int, int, FileEntry]] = []
        heap_seq = 0
        ext_map: Dict[str, ExtensionStat] = {}
        stats = {
            "files": 0,
            "dirs": 0,
            "logical_bytes": 0,
            "disk_bytes": 0,
            "skipped_reparse": 0,
            "perm_errors": 0,
            "cloud_files": 0,
        }
        last_notify = [t0]

        def maybe_notify(current_path: str, force: bool = False) -> None:
            if not progress_cb:
                return
            now = time.perf_counter()
            if force or (now - last_notify[0]) >= 0.15:
                last_notify[0] = now
                progress_cb(
                    stats["files"],
                    stats["dirs"],
                    stats["disk_bytes"],
                    current_path,
                )

        def walk_dir(dir_path: str, node: Optional[FolderNode], depth: int) -> Tuple[int, int, int, int, float]:
            """Return (logical_bytes, disk_bytes, file_count, dir_count, max_mtime)."""
            if cancel_event and cancel_event.is_set():
                return (0, 0, 0, 0, 0.0)

            logical_sum = 0
            disk_sum = 0
            file_cnt = 0
            dir_cnt = 0
            max_mtime = 0.0

            try:
                it = os.scandir(dir_path)
            except OSError as exc:
                stats["perm_errors"] += 1
                if node is not None:
                    node.error = str(exc)
                return (0, 0, 0, 0, 0.0)

            with it:
                for entry in it:
                    if cancel_event and cancel_event.is_set():
                        break
                    try:
                        st = entry.stat(follow_symlinks=False)
                    except OSError:
                        stats["perm_errors"] += 1
                        continue

                    if is_reparse_or_junction(entry, st):
                        # Only skip directory junctions/symlinks; cloud placeholder *files* are still listed
                        try:
                            is_dir = entry.is_dir(follow_symlinks=False)
                        except OSError:
                            is_dir = False
                        if is_dir:
                            stats["skipped_reparse"] += 1
                            continue

                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        stats["perm_errors"] += 1
                        continue

                    if is_dir:
                        dir_cnt += 1
                        stats["dirs"] += 1
                        child_node: Optional[FolderNode] = None
                        if node is not None and depth < self.max_tree_depth:
                            child_node = FolderNode(path=entry.path, name=entry.name)
                            node.children.append(child_node)

                        c_log, c_disk, c_files, c_dirs, c_mtime = walk_dir(
                            entry.path, child_node, depth + 1
                        )
                        logical_sum += c_log
                        disk_sum += c_disk
                        file_cnt += c_files
                        dir_cnt += c_dirs
                        if c_mtime > max_mtime:
                            max_mtime = c_mtime

                        if child_node is not None:
                            child_node.logical_bytes = c_log
                            child_node.disk_bytes = c_disk
                            child_node.file_count = c_files
                            child_node.dir_count = c_dirs
                            child_node.modified_ts = c_mtime or st.st_mtime
                    else:
                        logical_sz = int(st.st_size)
                        cloud = is_cloud_placeholder(st)
                        attrs = getattr(st, "st_file_attributes", 0)
                        if cloud:
                            disk_sz = 0
                            stats["cloud_files"] += 1
                        elif self.exact_disk_size or (
                            attrs & (FILE_ATTRIBUTE_SPARSE_FILE | FILE_ATTRIBUTE_COMPRESSED | FILE_ATTRIBUTE_REPARSE_POINT)
                        ):
                            disk_sz = get_allocated_size(entry.path, logical_sz, is_cloud=False)
                        else:
                            disk_sz = logical_sz

                        mtime = float(st.st_mtime)
                        if mtime > max_mtime:
                            max_mtime = mtime

                        logical_sum += logical_sz
                        disk_sum += disk_sz
                        file_cnt += 1

                        stats["files"] += 1
                        stats["logical_bytes"] += logical_sz
                        stats["disk_bytes"] += disk_sz

                        _, ext = os.path.splitext(entry.name)
                        ext_key = ext.lower() if ext else "(no ext)"
                        ext_stat = ext_map.get(ext_key)
                        if ext_stat is None:
                            ext_stat = ExtensionStat(extension=ext_key)
                            ext_map[ext_key] = ext_stat
                        ext_stat.file_count += 1
                        ext_stat.logical_bytes += logical_sz
                        ext_stat.disk_bytes += disk_sz

                        rank_sz = disk_sz if disk_sz > 0 else logical_sz
                        if rank_sz >= self.min_top_file_bytes:
                            nonlocal heap_seq
                            heap_seq += 1
                            fe = FileEntry(
                                path=entry.path,
                                name=entry.name,
                                extension=ext_key,
                                parent_dir=dir_path,
                                logical_bytes=logical_sz,
                                disk_bytes=disk_sz,
                                modified_ts=mtime,
                                is_cloud_only=cloud,
                            )
                            if len(top_heap) < self.top_n_files:
                                heapq.heappush(top_heap, (disk_sz, heap_seq, fe))
                            elif disk_sz > top_heap[0][0]:
                                heapq.heapreplace(top_heap, (disk_sz, heap_seq, fe))

                        if stats["files"] % 400 == 0:
                            maybe_notify(dir_path)

            if node is not None:
                node.logical_bytes = logical_sum
                node.disk_bytes = disk_sum
                node.file_count = file_cnt
                node.dir_count = dir_cnt
                node.modified_ts = max_mtime
            return (logical_sum, disk_sum, file_cnt, dir_cnt, max_mtime)

        maybe_notify(norm_root, force=True)
        total_log, total_disk, total_files, total_dirs, root_mtime = walk_dir(norm_root, root_node, 0)
        root_node.logical_bytes = total_log
        root_node.disk_bytes = total_disk
        root_node.file_count = total_files
        root_node.dir_count = total_dirs
        root_node.modified_ts = root_mtime
        root_node.sort_children_desc(by_disk=True)

        top_files = [item[2] for item in sorted(top_heap, key=lambda x: (x[0], x[2].logical_bytes), reverse=True)]
        ext_stats = sorted(ext_map.values(), key=lambda e: (e.disk_bytes, e.logical_bytes), reverse=True)
        maybe_notify(norm_root, force=True)

        return ScanResult(
            target_path=norm_root,
            started_at=started_dt,
            duration_sec=time.perf_counter() - t0,
            total_logical_bytes=total_log,
            total_disk_bytes=total_disk,
            total_files=total_files,
            total_dirs=total_dirs,
            skipped_reparse_dirs=stats["skipped_reparse"],
            permission_errors=stats["perm_errors"],
            cloud_only_files=stats["cloud_files"],
            root_node=root_node,
            top_files=top_files,
            extension_stats=ext_stats,
            cancelled=bool(cancel_event and cancel_event.is_set()),
        )


def quick_dir_usage(path: str, max_files: Optional[int] = None) -> Tuple[int, int, int, str]:
    """Quickly sum (logical_bytes, disk_bytes, file_count, error) of a directory tree without building UI nodes."""
    logical_total = 0
    disk_total = 0
    file_total = 0
    first_error = ""
    stack = [path]

    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        st = entry.stat(follow_symlinks=False)
                    except OSError as exc:
                        if not first_error:
                            first_error = str(exc)
                        continue

                    if is_reparse_or_junction(entry, st):
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                continue
                        except OSError:
                            continue

                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        continue

                    if is_dir:
                        stack.append(entry.path)
                    else:
                        sz = int(st.st_size)
                        cloud = is_cloud_placeholder(st)
                        attrs = getattr(st, "st_file_attributes", 0)
                        if cloud:
                            d_sz = 0
                        elif attrs & (FILE_ATTRIBUTE_SPARSE_FILE | FILE_ATTRIBUTE_COMPRESSED | FILE_ATTRIBUTE_REPARSE_POINT):
                            d_sz = get_allocated_size(entry.path, sz, is_cloud=False)
                        else:
                            d_sz = sz
                        logical_total += sz
                        disk_total += d_sz
                        file_total += 1
                        if max_files and file_total >= max_files:
                            return (logical_total, disk_total, file_total, first_error)
        except OSError as exc:
            if not first_error:
                first_error = str(exc)

    return (logical_total, disk_total, file_total, first_error)
