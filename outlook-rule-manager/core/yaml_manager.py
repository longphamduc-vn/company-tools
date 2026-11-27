"""YAML Configuration Manager with Versioned Backups."""
import copy
import glob
import os
import re
import shutil
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple
import yaml

from core.config_format import (
    dump_folders,
    dump_yaml,
    migrate_v2_with_warnings,
    normalize_domain as _fmt_normalize_domain,
    normalize_domains as _fmt_normalize_domains,
    normalize_folder_path,
    normalize_keywords as _fmt_normalize_keywords,
    parse_folders,
    unique_rule_id,
)
from core.models import RuleConfig, StoreConfig, rule_name_from_folder


def _is_v2_data(data: Dict[str, Any]) -> bool:
    if "rules" in data:
        return True
    raw_ver = str(data.get("version", "2.0") or "2.0").strip()
    try:
        major = int(raw_ver.split(".", 1)[0])
        return major < 3
    except ValueError:
        return "folders" not in data


class YamlConfigManager:
    """Loads, saves, and versions the rules.yaml configuration."""

    def __init__(self, config_path: str):
        self.config_path = os.path.abspath(config_path)
        self.backup_dir = os.path.join(os.path.dirname(self.config_path), "backups")
        os.makedirs(self.backup_dir, exist_ok=True)

        self.version: str = "3.0"
        self.settings: dict = {
            "auto_split_threshold": 40,
            "unclassified_folder": "_Unclassified",
            "backup_versions": 30,
        }
        self.stores: Dict[str, StoreConfig] = {}
        self.folders: List[str] = []
        self.rules: List[RuleConfig] = []
        self.unclassified_pool: List[str] = []
        self.legacy_rule_names: List[str] = []
        self.load_warnings: List[str] = []
        self.unsynced_changes: int = 0
        self.has_synced: bool = False
        self._change_listeners: List[Callable[[], Any]] = []

        # In-memory undo: the state before each save, newest last
        self._undo_stack: List[Tuple[str, Dict[str, Any]]] = []
        self._last_saved_state: Optional[Dict[str, Any]] = None
        self._restoring_undo: bool = False
        self.next_change_label: Optional[str] = None

        self.load()

    def load(self) -> bool:
        """Load configuration from YAML file, migrating v2 files automatically."""
        if not os.path.exists(self.config_path):
            return False

        with open(self.config_path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"{os.path.basename(self.config_path)} is not valid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(
                f"{os.path.basename(self.config_path)} must contain settings / folders sections, not a list or text."
            )

        mig_warnings: List[str] = []
        migrated = False
        if isinstance(data, dict) and _is_v2_data(data):
            bak_path = f"{self.config_path}.v2.bak"
            if not os.path.exists(bak_path):
                shutil.copy2(self.config_path, bak_path)
            data, mig_warnings = migrate_v2_with_warnings(data)
            migrated = True

        parsed = parse_folders(data, default_settings=self.settings)
        self.version = parsed.version
        self.settings = parsed.settings
        self.stores = parsed.stores
        self.folders = parsed.folders
        self.rules = parsed.rules
        self.unclassified_pool = parsed.unclassified
        self.legacy_rule_names = parsed.legacy_rule_names
        self.load_warnings = list(dict.fromkeys(mig_warnings + parsed.warnings))

        if migrated:
            self.save()

        # A (re)load starts a fresh undo history
        self._undo_stack = []
        self._last_saved_state = self._capture_state()
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the current configuration to the v3 rules.yaml structure."""
        return dump_folders(
            rules=self.rules,
            folders=self.folders,
            unclassified=self.unclassified_pool,
            legacy_rule_names=self.legacy_rule_names,
            settings=self.settings,
            stores=self.stores,
            version=self.version,
        )

    # -----------------------------------------------------------------
    # Undo (in memory, last UNDO_LIMIT saves)
    # -----------------------------------------------------------------
    UNDO_LIMIT = 20

    def _capture_state(self) -> Dict[str, Any]:
        return copy.deepcopy({
            "settings": self.settings,
            "stores": self.stores,
            "folders": self.folders,
            "rules": self.rules,
            "unclassified_pool": self.unclassified_pool,
            "legacy_rule_names": self.legacy_rule_names,
        })

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def undo_label(self) -> Optional[str]:
        return self._undo_stack[-1][0] if self._undo_stack else None

    def undo(self) -> Optional[str]:
        """Restore the state before the last save and write it. Returns the undone label or None."""
        if not self._undo_stack:
            return None
        label, state = self._undo_stack.pop()
        state = copy.deepcopy(state)
        self.settings = state["settings"]
        self.stores = state["stores"]
        self.folders = state["folders"]
        self.rules = state["rules"]
        self.unclassified_pool = state["unclassified_pool"]
        self.legacy_rule_names = state["legacy_rule_names"]
        self._restoring_undo = True
        try:
            self.save()
        finally:
            self._restoring_undo = False
        return label

    def _record_undo_point(self) -> None:
        """Called after a successful write: remember the previous state unless nothing changed."""
        label = self.next_change_label or "Last change"
        self.next_change_label = None
        current = self._capture_state()
        if not self._restoring_undo and self._last_saved_state is not None and current != self._last_saved_state:
            self._undo_stack.append((label, self._last_saved_state))
            del self._undo_stack[:-self.UNDO_LIMIT]
        self._last_saved_state = current

    @staticmethod
    def normalize_domain(domain_str: str) -> str:
        """Normalize a domain to lowercase stripped '@domain' format; return '' if empty."""
        return _fmt_normalize_domain(domain_str)

    @classmethod
    def normalize_domains(cls, domains: List[str]) -> List[str]:
        """Normalize a list of domains and drop empty entries."""
        return _fmt_normalize_domains(domains)

    @staticmethod
    def normalize_keywords(keywords: Iterable[str]) -> List[str]:
        """Strip whitespace, drop empty items, and deduplicate case-insensitively keeping first spelling."""
        return _fmt_normalize_keywords(keywords)

    def _create_backup_file(self) -> None:
        """Create a unique microsecond-timestamped backup copy and prune old backups."""
        if not os.path.exists(self.config_path):
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_file = os.path.join(self.backup_dir, f"rules_{timestamp}.yaml")
        if os.path.exists(backup_file):
            counter = 1
            while os.path.exists(backup_file):
                backup_file = os.path.join(self.backup_dir, f"rules_{timestamp}_{counter}.yaml")
                counter += 1
        shutil.copy2(self.config_path, backup_file)
        self._prune_backups()

    def _sync_rule_names_and_folders(self) -> None:
        """Keep rule names derived from target_folder and ensure folders list is consistent."""
        seen_folders = {f.lower() for f in self.folders}
        for r in self.rules:
            if r.id == "rule_unclassified" or self.is_inside_unclassified(r.target_folder or ""):
                r.emails = sorted(set(e.lower().strip() for e in (self.unclassified_pool or []) if e and e.strip()))
                continue
            norm = normalize_folder_path(r.target_folder or "")
            if norm:
                r.target_folder = norm
                r.name = rule_name_from_folder(norm)
                if norm.lower() not in seen_folders:
                    self.folders.append(norm)
                    seen_folders.add(norm.lower())

    def save(self) -> bool:
        """Create versioned backup and write updated configuration to YAML atomically."""
        self._create_backup_file()
        self._sync_rule_names_and_folders()
        data = self.to_dict()
        yaml_text = dump_yaml(data)

        tmp_path = f"{self.config_path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(yaml_text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.config_path)
        except OSError as exc:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise RuntimeError(
                f"Failed to save configuration atomically to '{self.config_path}': {exc}"
            ) from exc

        self._record_undo_point()
        self.unsynced_changes += 1
        self._notify_change_listeners()
        return True

    def add_change_listener(self, callback: Callable[[], Any]) -> None:
        """Register a callback invoked when saved config or sync status changes."""
        if callback not in self._change_listeners:
            self._change_listeners.append(callback)

    def _notify_change_listeners(self) -> None:
        """Notify all registered change listeners."""
        for callback in list(self._change_listeners):
            callback()

    def mark_synced(self) -> None:
        """Reset unsynced change counter after a real Outlook sync."""
        self.unsynced_changes = 0
        self.has_synced = True
        self._notify_change_listeners()

    def _prune_backups(self):
        """Keep only the latest N backup files sorted chronologically by filename."""
        max_backups = int(self.settings.get("backup_versions", 30))
        backups = sorted(
            glob.glob(os.path.join(self.backup_dir, "rules_*.yaml")),
            key=os.path.basename,
        )
        if max_backups > 0 and len(backups) > max_backups:
            for b_file in backups[:-max_backups]:
                try:
                    os.remove(b_file)
                except Exception:
                    pass

    def get_all_emails_for_rule(self, rule: RuleConfig) -> List[str]:
        """Return sorted distinct direct emails for this rule."""
        return sorted(list(set(rule.emails)))

    def get_all_domains_for_rule(self, rule: RuleConfig) -> List[str]:
        """Return sorted distinct direct domains for this rule."""
        return sorted(list(set(rule.domains)))

    def rule_for_folder(self, path: str) -> Optional[RuleConfig]:
        """Return the rule assigned to `path` (case-insensitive), or None."""
        norm = normalize_folder_path(path).lower()
        if not norm:
            return None
        return next(
            (r for r in self.rules if normalize_folder_path(r.target_folder or "").lower() == norm),
            None,
        )

    def ensure_rule_for_folder(self, path: str) -> RuleConfig:
        """Return the rule for `path`, creating an empty rule (and registering the folder) if needed."""
        norm = normalize_folder_path(path)
        existing = self.rule_for_folder(norm)
        if existing is not None:
            return existing
        if norm and norm.lower() not in {f.lower() for f in self.folders}:
            self.folders.append(norm)
        new_rule = RuleConfig(
            # A rule moved away keeps its id for the session, so the plain id may be taken
            id=unique_rule_id(norm, (r.id for r in self.rules)),
            name=rule_name_from_folder(norm),
            enabled=True,
            target_folder=norm,
        )
        unc_idx = next((i for i, r in enumerate(self.rules) if r.id == "rule_unclassified"), len(self.rules))
        self.rules.insert(unc_idx, new_rule)
        return new_rule

    def _remove_rule_no_save(self, rule_id: str) -> bool:
        """Remove a rule and move its emails to unclassified_pool without saving."""
        rule_to_remove = next((r for r in self.rules if r.id == rule_id), None)
        if not rule_to_remove:
            return False

        for email in self.get_all_emails_for_rule(rule_to_remove):
            if email and email not in self.unclassified_pool:
                self.unclassified_pool.append(email)

        self.rules = [r for r in self.rules if r.id != rule_id]
        return True

    def remove_rule_and_repool(self, rule_id: str):
        """Remove a rule and automatically add its addresses to unclassified_pool."""
        rule = next((r for r in self.rules if r.id == rule_id), None)
        if rule:
            self._set_change_label(f"Delete rule '{rule.name}'")
        if self._remove_rule_no_save(rule_id):
            self.save()

    def add_sender_to_rule_or_group(
        self,
        email: str,
        rule_id: str,
        as_domain: bool = False,
        save: bool = True,
    ):
        """Add email or normalized domain directly to a rule."""
        raw = (email or "").lower().strip()
        if not raw:
            return

        if raw in self.unclassified_pool:
            self.unclassified_pool.remove(raw)

        rule = next((r for r in self.rules if r.id == rule_id), None)
        if not rule:
            return

        if as_domain:
            domain = self.normalize_domain(raw)
            if not domain:
                return
            if domain not in rule.domains:
                rule.domains.append(domain)
        else:
            if raw not in rule.emails:
                rule.emails.append(raw)

        if save:
            self.save()

    # -----------------------------------------------------------------
    # Moving a sender between rules (one sender lives in one rule per match level)
    # -----------------------------------------------------------------
    def _normalize_sender_value(self, value: str, as_domain: bool) -> str:
        raw = (value or "").lower().strip()
        return self.normalize_domain(raw) if as_domain else raw

    def _sender_holders(
        self, value: str, as_domain: bool, target_rule_id: Optional[str]
    ) -> List[RuleConfig]:
        """Find other rules holding `value` at the same match level."""
        holders: List[RuleConfig] = []
        for r in self.rules:
            if r.id == target_rule_id:
                continue
            own = r.domains if as_domain else r.emails
            if value in own:
                holders.append(r)
        return holders

    def preview_sender_move(self, value: str, rule_id: Optional[str], as_domain: bool = False) -> Dict[str, Any]:
        """Describe which rules would lose `value` if assigned to `rule_id`."""
        value = self._normalize_sender_value(value, as_domain)
        holders = self._sender_holders(value, as_domain, rule_id)
        return {"from_rules": [r.name for r in holders]}

    def detach_sender(
        self,
        value: str,
        as_domain: bool = False,
        except_rule_id: Optional[str] = None,
    ) -> List[str]:
        """Remove `value` from every rule other than `except_rule_id`."""
        value = self._normalize_sender_value(value, as_domain)
        if not value:
            return []
        holders = self._sender_holders(value, as_domain, except_rule_id)
        moved_from: List[str] = []
        for r in holders:
            own = r.domains if as_domain else r.emails
            while value in own:
                own.remove(value)
            moved_from.append(r.name)
        if not as_domain and value in self.unclassified_pool:
            self.unclassified_pool.remove(value)
        return moved_from

    def assign_sender(
        self,
        value: str,
        rule_id: str,
        as_domain: bool = False,
        save: bool = True,
    ) -> Dict[str, Any]:
        """Move a sender email (or domain) into `rule_id`, removing it from other rules at the same level."""
        rule = next((r for r in self.rules if r.id == rule_id), None)
        value = self._normalize_sender_value(value, as_domain)
        if not rule or not value:
            return {"added": False, "moved_from": []}

        moved_from = self.detach_sender(value, as_domain=as_domain, except_rule_id=rule_id)
        target_list = rule.domains if as_domain else rule.emails
        if value not in target_list:
            target_list.append(value)
        self._set_change_label(f"Move '{value}' to rule '{rule.name}'")
        if save:
            self.save()
        return {"added": True, "moved_from": moved_from}

    def get_existing_hierarchy(self) -> Tuple[List[str], List[str], List[str]]:
        """Collect all distinct Teams, Parts, and Units from current rules and folders."""
        teams = set()
        parts = set()
        units = set()
        all_paths = set(r.target_folder for r in self.rules if r.target_folder)
        all_paths.update(self.folders)

        unc = self.unclassified_folder().lower()
        for folder in all_paths:
            if folder and folder.lower() != unc:
                segments = [s.strip() for s in re.split(r'[\\/]', folder) if s.strip()]
                if len(segments) >= 1:
                    teams.add(segments[0])
                if len(segments) >= 2:
                    parts.add(segments[1])
                if len(segments) >= 3:
                    units.add(segments[2])
        return sorted(list(teams)), sorted(list(parts)), sorted(list(units))

    def get_all_folders(self) -> List[str]:
        """Return a sorted list of all unique folder paths."""
        folders = set()
        for r in self.rules:
            if r.target_folder:
                folders.add(r.target_folder)
        for f in self.folders:
            if f:
                folders.add(f)
        return sorted(list(folders))

    def add_folder(self, folder_path: str) -> bool:
        """Register a folder path so it stays in hierarchy even without a rule."""
        folder_path = normalize_folder_path(folder_path)
        if not folder_path:
            return False
        parts = folder_path.split("\\")
        if any(p.startswith("_") for p in parts) or self.is_inside_unclassified(folder_path):
            return False
        if folder_path.lower() not in {f.lower() for f in self.folders}:
            self.folders.append(folder_path)
            self._set_change_label(f"Create folder '{folder_path}'")
            self.save()
        return True

    def _set_change_label(self, text: str) -> None:
        """Describe the next save for Undo, unless the caller (GUI) already set a label."""
        if self.next_change_label is None:
            self.next_change_label = text

    def unclassified_folder(self) -> str:
        return self.settings.get("unclassified_folder", "_Unclassified") or "_Unclassified"

    def is_inside_unclassified(self, path: str) -> bool:
        """True if `path` is the Unclassified folder or anything below it."""
        norm = normalize_folder_path(path).lower()
        unc = self.unclassified_folder().lower()
        return norm == unc or norm.startswith(unc + "\\")

    def move_rule_to_folder(self, rule_id: str, new_folder_path: str) -> Tuple[bool, str]:
        """Move a rule to a target folder hierarchy (never into Unclassified or an occupied folder)."""
        new_folder_path = normalize_folder_path(new_folder_path)
        if not new_folder_path:
            return False, "Target folder cannot be empty."
        if any(p.startswith("_") for p in new_folder_path.split("\\")) and not self.is_inside_unclassified(new_folder_path):
            return False, "Folder name cannot start with '_'."

        rule = next((r for r in self.rules if r.id == rule_id), None)
        if not rule:
            return False, "Rule not found."
        if rule.id != "rule_unclassified" and self.is_inside_unclassified(new_folder_path):
            return False, f"Rules cannot be moved into '{self.unclassified_folder()}'."
        if (rule.target_folder or "").lower() == new_folder_path.lower():
            return True, new_folder_path

        occupant = self.rule_for_folder(new_folder_path)
        if occupant is not None and occupant.id != rule_id:
            return False, f"'{new_folder_path}' already has a rule"

        self._set_change_label(f"Move rule '{rule.name}' to '{new_folder_path}'")
        rule.target_folder = new_folder_path
        if rule.id != "rule_unclassified":
            rule.name = rule_name_from_folder(new_folder_path)
            if new_folder_path.lower() not in {f.lower() for f in self.folders}:
                self.folders.append(new_folder_path)
        self.save()
        return True, new_folder_path

    def move_folder_hierarchy(self, source_path: str, dest_parent_path: str) -> Tuple[bool, str]:
        """Move a folder hierarchy (and all contained rules) into another destination parent folder."""
        source_path = normalize_folder_path(source_path)
        dest_parent_path = normalize_folder_path(dest_parent_path)

        if not source_path:
            return False, "Source folder cannot be empty."
        if source_path.lower() == self.unclassified_folder().lower():
            return False, f"The '{self.unclassified_folder()}' folder cannot be moved."
        if self.is_inside_unclassified(dest_parent_path):
            return False, f"Folders cannot be moved into '{self.unclassified_folder()}'."

        if dest_parent_path.lower() == source_path.lower() or dest_parent_path.lower().startswith(source_path.lower() + "\\"):
            return False, "Cannot move a folder into itself or its own subfolder."

        folder_name = source_path.split("\\")[-1]
        new_base_path = f"{dest_parent_path}\\{folder_name}" if dest_parent_path else folder_name

        if new_base_path.lower() == source_path.lower():
            return True, new_base_path

        src_low = source_path.lower()
        # Check for rule collisions at destination before mutating
        for r in self.rules:
            rf_low = (r.target_folder or "").lower()
            if rf_low == src_low or rf_low.startswith(src_low + "\\"):
                suffix = (r.target_folder or "")[len(source_path):]
                candidate = f"{new_base_path}{suffix}"
                existing = self.rule_for_folder(candidate)
                if existing is not None and existing.id != r.id:
                    return False, f"'{candidate}' already has a rule"

        for r in self.rules:
            rf_low = (r.target_folder or "").lower()
            if rf_low == src_low:
                r.target_folder = new_base_path
                r.name = rule_name_from_folder(new_base_path)
            elif rf_low.startswith(src_low + "\\"):
                sub_suffix = (r.target_folder or "")[len(source_path):]
                r.target_folder = f"{new_base_path}{sub_suffix}"
                r.name = rule_name_from_folder(r.target_folder)

        new_folders: List[str] = []
        seen: Set[str] = set()
        for f in self.folders:
            f_low = f.lower()
            if f_low == src_low:
                updated = new_base_path
            elif f_low.startswith(src_low + "\\"):
                updated = f"{new_base_path}{f[len(source_path):]}"
            else:
                updated = f
            if updated.lower() not in seen:
                seen.add(updated.lower())
                new_folders.append(updated)
        self.folders = new_folders

        self._set_change_label(f"Move folder '{source_path}' to '{new_base_path}'")
        self.save()
        return True, new_base_path

    def promote_folder_to_root(self, source_path: str) -> Tuple[bool, str]:
        """Promote any folder (Level 2, 3, 4, etc.) to Root (Level 1)."""
        return self.move_folder_hierarchy(source_path, "")

    def move_folder_up_one_level(self, source_path: str) -> Tuple[bool, str]:
        """Move a folder up one level into its grandparent folder."""
        source_path = normalize_folder_path(source_path)
        parts = source_path.split("\\")
        if len(parts) <= 1:
            return False, "Folder is already at Root level (Level 1)."
        if len(parts) == 2:
            return self.move_folder_hierarchy(source_path, "")
        return self.move_folder_hierarchy(source_path, "\\".join(parts[:-2]))

    def rename_folder_hierarchy(self, old_path: str, new_name: str) -> Tuple[bool, str]:
        """Rename the last segment of a folder path across all rules and folders."""
        old_path = normalize_folder_path(old_path)
        new_name = (new_name or "").strip().replace("\\", "_").replace("/", "_")

        if not old_path or not new_name:
            return False, "Invalid folder name."
        if new_name.startswith("_"):
            return False, "Folder name cannot start with '_'."

        parts = old_path.split("\\")
        parts[-1] = new_name
        new_path = "\\".join(parts)

        if new_path == old_path:
            return True, new_path

        old_low = old_path.lower()
        for r in self.rules:
            rf_low = (r.target_folder or "").lower()
            if rf_low == old_low or rf_low.startswith(old_low + "\\"):
                suffix = (r.target_folder or "")[len(old_path):]
                candidate = f"{new_path}{suffix}"
                existing = self.rule_for_folder(candidate)
                if existing is not None and existing.id != r.id:
                    return False, f"'{candidate}' already has a rule"

        for r in self.rules:
            rf_low = (r.target_folder or "").lower()
            if rf_low == old_low:
                r.target_folder = new_path
                r.name = rule_name_from_folder(new_path)
            elif rf_low.startswith(old_low + "\\"):
                sub_suffix = (r.target_folder or "")[len(old_path):]
                r.target_folder = f"{new_path}{sub_suffix}"
                r.name = rule_name_from_folder(r.target_folder)

        new_folders: List[str] = []
        seen: Set[str] = set()
        for f in self.folders:
            f_low = f.lower()
            if f_low == old_low:
                updated = new_path
            elif f_low.startswith(old_low + "\\"):
                updated = f"{new_path}{f[len(old_path):]}"
            else:
                updated = f
            if updated.lower() not in seen:
                seen.add(updated.lower())
                new_folders.append(updated)
        self.folders = new_folders

        self._set_change_label(f"Rename folder '{old_path}' to '{new_path}'")
        self.save()
        return True, new_path

    def delete_folder_hierarchy(self, folder_path: str, repool_addresses: bool = True) -> int:
        """Delete a folder and repool its rules' addresses into unclassified_pool."""
        folder_path = normalize_folder_path(folder_path)
        fp_low = folder_path.lower()
        affected_rules = [
            r for r in self.rules
            if (r.target_folder or "").lower() == fp_low or (r.target_folder or "").lower().startswith(fp_low + "\\")
        ]

        for r in affected_rules:
            if repool_addresses:
                self._remove_rule_no_save(r.id)
            else:
                self._remove_rule_no_save(r.id)

        self.folders = [
            f for f in self.folders
            if f.lower() != fp_low and not f.lower().startswith(fp_low + "\\")
        ]

        self._set_change_label(f"Delete folder '{folder_path}'")
        self.save()
        return len(affected_rules)

    # -----------------------------------------------------------------
    # Export / import (sharing rules with colleagues)
    # -----------------------------------------------------------------
    def export_config(self, path: str, include_store_paths: bool = False) -> Dict[str, int]:
        """Write a shareable copy of the rules. PST paths are blanked unless asked for."""
        data = self.to_dict()
        if not include_store_paths:
            for store in data["stores"].values():
                store["file_path"] = ""
                store.pop("store_id", None)
        data["exported_at"] = datetime.now().isoformat(timespec="seconds")
        with open(path, "w", encoding="utf-8") as f:
            f.write(dump_yaml(data))
        return {"rules": len(self.rules)}

    @classmethod
    def read_shared_file(cls, path: str) -> Dict[str, Any]:
        """Parse a shared v3 (or v2, auto-migrated) rules file."""
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as exc:
                raise ValueError(f"Not a valid YAML file: {exc}") from exc
        if not isinstance(data, dict) or ("folders" not in data and "rules" not in data):
            raise ValueError("This file has no 'folders' or 'rules' section, so it is not a rules file.")
        if _is_v2_data(data):
            if not isinstance(data.get("rules"), list):
                raise ValueError("This file has no 'rules' list, so it is not a rules file.")
            for r in data["rules"]:
                if not isinstance(r, dict) or not r.get("name"):
                    raise ValueError("Every rule in the file needs a name.")
            data, _ = migrate_v2_with_warnings(data)
        parsed = parse_folders(data)
        return {
            "settings": parsed.settings,
            "stores": parsed.stores,
            "folders": parsed.folders,
            "rules": parsed.rules,
            "unclassified_pool": parsed.unclassified,
            "legacy_rule_names": parsed.legacy_rule_names,
            "warnings": parsed.warnings,
        }

    def import_config(self, path: str, mode: str = "merge") -> Dict[str, int]:
        """Import folders, rules, unclassified, and legacy_rule_names from a shared file."""
        if mode not in ("merge", "replace"):
            raise ValueError(f"Unknown import mode: {mode}")
        incoming = self.read_shared_file(path)
        summary = {"rules_added": 0, "rules_merged": 0}

        if mode == "replace":
            self.folders = incoming["folders"]
            self.rules = incoming["rules"]
            self.unclassified_pool = incoming["unclassified_pool"]
            self.legacy_rule_names = incoming["legacy_rule_names"]
            summary["rules_added"] = len(self.rules)
        else:
            for f in incoming["folders"]:
                if f and f.lower() not in {x.lower() for x in self.folders}:
                    self.folders.append(f)

            for rule in incoming["rules"]:
                if rule.id == "rule_unclassified" or self.is_inside_unclassified(rule.target_folder or ""):
                    continue
                local = self.rule_for_folder(rule.target_folder)
                if local is not None:
                    local.emails = sorted(set(local.emails) | set(rule.emails))
                    local.domains = sorted(set(local.domains) | set(rule.domains))
                    local.subject_keywords = self.normalize_keywords(local.subject_keywords + rule.subject_keywords)
                    summary["rules_merged"] += 1
                else:
                    rule.id = unique_rule_id(rule.target_folder, (r.id for r in self.rules))
                    unc_idx = next((i for i, r in enumerate(self.rules) if r.id == "rule_unclassified"), len(self.rules))
                    self.rules.insert(unc_idx, rule)
                    summary["rules_added"] += 1

            claimed = set()
            for r in self.rules:
                if r.id != "rule_unclassified" and not self.is_inside_unclassified(r.target_folder or ""):
                    claimed.update(self.get_all_emails_for_rule(r))
            self.unclassified_pool = sorted(
                (set(self.unclassified_pool) | set(incoming["unclassified_pool"])) - claimed
            )
            for name in incoming.get("legacy_rule_names", []):
                if name and name not in self.legacy_rule_names:
                    self.legacy_rule_names.append(name)

        summary["duplicate_senders"] = self._count_duplicate_senders()
        self._set_change_label(f"Import '{os.path.basename(path)}' ({mode})")
        self.save()
        return summary

    def _count_duplicate_senders(self) -> int:
        """Senders (emails or domains) that more than one active rule claims."""
        seen: Dict[str, int] = {}
        for r in self.rules:
            if not r.enabled or self.is_inside_unclassified(r.target_folder or ""):
                continue
            for value in set(self.get_all_emails_for_rule(r)) | set(self.get_all_domains_for_rule(r)):
                seen[value] = seen.get(value, 0) + 1
        return sum(1 for c in seen.values() if c > 1)
