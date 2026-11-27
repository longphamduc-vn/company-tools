"""YAML Configuration Manager with Versioned Backups."""
import copy
import os
import shutil
import glob
import re
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple
import yaml

from core.models import StoreConfig, AddressGroup, RuleConfig


class YamlConfigManager:
    """Loads, saves, and versions the rules.yaml configuration."""

    def __init__(self, config_path: str):
        self.config_path = os.path.abspath(config_path)
        self.backup_dir = os.path.join(os.path.dirname(self.config_path), "backups")
        os.makedirs(self.backup_dir, exist_ok=True)

        self.version: str = "2.0"
        self.settings: dict = {
            "auto_split_threshold": 40,
            "unclassified_folder": "_Unclassified",
            "backup_versions": 30,
            "custom_folders": []
        }
        self.stores: Dict[str, StoreConfig] = {}
        self.groups: Dict[str, AddressGroup] = {}
        self.rules: List[RuleConfig] = []
        self.unclassified_pool: List[str] = []
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
        """Load configuration from YAML file."""
        if not os.path.exists(self.config_path):
            return False

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        self.version = str(data.get("version", "2.0"))
        self.settings = data.get("settings", self.settings)

        # Parse stores
        self.stores = {}
        raw_stores = data.get("stores", {})
        for s_id, s_data in raw_stores.items():
            self.stores[s_id] = StoreConfig(
                id=s_id,
                name=s_data.get("name", s_id),
                file_path=s_data.get("file_path", ""),
                store_id=s_data.get("store_id", "")
            )

        # Parse groups
        self.groups = {}
        raw_groups = data.get("groups", {})
        for g_id, g_data in raw_groups.items():
            raw_domains = g_data.get("domains", []) or []
            self.groups[g_id] = AddressGroup(
                id=g_id,
                name=g_data.get("name", g_id),
                domains=self.normalize_domains(raw_domains),
                emails=[e.lower().strip() for e in (g_data.get("emails", []) or [])]
            )

        # Parse unclassified pool
        self.unclassified_pool = [e.lower().strip() for e in (data.get("unclassified_pool", []) or [])]

        # Parse rules
        self.rules = []
        raw_rules = data.get("rules", [])
        for r_data in raw_rules:
            raw_rule_domains = r_data.get("domains", []) or []
            self.rules.append(RuleConfig(
                id=r_data.get("id", ""),
                name=r_data.get("name", ""),
                enabled=r_data.get("enabled", True),
                groups=r_data.get("groups", []) or [],
                emails=[e.lower().strip() for e in (r_data.get("emails", []) or [])],
                domains=self.normalize_domains(raw_rule_domains),
                subject_keywords=r_data.get("subject_keywords", []) or [],
                target_store=r_data.get("target_store", "active_archive"),
                target_folder=r_data.get("target_folder", "")
            ))

        # A (re)load starts a fresh undo history
        self._undo_stack = []
        self._last_saved_state = self._capture_state()
        return True

    # -----------------------------------------------------------------
    # Undo (in memory, last UNDO_LIMIT saves)
    # -----------------------------------------------------------------
    UNDO_LIMIT = 20

    def _capture_state(self) -> Dict[str, Any]:
        return copy.deepcopy({
            "settings": self.settings,
            "stores": self.stores,
            "groups": self.groups,
            "rules": self.rules,
            "unclassified_pool": self.unclassified_pool,
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
        self.groups = state["groups"]
        self.rules = state["rules"]
        self.unclassified_pool = state["unclassified_pool"]
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
        val = (domain_str or "").lower().strip()
        if not val:
            return ""
        if "@" in val:
            val = val.split("@", 1)[1].strip()
        val = val.lstrip("@").strip()
        if not val:
            return ""
        return f"@{val}"

    @classmethod
    def normalize_domains(cls, domains: List[str]) -> List[str]:
        """Normalize a list of domains and drop empty entries."""
        return [d for d in (cls.normalize_domain(x) for x in (domains or [])) if d]

    @staticmethod
    def normalize_keywords(keywords: Iterable[str]) -> List[str]:
        """Strip whitespace, drop empty items, and deduplicate case-insensitively keeping first spelling."""
        seen: Set[str] = set()
        result: List[str] = []
        for raw in keywords or []:
            kw = str(raw).strip()
            if not kw:
                continue
            key = kw.lower()
            if key not in seen:
                seen.add(key)
                result.append(kw)
        return result

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

    def save(self) -> bool:
        """Create versioned backup and write updated configuration to YAML atomically."""
        # 1. Create timestamped backup
        self._create_backup_file()

        # 2. Serialize objects to dict
        data = {
            "version": self.version,
            "settings": self.settings,
            "stores": {
                s_id: {
                    "name": s.name,
                    "file_path": s.file_path,
                    **({"store_id": s.store_id} if s.store_id else {}),
                }
                for s_id, s in self.stores.items()
            },
            "groups": {
                g_id: {
                    "name": g.name,
                    "domains": g.domains,
                    "emails": sorted(list(set(g.emails))),
                }
                for g_id, g in self.groups.items()
            },
            "unclassified_pool": sorted(list(set(self.unclassified_pool))),
            "rules": [
                {
                    "id": r.id,
                    "name": r.name,
                    "enabled": r.enabled,
                    "groups": r.groups,
                    "emails": sorted(list(set(r.emails))),
                    "domains": r.domains,
                    "subject_keywords": r.subject_keywords,
                    "target_store": r.target_store,
                    "target_folder": r.target_folder,
                }
                for r in self.rules
            ]
        }

        # 3. Atomic write: temp file -> flush + fsync -> os.replace
        tmp_path = f"{self.config_path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
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
        """Collect all distinct emails matching this rule (direct emails + emails from groups)."""
        emails = set(rule.emails)
        for g_id in rule.groups:
            if g_id in self.groups:
                emails.update(self.groups[g_id].emails)
        return sorted(list(emails))

    def get_all_domains_for_rule(self, rule: RuleConfig) -> List[str]:
        """Collect all distinct domains matching this rule (direct + from groups)."""
        domains = set(rule.domains)
        for g_id in rule.groups:
            if g_id in self.groups:
                domains.update(self.groups[g_id].domains)
        return sorted(list(domains))

    def _remove_rule_no_save(self, rule_id: str) -> bool:
        """Remove a rule and move its emails to unclassified_pool without saving."""
        rule_to_remove = next((r for r in self.rules if r.id == rule_id), None)
        if not rule_to_remove:
            return False

        # Collect direct emails and group emails
        emails_to_repool = self.get_all_emails_for_rule(rule_to_remove)
        for email in emails_to_repool:
            if email and email not in self.unclassified_pool:
                self.unclassified_pool.append(email)

        # Remove the rule
        self.rules = [r for r in self.rules if r.id != rule_id]
        return True

    def remove_rule_and_repool(self, rule_id: str):
        """Remove a rule and automatically add its addresses to unclassified_pool."""
        rule = next((r for r in self.rules if r.id == rule_id), None)
        if rule:
            self._set_change_label(f"Delete rule '{rule.name}'")
        if self._remove_rule_no_save(rule_id):
            self.save()

    def delete_group(self, g_id: str, repool_emails: bool = False) -> bool:
        """Delete an address group, detach it from all rules, and optionally repool its emails."""
        if g_id not in self.groups:
            return False

        group = self.groups.pop(g_id)
        self._set_change_label(f"Delete group '{group.name}'")
        for rule in self.rules:
            if g_id in rule.groups:
                rule.groups = [gid for gid in rule.groups if gid != g_id]

        if repool_emails:
            for email in group.emails:
                norm_email = email.lower().strip()
                if norm_email and norm_email not in self.unclassified_pool:
                    self.unclassified_pool.append(norm_email)

        self.save()
        return True

    def add_sender_to_rule_or_group(
        self,
        email: str,
        rule_id: str,
        as_domain: bool = False,
        save: bool = True,
    ):
        """Add email or normalized domain to a rule or its first valid group."""
        raw = (email or "").lower().strip()
        if not raw:
            return

        # Remove from unclassified_pool if present
        if raw in self.unclassified_pool:
            self.unclassified_pool.remove(raw)

        rule = next((r for r in self.rules if r.id == rule_id), None)
        if not rule:
            return

        target_group = next((self.groups[g_id] for g_id in rule.groups if g_id in self.groups), None)

        if as_domain:
            domain = self.normalize_domain(raw)
            if not domain:
                return
            target_list = target_group.domains if target_group is not None else rule.domains
            if domain not in target_list:
                target_list.append(domain)
        else:
            target_list = target_group.emails if target_group is not None else rule.emails
            if raw not in target_list:
                target_list.append(raw)

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
    ) -> Tuple[List[RuleConfig], List[Tuple[AddressGroup, List[RuleConfig]]]]:
        """Find other rules holding `value` at the same match level.

        Returns (rules holding it directly, [(group holding it, rules using that group)]).
        Groups linked to the target rule are ignored (the value stays reachable from the target).
        """
        target = next((r for r in self.rules if r.id == target_rule_id), None)
        target_groups = set(target.groups) if target else set()
        direct: List[RuleConfig] = []
        group_hits: Dict[str, Tuple[AddressGroup, List[RuleConfig]]] = {}
        for r in self.rules:
            if r.id == target_rule_id:
                continue
            own = r.domains if as_domain else r.emails
            if value in own:
                direct.append(r)
            for g_id in r.groups:
                grp = self.groups.get(g_id)
                if grp is None or g_id in target_groups:
                    continue
                members = grp.domains if as_domain else grp.emails
                if value in members and g_id not in group_hits:
                    users = [u for u in self.rules if g_id in u.groups]
                    group_hits[g_id] = (grp, users)
        return direct, list(group_hits.values())

    def preview_sender_move(self, value: str, rule_id: Optional[str], as_domain: bool = False) -> Dict[str, Any]:
        """Describe what assigning `value` to `rule_id` would move, without changing anything.

        from_rules: names of rules that currently hold the value and would lose it.
        shared_groups: [(group name, [rule names])] for groups used by several rules (needs confirmation).
        """
        value = self._normalize_sender_value(value, as_domain)
        direct, group_hits = self._sender_holders(value, as_domain, rule_id)
        from_rules: List[str] = [r.name for r in direct]
        shared: List[Tuple[str, List[str]]] = []
        for grp, users in group_hits:
            if len(users) <= 1:
                from_rules.extend(u.name for u in users if u.name not in from_rules)
            else:
                shared.append((grp.name, [u.name for u in users]))
        return {"from_rules": from_rules, "shared_groups": shared}

    def detach_sender(
        self,
        value: str,
        as_domain: bool = False,
        except_rule_id: Optional[str] = None,
        remove_from_shared_groups: bool = False,
    ) -> Tuple[List[str], List[Tuple[str, List[str]]]]:
        """Remove `value` from every rule (and single-use group) other than `except_rule_id`.

        Groups shared by several rules are only changed when remove_from_shared_groups is True.
        Returns (names of rules it was removed from, shared groups left untouched).
        """
        value = self._normalize_sender_value(value, as_domain)
        if not value:
            return [], []
        direct, group_hits = self._sender_holders(value, as_domain, except_rule_id)
        moved_from: List[str] = []
        blocked: List[Tuple[str, List[str]]] = []
        for r in direct:
            own = r.domains if as_domain else r.emails
            while value in own:
                own.remove(value)
            moved_from.append(r.name)
        for grp, users in group_hits:
            if len(users) > 1 and not remove_from_shared_groups:
                blocked.append((grp.name, [u.name for u in users]))
                continue
            members = grp.domains if as_domain else grp.emails
            while value in members:
                members.remove(value)
            moved_from.extend(u.name for u in users if u.name not in moved_from)
        if not as_domain and value in self.unclassified_pool:
            self.unclassified_pool.remove(value)
        return moved_from, blocked

    def assign_sender(
        self,
        value: str,
        rule_id: str,
        as_domain: bool = False,
        remove_from_shared_groups: bool = False,
        save: bool = True,
    ) -> Dict[str, Any]:
        """Move a sender email (or domain) into `rule_id`, removing it from other rules at the same level.

        An exact email in one rule already beats a domain in another, so moving an email never
        touches domains (and vice versa).
        """
        rule = next((r for r in self.rules if r.id == rule_id), None)
        value = self._normalize_sender_value(value, as_domain)
        if not rule or not value:
            return {"added": False, "moved_from": [], "blocked_by_groups": []}

        moved_from, blocked = self.detach_sender(
            value, as_domain=as_domain, except_rule_id=rule_id,
            remove_from_shared_groups=remove_from_shared_groups,
        )
        target_group = next((self.groups[g] for g in rule.groups if g in self.groups), None)
        if as_domain:
            target_list = target_group.domains if target_group is not None else rule.domains
        else:
            target_list = target_group.emails if target_group is not None else rule.emails
        already = value in target_list or (
            value in (self.get_all_domains_for_rule(rule) if as_domain else self.get_all_emails_for_rule(rule))
        )
        if not already:
            target_list.append(value)
        self._set_change_label(f"Move '{value}' to rule '{rule.name}'")
        if save:
            self.save()
        return {"added": True, "moved_from": moved_from, "blocked_by_groups": blocked}

    def get_existing_hierarchy(self) -> Tuple[List[str], List[str], List[str]]:
        """Collect all distinct Teams, Parts, and Units from current rules and custom folders."""
        teams = set()
        parts = set()
        units = set()
        all_paths = set(r.target_folder for r in self.rules if r.target_folder)
        all_paths.update(self.settings.get("custom_folders", []))

        for folder in all_paths:
            if folder and folder != "_Unclassified":
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
        for cf in self.settings.get("custom_folders", []):
            if cf:
                folders.add(cf)
        return sorted(list(folders))

    def add_custom_folder(self, folder_path: str) -> bool:
        """Register a folder path so it stays in hierarchy even without rules."""
        folder_path = "\\".join([s.strip() for s in re.split(r'[\\/]', folder_path) if s.strip()])
        if not folder_path:
            return False
        custom_folders = self.settings.setdefault("custom_folders", [])
        if folder_path not in custom_folders:
            custom_folders.append(folder_path)
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
        norm = "\\".join(s.strip() for s in re.split(r'[\\/]', path or "") if s.strip()).lower()
        unc = self.unclassified_folder().lower()
        return norm == unc or norm.startswith(unc + "\\")

    def move_rule_to_folder(self, rule_id: str, new_folder_path: str) -> bool:
        """Move a rule to a target folder hierarchy (never into the Unclassified folder)."""
        new_folder_path = "\\".join([s.strip() for s in re.split(r'[\\/]', new_folder_path) if s.strip()])
        for r in self.rules:
            if r.id == rule_id:
                if r.id != "rule_unclassified" and self.is_inside_unclassified(new_folder_path):
                    return False
                if r.target_folder == new_folder_path:
                    return True
                self._set_change_label(f"Move rule '{r.name}' to '{new_folder_path}'")
                r.target_folder = new_folder_path
                self.save()
                return True
        return False

    def move_folder_hierarchy(self, source_path: str, dest_parent_path: str) -> Tuple[bool, str]:
        """
        Move a folder hierarchy (and all contained rules) into another destination parent folder.
        e.g., source='Engineering_Team\\SCADA_Part\\PLC_Unit', dest_parent='Purchasing_Team\\Vendor_Part'
        Results in 'Purchasing_Team\\Vendor_Part\\PLC_Unit'.
        """
        source_path = "\\".join([s.strip() for s in re.split(r'[\\/]', source_path) if s.strip()])
        dest_parent_path = "\\".join([s.strip() for s in re.split(r'[\\/]', dest_parent_path) if s.strip()])

        if not source_path:
            return False, "Source folder cannot be empty."
        if source_path.lower() == self.unclassified_folder().lower():
            return False, f"The '{self.unclassified_folder()}' folder cannot be moved."
        if self.is_inside_unclassified(dest_parent_path):
            return False, f"Folders cannot be moved into '{self.unclassified_folder()}'."

        # Prevent circular nesting
        if dest_parent_path == source_path or dest_parent_path.startswith(source_path + "\\"):
            return False, "Cannot move a folder into itself or its own subfolder."

        source_parts = source_path.split("\\")
        folder_name = source_parts[-1]

        if dest_parent_path:
            new_base_path = f"{dest_parent_path}\\{folder_name}"
        else:
            # Moved to root (becomes a top-level Team)
            new_base_path = folder_name

        if new_base_path == source_path:
            return True, new_base_path

        # Update all rules
        for r in self.rules:
            if r.target_folder == source_path:
                r.target_folder = new_base_path
            elif r.target_folder and r.target_folder.startswith(source_path + "\\"):
                sub_suffix = r.target_folder[len(source_path):]
                r.target_folder = f"{new_base_path}{sub_suffix}"

        # Update custom folders
        custom_folders = self.settings.get("custom_folders", [])
        new_custom = []
        for cf in custom_folders:
            if cf == source_path:
                new_custom.append(new_base_path)
            elif cf.startswith(source_path + "\\"):
                new_custom.append(f"{new_base_path}{cf[len(source_path):]}")
            else:
                new_custom.append(cf)
        self.settings["custom_folders"] = new_custom

        self._set_change_label(f"Move folder '{source_path}' to '{new_base_path}'")
        self.save()
        return True, new_base_path

    def promote_folder_to_root(self, source_path: str) -> Tuple[bool, str]:
        """Promote any folder (Level 2, 3, 4, etc.) to Root (Level 1)."""
        return self.move_folder_hierarchy(source_path, "")

    def move_folder_up_one_level(self, source_path: str) -> Tuple[bool, str]:
        """Move a folder up one level into its grandparent folder (e.g. Level 3 -> Level 2, Level 2 -> Level 1)."""
        source_path = "\\".join([s.strip() for s in re.split(r'[\\/]', source_path) if s.strip()])
        parts = source_path.split("\\")
        if len(parts) <= 1:
            return False, "Folder is already at Root level (Level 1)."

        if len(parts) == 2:
            # Grandparent is root
            return self.move_folder_hierarchy(source_path, "")
        else:
            grandparent = "\\".join(parts[:-2])
            return self.move_folder_hierarchy(source_path, grandparent)

    def rename_folder_hierarchy(self, old_path: str, new_name: str) -> Tuple[bool, str]:
        """Rename the last segment of a folder path across all rules."""
        old_path = "\\".join([s.strip() for s in re.split(r'[\\/]', old_path) if s.strip()])
        new_name = new_name.strip().replace("\\", "_").replace("/", "_")

        if not old_path or not new_name:
            return False, "Invalid folder name."

        parts = old_path.split("\\")
        parts[-1] = new_name
        new_path = "\\".join(parts)

        if new_path == old_path:
            return True, new_path

        for r in self.rules:
            if r.target_folder == old_path:
                r.target_folder = new_path
            elif r.target_folder and r.target_folder.startswith(old_path + "\\"):
                sub_suffix = r.target_folder[len(old_path):]
                r.target_folder = f"{new_path}{sub_suffix}"

        custom_folders = self.settings.get("custom_folders", [])
        new_custom = []
        for cf in custom_folders:
            if cf == old_path:
                new_custom.append(new_path)
            elif cf.startswith(old_path + "\\"):
                new_custom.append(f"{new_path}{cf[len(old_path):]}")
            else:
                new_custom.append(cf)
        self.settings["custom_folders"] = new_custom

        self._set_change_label(f"Rename folder '{old_path}' to '{new_path}'")
        self.save()
        return True, new_path

    def delete_folder_hierarchy(self, folder_path: str, repool_addresses: bool = True) -> int:
        """
        Delete a folder and either repool its addresses or move its rules to _Unclassified.
        Returns the number of affected rules. Saves once.
        """
        folder_path = "\\".join([s.strip() for s in re.split(r'[\\/]', folder_path) if s.strip()])
        affected_rules = [
            r for r in self.rules
            if r.target_folder == folder_path or (r.target_folder and r.target_folder.startswith(folder_path + "\\"))
        ]

        unclassified_fld = self.settings.get("unclassified_folder", "_Unclassified")

        for r in affected_rules:
            if repool_addresses:
                self._remove_rule_no_save(r.id)
            else:
                # Re-route to _Unclassified
                r.target_folder = unclassified_fld

        # Remove from custom folders
        custom_folders = self.settings.get("custom_folders", [])
        self.settings["custom_folders"] = [
            cf for cf in custom_folders
            if cf != folder_path and not cf.startswith(folder_path + "\\")
        ]

        self._set_change_label(f"Delete folder '{folder_path}'")
        self.save()
        return len(affected_rules)

    def _generate_unique_id(self, prefix: str, base: str, existing_ids: Set[str]) -> str:
        """Generate a unique slugified ID starting with the given prefix."""
        slug = re.sub(r"[^a-z0-9_]", "_", (base or "").lower())
        slug = re.sub(r"_+", "_", slug).lstrip("_")
        if slug.startswith(prefix):
            slug = slug[len(prefix):]
        slug = slug.strip("_")
        if not slug:
            slug = "new"
        candidate_base = f"{prefix}{slug}"

        if candidate_base not in existing_ids:
            return candidate_base

        suffix = 1
        while f"{candidate_base}_{suffix}" in existing_ids:
            suffix += 1
        return f"{candidate_base}_{suffix}"

    def generate_rule_id(self, base: str) -> str:
        """Generate a unique slugified rule ID starting with 'rule_'."""
        return self._generate_unique_id("rule_", base, {r.id for r in self.rules})

    def generate_group_id(self, base: str) -> str:
        """Generate a unique slugified group ID starting with 'grp_'."""
        return self._generate_unique_id("grp_", base, set(self.groups.keys()))

    def duplicate_rule(self, rule_id: str) -> Optional[RuleConfig]:
        """Duplicate an existing rule with a unique ID and 'Copy of' name."""
        rule = next((r for r in self.rules if r.id == rule_id), None)
        if not rule:
            return None

        new_name = f"Copy of {rule.name}"
        new_id = self.generate_rule_id(new_name)
        new_rule = RuleConfig(
            id=new_id,
            name=new_name,
            enabled=rule.enabled,
            groups=list(rule.groups),
            emails=list(rule.emails),
            domains=list(rule.domains),
            subject_keywords=list(rule.subject_keywords),
            target_store=rule.target_store,
            target_folder=rule.target_folder
        )
        self.rules.append(new_rule)
        self._set_change_label(f"Duplicate rule '{rule.name}'")
        self.save()
        return new_rule


