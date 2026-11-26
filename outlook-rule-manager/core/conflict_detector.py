"""Conflict Detection and Resolution between YAML rules and Outlook Native Rules."""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

from core.models import RuleConfig, MANAGED_PREFIX, extract_base_rule_name
from core.yaml_manager import YamlConfigManager
from core.outlook_client import BaseOutlookClient


@dataclass
class RuleConflict:
    conflict_type: str          # 'NAME_COLLISION', 'SENDER_OVERLAP', 'LEGACY_RULE'
    rule_name: str
    yaml_rule: Optional[RuleConfig]
    outlook_rule_info: Optional[Dict[str, Any]]
    overlapping_senders: List[str] = field(default_factory=list)
    description: str = ""
    suggested_action: str = "OVERWRITE"  # 'OVERWRITE', 'IMPORT', 'MERGE', 'IGNORE'


class ConflictDetector:
    """Detects and resolves discrepancies between YAML configuration and Outlook COM rules."""

    def __init__(self, yaml_mgr: YamlConfigManager, outlook: BaseOutlookClient):
        self.yaml_mgr = yaml_mgr
        self.outlook = outlook

    def detect_conflicts(self) -> List[RuleConflict]:
        """Scan both YAML and Outlook rules and identify all collisions."""
        conflicts: List[RuleConflict] = []
        native_rules = self.outlook.get_native_rules()

        # Map native rules by exact name and normalized base name (without prefix/split suffixes)
        native_by_base: Dict[str, List[Dict[str, Any]]] = {}
        for r in native_rules:
            base = extract_base_rule_name(r.get("name", ""))
            native_by_base.setdefault(base, []).append(r)
        yaml_map = {r.name: r for r in self.yaml_mgr.rules}

        # 1. Check for Name Collisions and Folder Mismatches
        for r_name, r_yaml in yaml_map.items():
            matched_natives = native_by_base.get(r_name, [])
            for r_native in matched_natives:
                native_folder = r_native.get("target_folder", "")
                yaml_folder = r_yaml.target_folder

                # If destination folders don't match
                if native_folder and yaml_folder and (yaml_folder.lower() not in native_folder.lower()):
                    conflicts.append(RuleConflict(
                        conflict_type="NAME_COLLISION",
                        rule_name=r_name,
                        yaml_rule=r_yaml,
                        outlook_rule_info=r_native,
                        description=(
                            f"Rule '{r_name}' exists in Outlook targeting '{native_folder}', "
                            f"but YAML targets '{yaml_folder}'."
                        ),
                        suggested_action="OVERWRITE"
                    ))
                    break

        # 2. Check for Senders Overlapping between Different Rules
        # Build map of email -> rule_name in YAML
        yaml_sender_to_rule: Dict[str, str] = {}
        for r in self.yaml_mgr.rules:
            for email in self.yaml_mgr.get_all_emails_for_rule(r):
                yaml_sender_to_rule[email.lower()] = r.name

        # Check native rules for overlapping senders
        for r_native in native_rules:
            native_name = r_native.get("name", "")
            native_base_name = extract_base_rule_name(native_name)
            native_emails = [e.lower() for e in r_native.get("emails", [])]
            for email in native_emails:
                if email in yaml_sender_to_rule:
                    yaml_target_rule = yaml_sender_to_rule[email]
                    if yaml_target_rule != native_base_name:
                        conflicts.append(RuleConflict(
                            conflict_type="SENDER_OVERLAP",
                            rule_name=f"{email} ({yaml_target_rule} vs {native_name})",
                            yaml_rule=yaml_map.get(yaml_target_rule),
                            outlook_rule_info=r_native,
                            overlapping_senders=[email],
                            description=(
                                f"Sender '{email}' is routed to '{yaml_target_rule}' in YAML, "
                                f"but handled by '{native_name}' in Outlook."
                            ),
                            suggested_action="MERGE"
                        ))

        # 3. Check for Untracked Legacy Outlook Rules
        for r_native in native_rules:
            r_name = r_native.get("name", "")
            if not r_name.startswith(MANAGED_PREFIX) and extract_base_rule_name(r_name) not in yaml_map:
                conflicts.append(RuleConflict(
                    conflict_type="LEGACY_RULE",
                    rule_name=r_name,
                    yaml_rule=None,
                    outlook_rule_info=r_native,
                    description=f"Rule '{r_name}' exists in Outlook but is missing from rules.yaml.",
                    suggested_action="IMPORT"
                ))

        return conflicts

    def resolve_import_to_yaml(self, conflict: RuleConflict, save: bool = True) -> bool:
        """Import a native Outlook rule into rules.yaml."""
        if not conflict.outlook_rule_info:
            return False

        r_name = conflict.rule_name
        r_info = conflict.outlook_rule_info
        folder = r_info.get("target_folder", "").split("\\")[-1] or "Inbox"
        emails = r_info.get("emails", [])

        # Clean unique ID
        clean_id = self.yaml_mgr.generate_rule_id(r_name)
        new_rule = RuleConfig(
            id=clean_id,
            name=r_name,
            enabled=r_info.get("enabled", True),
            emails=emails,
            target_store="active_archive",
            target_folder=folder
        )
        self.yaml_mgr.rules.append(new_rule)
        if save:
            self.yaml_mgr.save()
        return True
