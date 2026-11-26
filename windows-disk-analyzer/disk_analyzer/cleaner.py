"""Safe Cleanup Engine with critical-path guards, dry-run mode, and Recycle Bin support."""

from __future__ import annotations

from datetime import datetime
import os
import time
from typing import List, Tuple

from .models import CleanupItemResult, CleanupSummary, DiagnosticItem
from .win32_api import empty_recycle_bin, is_windows, send_to_recycle_bin

# Paths that must NEVER be wiped directly
_CRITICAL_PATH_TAILS = {
    "",
    "windows",
    "windows\\system32",
    "windows\\syswow64",
    "windows\\winsxs",
    "windows\\installer",
    "program files",
    "program files (x86)",
    "programdata",
    "users",
    "system volume information",
    "$recycle.bin",
}


def is_protected_path(path: str) -> bool:
    """Return True if path is a root or critical OS/user root folder that cannot be bulk-deleted."""
    if not path or not path.strip():
        return True
    norm = os.path.normpath(os.path.abspath(path)).rstrip("\\/")
    if len(norm) <= 3 and norm.endswith(":"):
        return True
    if norm in ("/", "\\"):
        return True

    # Strip drive prefix e.g. 'C:\Windows' -> 'windows'
    _, tail = os.path.splitdrive(norm)
    rel = tail.lstrip("\\/").lower().replace("/", "\\")
    if rel in _CRITICAL_PATH_TAILS:
        return True

    # Protect user profile root (e.g. C:\Users\admin)
    parts = [p for p in rel.split("\\") if p]
    if len(parts) == 2 and parts[0] == "users":
        return True

    # Protect AppData, Desktop, and Documents roots themselves
    if len(parts) == 3 and parts[0] == "users" and parts[2] in ("appdata", "desktop", "documents"):
        return True

    return False


