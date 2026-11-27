"""Conflict Detection and Resolution between YAML rules and Outlook Native Rules."""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

from core.models import RuleConfig, MANAGED_PREFIX, extract_base_rule_name
from core.yaml_manager import YamlConfigManager
from core.outlook_client import BaseOutlookClient


@dataclass
class ImportResult:
    """Result of importing an Outlook rule into rules.yaml."""
    imported: bool
    rule_name: str = ""
    has_unsupported_conditions: bool = False
    unresolved_recipients: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.imported

    @property
    def has_warnings(self) -> bool:
        return self.has_unsupported_conditions or bool(self.unresolved_recipients)


def _extract_relative_folder_path(raw_folder: str) -> str:
    """Strip leading '\\\\<StoreName>\\' prefix from Outlook FolderPath and preserve subfolders."""
    cleaned = (raw_folder or "").strip().replace("/", "\\")
    if cleaned.startswith("\\\\"):
        parts = [p for p in cleaned.lstrip("\\").split("\\") if p]
        rel_parts = parts[1:] if len(parts) > 1 else []
    else:
        rel_parts = [p for p in cleaned.split("\\") if p]
    return "\\".join(rel_parts) or "Inbox"


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
        yaml_map = {n: r for r in self.yaml_mgr.rules for n in r.known_names()}

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
        yaml_rule_by_sender: Dict[str, RuleConfig] = {}
        for r in self.yaml_mgr.rules:
            for email in self.yaml_mgr.get_all_emails_for_rule(r):
                yaml_sender_to_rule[email.lower()] = r.name
                yaml_rule_by_sender[email.lower()] = r

        # Check native rules for overlapping senders
        for r_native in native_rules:
            native_name = r_native.get("name", "")
            native_base_name = extract_base_rule_name(native_name)
            native_emails = [e.lower() for e in r_native.get("emails", [])]
            for email in native_emails:
                if email in yaml_sender_to_rule:
                    yaml_target_rule = yaml_sender_to_rule[email]
                    # The same rule under its current or a former (pre auto-naming) name is no overlap
                    if native_base_name not in yaml_rule_by_sender[email].known_names():
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

    def resolve_import_to_yaml(self, conflict: RuleConflict, save: bool = True) -> ImportResult:
        """Import a native Outlook rule (folder hierarchy, emails, domains, keywords) into rules.yaml."""
        if not conflict.outlook_rule_info:
            return ImportResult(imported=False, rule_name=conflict.rule_name)

        r_name = conflict.rule_name
        r_info = conflict.outlook_rule_info
        folder = _extract_relative_folder_path(r_info.get("target_folder", ""))
        emails = [str(e).lower().strip() for e in (r_info.get("emails") or []) if e and "@" in str(e)]
        domains = self.yaml_mgr.normalize_domains(r_info.get("domains") or [])
        subject_keywords = [
            str(k).strip()
            for k in (r_info.get("subject_keywords") or [])
            if k and str(k).strip()
        ]
        unresolved = list(r_info.get("unresolved_recipients") or [])
        has_unsupported = bool(r_info.get("has_unsupported_conditions", False))
        imported_enabled = False if has_unsupported else r_info.get("enabled", True)

        # Clean unique ID
        clean_id = self.yaml_mgr.generate_rule_id(r_name)
        new_rule = RuleConfig(
            id=clean_id,
            name=r_name,
            enabled=imported_enabled,
            emails=emails,
            domains=domains,
            subject_keywords=subject_keywords,
            target_store="active_archive",
            target_folder=folder
        )
        self.yaml_mgr.rules.append(new_rule)
        if save:
            self.yaml_mgr.save()
        return ImportResult(
            imported=True,
            rule_name=r_name,
            has_unsupported_conditions=has_unsupported,
            unresolved_recipients=unresolved,
        )
