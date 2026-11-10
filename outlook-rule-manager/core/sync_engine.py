"""Sync Engine: Bridges YAML configuration with Outlook Native Rules."""
from typing import List, Dict, Any, Tuple, Optional

from core.yaml_manager import YamlConfigManager
from core.rule_splitter import split_rule_recipients
from core.outlook_client import BaseOutlookClient
from core.models import RuleConfig


class SyncEngine:
    """Manages synchronization between YAML definition and Outlook COM native rules."""

    def __init__(self, yaml_mgr: YamlConfigManager, outlook_client: BaseOutlookClient):
        self.yaml_mgr = yaml_mgr
        self.outlook = outlook_client

    def push_to_outlook(self) -> Tuple[bool, str]:
        """Compile YAML rules (with auto-split) and push directly to Outlook COM."""
        active_store_key = "active_archive"
        active_store = self.yaml_mgr.stores.get(active_store_key)
        store_path = active_store.file_path if active_store else ""

        threshold = int(self.yaml_mgr.settings.get("auto_split_threshold", 40))
        compiled_rules = []

        for rule in self.yaml_mgr.rules:
            if not rule.enabled:
                continue

            emails = self.yaml_mgr.get_all_emails_for_rule(rule)
            domains = self.yaml_mgr.get_all_domains_for_rule(rule)

            # Special case for unclassified rule: include unclassified_pool
            if rule.id == "rule_unclassified" or rule.target_folder == "_Unclassified":
                emails = sorted(list(set(emails + self.yaml_mgr.unclassified_pool)))

            # Check if auto-splitting is required
            sub_rules = split_rule_recipients(rule.name, emails, domains, max_recipients=threshold)
            for sub_name, email_chunk, domain_chunk in sub_rules:
                compiled_rules.append({
                    "name": sub_name,
                    "enabled": rule.enabled,
                    "emails": email_chunk,
                    "domains": domain_chunk,
                    "subject_keywords": rule.subject_keywords,
                    "target_folder": rule.target_folder
                })

        success, msg = self.outlook.save_native_rules(compiled_rules, store_path)
        return success, msg

    def perform_rollover(self, new_store_name: str, new_store_path: str) -> Tuple[bool, str]:
        """Perform 1-Click Rollover to new yearly PST file."""
        if not new_store_path:
            return False, "Target store path cannot be empty"

        # 1. Update YAML configuration
        self.yaml_mgr.stores["active_archive"].name = new_store_name
        self.yaml_mgr.stores["active_archive"].file_path = new_store_path
        self.yaml_mgr.save()

        # 2. Re-point Outlook native rules
        success, msg = self.outlook.rollover_rules(new_store_path)
        return success, msg

    def match_message(self, sender_email: str, subject: str) -> Tuple[Optional[RuleConfig], str]:
        """Match an email against rules using Specificity-First hierarchy.
        
        Returns: (matching_rule, match_reason)
        """
        sender_email = sender_email.lower().strip()
        sender_domain = ""
        if "@" in sender_email:
            sender_domain = "@" + sender_email.split("@", 1)[1]

        # Level 1: Exact Email Match
        for rule in self.yaml_mgr.rules:
            if not rule.enabled or rule.id == "rule_unclassified":
                continue
            all_emails = self.yaml_mgr.get_all_emails_for_rule(rule)
            if sender_email in all_emails:
                return rule, f"Exact Email Match: {sender_email}"

        # Level 2: Domain Match
        if sender_domain:
            for rule in self.yaml_mgr.rules:
                if not rule.enabled or rule.id == "rule_unclassified":
                    continue
                all_domains = self.yaml_mgr.get_all_domains_for_rule(rule)
                if sender_domain in all_domains:
                    return rule, f"Domain Match: {sender_domain}"

        # Level 3: Subject Keywords Match
        subj_lower = subject.lower()
        for rule in self.yaml_mgr.rules:
            if not rule.enabled or rule.id == "rule_unclassified":
                continue
            for kw in rule.subject_keywords:
                if kw.lower() in subj_lower:
                    return rule, f"Subject Keyword Match: '{kw}'"

        # Level 4: Unclassified Pool Match (orphaned from deleted rules)
        if sender_email in self.yaml_mgr.unclassified_pool:
            for rule in self.yaml_mgr.rules:
                if rule.id == "rule_unclassified":
                    return rule, "Unclassified Pool (Orphaned Sender)"

        # Level 5: No Match (Stranger / Untracked)
        return None, "Untracked / Stranger"