class SafeCleaner:
    """Executes safe cleanups on approved diagnostic items or selected files."""

    def clean_diagnostic_items(
        self,
        items: List[DiagnosticItem],
        dry_run: bool = True,
        use_recycle_bin: bool = False,
    ) -> CleanupSummary:
        """Clean a list of auto-cleanable DiagnosticItem entries."""
        t0 = time.perf_counter()
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        results: List[CleanupItemResult] = []

        for item in items:
            if not item.can_auto_clean:
                results.append(
                    CleanupItemResult(
                        item_id=item.item_id,
                        label=item.name,
                        target_paths=list(item.paths),
                        errors=["This item is system-managed / guide-only and cannot be auto-deleted."],
                        dry_run=dry_run,
                    )
                )
                continue

            if item.clean_mode == "recycle_bin":
                results.append(self._clean_recycle_bin(item, dry_run=dry_run))
            else:
                results.append(
                    self._clean_paths_contents(
                        item_id=item.item_id,
                        label=item.name,
                        paths=item.paths,
                        dry_run=dry_run,
                        use_recycle_bin=use_recycle_bin,
                    )
                )

        return CleanupSummary(
            dry_run=dry_run,
            started_at=started_at,
            duration_sec=time.perf_counter() - t0,
            items=results,
        )

    def delete_selected_files(
        self,
        file_paths: List[str],
        dry_run: bool = True,
        use_recycle_bin: bool = True,
    ) -> CleanupSummary:
        """Delete user-selected individual files safely (Recycle Bin by default)."""
        t0 = time.perf_counter()
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item_res = CleanupItemResult(
            item_id="selected_files",
            label="Selected Large Files",
            target_paths=list(file_paths),
            dry_run=dry_run,
            used_recycle_bin=use_recycle_bin and is_windows(),
        )

        safe_targets: List[Tuple[str, int]] = []
        for raw_path in file_paths:
            abs_p = os.path.abspath(raw_path)
            if is_protected_path(abs_p) or not os.path.exists(abs_p):
                item_res.skipped_files += 1
                item_res.errors.append(f"Skipped protected or missing path: {abs_p}")
                continue
            if os.path.isdir(abs_p):
                item_res.skipped_files += 1
                item_res.errors.append(f"Only individual files can be deleted here: {abs_p}")
                continue
            try:
                sz = os.path.getsize(abs_p)
            except OSError:
                sz = 0
            safe_targets.append((abs_p, sz))

        if dry_run:
            item_res.deleted_files = len(safe_targets)
            item_res.freed_bytes = sum(sz for _, sz in safe_targets)
        else:
            if use_recycle_bin and is_windows() and safe_targets:
                ok, err = send_to_recycle_bin([p for p, _ in safe_targets])
                if ok:
                    for p, sz in safe_targets:
                        if not os.path.exists(p):
                            item_res.deleted_files += 1
                            item_res.freed_bytes += sz
                        else:
                            item_res.skipped_files += 1
                else:
                    item_res.errors.append(err)
                    item_res.skipped_files += len(safe_targets)
            else:
                for p, sz in safe_targets:
                    try:
                        os.unlink(p)
                        item_res.deleted_files += 1
                        item_res.freed_bytes += sz
                    except OSError as exc:
                        item_res.skipped_files += 1
                        item_res.errors.append(f"{os.path.basename(p)}: {exc}")

        return CleanupSummary(
            dry_run=dry_run,
            started_at=started_at,
            duration_sec=time.perf_counter() - t0,
            items=[item_res],
        )

    def _clean_recycle_bin(self, item: DiagnosticItem, dry_run: bool) -> CleanupItemResult:
        res = CleanupItemResult(
            item_id=item.item_id,
            label=item.name,
            target_paths=list(item.paths),
            dry_run=dry_run,
        )
        if dry_run:
            res.freed_bytes = item.size_on_disk_bytes
            res.deleted_files = item.file_count
            return res

        ok, msg = empty_recycle_bin(None)
        if ok:
            res.freed_bytes = item.size_on_disk_bytes
            res.deleted_files = item.file_count
        else:
            res.errors.append(msg)
        return res

    def _clean_paths_contents(
        self,
        item_id: str,
        label: str,
        paths: List[str],
        dry_run: bool,
        use_recycle_bin: bool,
    ) -> CleanupItemResult:
        res = CleanupItemResult(
            item_id=item_id,
            label=label,
            target_paths=list(paths),
            dry_run=dry_run,
            used_recycle_bin=use_recycle_bin and is_windows(),
        )

        for target in paths:
            if not target or not os.path.exists(target):
                continue
            abs_target = os.path.abspath(target)
            if is_protected_path(abs_target):
                res.errors.append(f"Blocked by critical-path guard: {abs_target}")
                continue

            if os.path.isfile(abs_target) or os.path.islink(abs_target):
                self._remove_file_entry(abs_target, res, dry_run, use_recycle_bin)
                continue

            # Delete children inside directory, preserving the root cache directory itself
            try:
                with os.scandir(abs_target) as it:
                    children = list(it)
            except OSError as exc:
                res.errors.append(f"{abs_target}: {exc}")
                continue

            for entry in children:
                try:
                    is_symlink_or_junction = entry.is_symlink() or (
                        callable(getattr(entry, "is_junction", None)) and entry.is_junction()
                    )
                    if is_symlink_or_junction:
                        res.skipped_files += 1
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        self._remove_dir_tree(entry.path, res, dry_run, use_recycle_bin)
                    else:
                        self._remove_file_entry(entry.path, res, dry_run, use_recycle_bin)
                except OSError as exc:
                    res.skipped_files += 1
                    if len(res.errors) < 15:
                        res.errors.append(f"{entry.name}: {exc}")

        return res

    def _remove_file_entry(
        self, file_path: str, res: CleanupItemResult, dry_run: bool, use_recycle_bin: bool
    ) -> None:
        try:
            sz = os.path.getsize(file_path)
        except OSError:
            sz = 0

        if dry_run:
            res.deleted_files += 1
            res.freed_bytes += sz
            return

        if use_recycle_bin and is_windows():
            ok, err = send_to_recycle_bin([file_path])
            if ok and not os.path.exists(file_path):
                res.deleted_files += 1
                res.freed_bytes += sz
            else:
                res.skipped_files += 1
                if err and len(res.errors) < 15:
                    res.errors.append(err)
            return

        try:
            os.unlink(file_path)
            res.deleted_files += 1
            res.freed_bytes += sz
        except OSError as exc:
            res.skipped_files += 1
            if len(res.errors) < 15:
                res.errors.append(f"{os.path.basename(file_path)}: {exc}")

    def _remove_dir_tree(
        self, dir_path: str, res: CleanupItemResult, dry_run: bool, use_recycle_bin: bool
    ) -> None:
        if is_protected_path(dir_path):
            res.errors.append(f"Skipped protected directory: {dir_path}")
            return

        if dry_run:
            stack = [dir_path]
            while stack:
                cur = stack.pop()
                res.deleted_dirs += 1
                try:
                    with os.scandir(cur) as it:
                        for e in it:
                            if e.is_symlink() or (callable(getattr(e, "is_junction", None)) and e.is_junction()):
                                continue
                            if e.is_dir(follow_symlinks=False):
                                stack.append(e.path)
                            else:
                                try:
                                    res.freed_bytes += e.stat(follow_symlinks=False).st_size
                                except OSError:
                                    pass
                                res.deleted_files += 1
                except OSError:
                    res.skipped_files += 1
            return

        if use_recycle_bin and is_windows():
            est_size, est_files = self._estimate_dir(dir_path)
            ok, err = send_to_recycle_bin([dir_path])
            if ok and not os.path.exists(dir_path):
                res.deleted_dirs += 1
                res.deleted_files += est_files
                res.freed_bytes += est_size
            else:
                res.skipped_files += max(1, est_files)
                if err and len(res.errors) < 15:
                    res.errors.append(err)
            return

        # Walk bottom-up deleting files individually so locked files don't abort the entire tree
        try:
            with os.scandir(dir_path) as it:
                entries = list(it)
        except OSError as exc:
            res.skipped_files += 1
            if len(res.errors) < 15:
                res.errors.append(f"{os.path.basename(dir_path)}: {exc}")
            return

        for entry in entries:
            try:
                if entry.is_symlink() or (callable(getattr(entry, "is_junction", None)) and entry.is_junction()):
                    res.skipped_files += 1
                    continue
                if entry.is_dir(follow_symlinks=False):
                    self._remove_dir_tree(entry.path, res, dry_run=False, use_recycle_bin=False)
                else:
                    self._remove_file_entry(entry.path, res, dry_run=False, use_recycle_bin=False)
            except OSError:
                res.skipped_files += 1

        try:
            os.rmdir(dir_path)
            res.deleted_dirs += 1
        except OSError:
            pass

    @staticmethod
    def _estimate_dir(dir_path: str) -> Tuple[int, int]:
        total_b = 0
        total_f = 0
        stack = [dir_path]
        while stack:
            cur = stack.pop()
            try:
                with os.scandir(cur) as it:
                    for e in it:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total_f += 1
                            try:
                                total_b += e.stat(follow_symlinks=False).st_size
                            except OSError:
                                pass
            except OSError:
                pass
        return (total_b, total_f)
