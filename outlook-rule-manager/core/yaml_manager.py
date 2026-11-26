"""YAML Configuration Manager with Versioned Backups."""
import os
import shutil
import glob
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
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

        return True

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
        if self._remove_rule_no_save(rule_id):
            self.save()

    def delete_group(self, g_id: str, repool_emails: bool = False) -> bool:
        """Delete an address group, detach it from all rules, and optionally repool its emails."""
        if g_id not in self.groups:
            return False

        group = self.groups.pop(g_id)
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
            self.save()
        return True

    def move_rule_to_folder(self, rule_id: str, new_folder_path: str) -> bool:
        """Move a rule to a target folder hierarchy."""
        new_folder_path = "\\".join([s.strip() for s in re.split(r'[\\/]', new_folder_path) if s.strip()])
        for r in self.rules:
            if r.id == rule_id:
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
        self.save()
        return new_rule


