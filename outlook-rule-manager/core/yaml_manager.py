"""YAML Configuration Manager with Versioned Backups."""
import os
import shutil
import glob
from datetime import datetime
from typing import Dict, List, Tuple
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
            "backup_versions": 30
        }
        self.stores: Dict[str, StoreConfig] = {}
        self.groups: Dict[str, AddressGroup] = {}
        self.rules: List[RuleConfig] = []
        self.unclassified_pool: List[str] = []

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
            self.groups[g_id] = AddressGroup(
                id=g_id,
                name=g_data.get("name", g_id),
                domains=g_data.get("domains", []) or [],
                emails=[e.lower().strip() for e in (g_data.get("emails", []) or [])]
            )

        # Parse unclassified pool
        self.unclassified_pool = [e.lower().strip() for e in (data.get("unclassified_pool", []) or [])]

        # Parse rules
        self.rules = []
        raw_rules = data.get("rules", [])
        for r_data in raw_rules:
            self.rules.append(RuleConfig(
                id=r_data.get("id", ""),
                name=r_data.get("name", ""),
                enabled=r_data.get("enabled", True),
                groups=r_data.get("groups", []) or [],
                emails=[e.lower().strip() for e in (r_data.get("emails", []) or [])],
                domains=r_data.get("domains", []) or [],
                subject_keywords=r_data.get("subject_keywords", []) or [],
                target_store=r_data.get("target_store", "active_archive"),
                target_folder=r_data.get("target_folder", "")
            ))

        return True

    def save(self) -> bool:
        """Create versioned backup and write updated configuration to YAML."""
        # 1. Create timestamped backup
        if os.path.exists(self.config_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(self.backup_dir, f"rules_{timestamp}.yaml")
            shutil.copy2(self.config_path, backup_file)
            self._prune_backups()

        # 2. Serialize objects to dict
        data = {
            "version": self.version,
            "settings": self.settings,
            "stores": {
                s_id: {
                    "name": s.name,
                    "file_path": s.file_path,
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

        # 3. Write YAML
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        return True

    def _prune_backups(self):
        """Keep only the latest N backup files."""
        max_backups = int(self.settings.get("backup_versions", 30))
        backups = sorted(glob.glob(os.path.join(self.backup_dir, "rules_*.yaml")))
        if len(backups) > max_backups:
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

    def remove_rule_and_repool(self, rule_id: str):
        """Remove a rule and automatically add its addresses to unclassified_pool."""
        rule_to_remove = None
        for r in self.rules:
            if r.id == rule_id:
                rule_to_remove = r
                break

        if not rule_to_remove:
            return

        # Collect direct emails and group emails
        emails_to_repool = self.get_all_emails_for_rule(rule_to_remove)
        for email in emails_to_repool:
            if email and email not in self.unclassified_pool:
                self.unclassified_pool.append(email)

        # Remove the rule
        self.rules = [r for r in self.rules if r.id != rule_id]
        self.save()

    def add_sender_to_rule_or_group(self, email: str, rule_id: str, as_domain: bool = False):
        """Add email or domain to a rule or its first group."""
        email = email.lower().strip()
        if not email:
            return

        # Remove from unclassified_pool if present
        if email in self.unclassified_pool:
            self.unclassified_pool.remove(email)

        for rule in self.rules:
            if rule.id == rule_id:
                if as_domain and "@" in email:
                    domain = "@" + email.split("@", 1)[1]
                    if rule.groups:
                        g_id = rule.groups[0]
                        if domain not in self.groups[g_id].domains:
                            self.groups[g_id].domains.append(domain)
                    else:
                        if domain not in rule.domains:
                            rule.domains.append(domain)
                else:
                    if rule.groups:
                        g_id = rule.groups[0]
                        if email not in self.groups[g_id].emails:
                            self.groups[g_id].emails.append(email)
                    else:
                        if email not in rule.emails:
                            rule.emails.append(email)
                self.save()
                break

