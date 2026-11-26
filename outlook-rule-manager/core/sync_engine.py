"""Sync Engine: Bridges YAML configuration with Outlook Native Rules."""
from typing import List, Dict, Any, Tuple, Optional, Iterable

from core.yaml_manager import YamlConfigManager
from core.rule_splitter import split_rule_recipients
from core.outlook_client import BaseOutlookClient
from core.models import RuleConfig, MANAGED_PREFIX, extract_base_rule_name


def match_email_domain(sender_email: str, domains: Iterable[str]) -> Optional[str]:
    """Return the matching normalized '@domain' if sender_email's domain after '@' matches exactly."""
    email = (sender_email or "").strip().lower()
    if "@" not in email:
        return None
    sender_domain = "@" + email.split("@", 1)[1]
    if not sender_domain[1:]:
        return None
    for dom in domains or []:
        norm_dom = (dom or "").strip().lower()
        if norm_dom and not norm_dom.startswith("@"):
            norm_dom = "@" + norm_dom
        if norm_dom and sender_domain == norm_dom:
            return norm_dom
    return None


class SyncEngine:
    """Manages synchronization between YAML definition and Outlook COM native rules."""

    def __init__(self, yaml_mgr: YamlConfigManager, outlook_client: BaseOutlookClient):
        self.yaml_mgr = yaml_mgr
        self.outlook = outlook_client

    def find_legacy_rules(self) -> List[str]:
        """Return unprefixed Outlook rule names matching YAML rules or split parts."""
        yaml_names = {r.name for r in self.yaml_mgr.rules}
        legacy = []
        for native_rule in self.outlook.get_native_rules():
            r_name = native_rule.get("name", "")
            if not r_name or r_name.startswith(MANAGED_PREFIX):
                continue
            if extract_base_rule_name(r_name) in yaml_names:
                legacy.append(r_name)
        return legacy

    def _effective_rule(self, rule: RuleConfig, group_ids: Optional[List[str]] = None) -> RuleConfig:
        """Return rule or a shallow view using overridden linked group IDs."""
        if group_ids is None:
            return rule
        return RuleConfig(
            id=rule.id,
            name=rule.name,
            enabled=rule.enabled,
            groups=list(group_ids),
            emails=rule.emails,
            domains=rule.domains,
            subject_keywords=rule.subject_keywords,
            target_store=rule.target_store,
            target_folder=rule.target_folder,
        )

    def _resolve_rule_conditions(self, rule: RuleConfig) -> Tuple[List[str], List[str], List[str]]:
        """Collect resolved (emails, domains, subject_keywords) for a rule."""
        is_unclassified = self._is_unclassified_rule(rule)
        emails = self.yaml_mgr.get_all_emails_for_rule(rule)
        domains = self.yaml_mgr.get_all_domains_for_rule(rule)
        keywords = [k.strip() for k in (rule.subject_keywords or []) if k and k.strip()]

        if is_unclassified:
            emails = sorted(list(set(emails + self.yaml_mgr.unclassified_pool)))

        return [e for e in emails if e], [d for d in domains if d], keywords

    def _compile_single_rule(
        self,
        rule: RuleConfig,
        threshold: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Compile one YAML rule into Outlook sub-rule dicts (or return skip reason)."""
        if threshold is None:
            threshold = int(self.yaml_mgr.settings.get("auto_split_threshold", 40))

        emails, domains, keywords = self._resolve_rule_conditions(rule)
        if not emails and not domains and not keywords:
            return [], "no_conditions"

        if not (rule.target_folder or "").strip():
            return [], "no_target_folder"

        entries: List[Dict[str, Any]] = []
        sub_rules = split_rule_recipients(rule.name, emails, domains, max_recipients=threshold)
        for sub_name, email_chunk, domain_chunk in sub_rules:
            entries.append({
                "name": f"{MANAGED_PREFIX}{sub_name}",
                "enabled": rule.enabled,
                "emails": email_chunk,
                "domains": domain_chunk,
                "subject_keywords": [],
                "target_folder": rule.target_folder,
            })

        if keywords:
            entries.append({
                "name": f"{MANAGED_PREFIX}{rule.name} (Keywords)",
                "enabled": rule.enabled,
                "emails": [],
                "domains": [],
                "subject_keywords": keywords,
                "target_folder": rule.target_folder,
            })

        return entries, None

    def get_rule_conditions(self, rule: RuleConfig) -> Tuple[List[str], List[str], List[str]]:
        """Public accessor for resolved (emails, domains, subject_keywords) including _Unclassified pool."""
        return self._resolve_rule_conditions(rule)

    def test_rule_match(
        self,
        rule: RuleConfig,
        sender_email: str = "",
        subject: str = "",
    ) -> Tuple[bool, str]:
        """Test whether sender_email or subject matches a single rule using exact domain semantics."""
        email = (sender_email or "").strip().lower()
        subj = (subject or "").strip()
        if not email and not subj:
            return False, ""

        all_emails, all_domains, keywords = self._resolve_rule_conditions(rule)
        if email and email in all_emails:
            return True, "MATCH! (Exact Email)"

        if email and match_email_domain(email, all_domains):
            return True, "MATCH! (Domain Rule)"

        if subj:
            subj_lower = subj.lower()
            matched_kw = next((kw for kw in keywords if kw.lower() in subj_lower), None)
            if matched_kw:
                return True, f"MATCH! (Subject: '{matched_kw}')"

        return False, "NO MATCH"

    def preview_compiled_rules(self, rule: RuleConfig, group_ids: Optional[List[str]] = None) -> List[str]:
        """Return ordered native Outlook rule names that push_to_outlook will create for rule."""
        effective = self._effective_rule(rule, group_ids)
        entries, _ = self._compile_single_rule(effective)
        return [entry["name"] for entry in entries]

    def get_rule_quota_summary(self, rule: RuleConfig, group_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Return condition counts and compiled Outlook sub-rule preview for a rule."""
        effective = self._effective_rule(rule, group_ids)
        emails, domains, keywords = self._resolve_rule_conditions(effective)
        entries, skip_reason = self._compile_single_rule(effective)
        return {
            "email_count": len(emails),
            "domain_count": len(domains),
            "keyword_count": len(keywords),
            "native_names": [entry["name"] for entry in entries],
            "skip_reason": skip_reason,
        }

    def push_to_outlook(
        self,
        remove_legacy: bool = False,
        remove_legacy_names: Optional[Iterable[str]] = None,
    ) -> Tuple[bool, str]:
        """Compile YAML rules (with auto-split and [Companion] prefix) and reconcile Outlook rules."""
        active_store_key = "active_archive"
        active_store = self.yaml_mgr.stores.get(active_store_key)
        store_path = active_store.file_path if active_store else ""

        threshold = int(self.yaml_mgr.settings.get("auto_split_threshold", 40))
        email_subrules: List[Dict[str, Any]] = []
        domain_subrules: List[Dict[str, Any]] = []
        keyword_subrules: List[Dict[str, Any]] = []
        unclassified_subrules: List[Dict[str, Any]] = []
        skipped_empty_rules: List[str] = []
        skipped_no_folder_rules: List[str] = []

        for rule in self.yaml_mgr.rules:
            entries, skip_reason = self._compile_single_rule(rule, threshold=threshold)
            if skip_reason == "no_conditions":
                skipped_empty_rules.append(rule.name)
                continue
            if skip_reason == "no_target_folder":
                skipped_no_folder_rules.append(rule.name)
                continue

            is_unclassified = self._is_unclassified_rule(rule)
            for entry in entries:
                if is_unclassified:
                    unclassified_subrules.append(entry)
                elif entry["emails"]:
                    email_subrules.append(entry)
                elif entry["domains"]:
                    domain_subrules.append(entry)
                else:
                    keyword_subrules.append(entry)

        compiled_rules = email_subrules + domain_subrules + keyword_subrules + unclassified_subrules
        legacy_base_names = [r.name for r in self.yaml_mgr.rules]

        success, msg = self.outlook.save_native_rules(
            compiled_rules,
            store_path,
            remove_legacy=remove_legacy,
            legacy_base_names=legacy_base_names,
            remove_legacy_names=remove_legacy_names,
        )
        if success and not self.outlook.is_simulated():
            self.yaml_mgr.mark_synced()
        if skipped_empty_rules:
            msg += f"\nWarning - skipped rules with no conditions: {', '.join(skipped_empty_rules)}"
        if skipped_no_folder_rules:
            msg += f"\nWarning - skipped rules without target folder: {', '.join(skipped_no_folder_rules)}"
        return success, msg

    def perform_rollover(self, new_store_name: str, new_store_path: str) -> Tuple[bool, str]:
        """Perform 1-Click Rollover to new yearly PST store safely.

        Verifies target store exists first, updates active_archive in memory,
        re-pushes managed rules via push_to_outlook(), and saves YAML only on
        success (restoring old values in memory on failure).
        """
        if not (new_store_path or "").strip():
            return False, "Target store path cannot be empty"

        active_store = self.yaml_mgr.stores.get("active_archive")
        if active_store is None:
            return False, "Active archive store is not configured in rules.yaml"

        if not self.outlook.store_exists(new_store_path):
            return False, f"Target store not found in Outlook: {new_store_path}"

        old_name = active_store.name
        old_file_path = active_store.file_path

        active_store.name = new_store_name
        active_store.file_path = new_store_path

        try:
            success, msg = self.push_to_outlook()
        except Exception as ex:
            active_store.name = old_name
            active_store.file_path = old_file_path
            return False, f"Rollover failed: {ex}"

        if not success:
            active_store.name = old_name
            active_store.file_path = old_file_path
            return False, msg

        self.yaml_mgr.save()
        if not self.outlook.is_simulated():
            self.yaml_mgr.mark_synced()
        return True, f"Successfully rolled over rules to '{new_store_name}' ({new_store_path}).\n{msg}"

    @staticmethod
    def _is_unclassified_rule(rule: RuleConfig) -> bool:
        """Return True if rule represents the fallback _Unclassified rule."""
        return rule.id == "rule_unclassified" or rule.target_folder == "_Unclassified"

    def match_message(self, sender_email: str, subject: str) -> Tuple[Optional[RuleConfig], str]:
        """Simulate dry-run matching for managed ([Companion]) rules only.

        Note: Dry-run evaluates only the YAML-defined managed rules and does not
        account for unprefixed user-created Outlook rules (which run before
        managed rules in Outlook's ExecutionOrder).

        Evaluation order mirrors Outlook ExecutionOrder (each managed rule sets
        Actions.Stop.Enabled = True):
        1. Exact email sub-rules (non-unclassified, YAML order)
        2. Domain sub-rules (non-unclassified, YAML order)
        3. Subject keyword sub-rules (non-unclassified, YAML order)
        4. Unclassified fallback (unclassified_pool / rule_unclassified, last)
        5. Untracked / Stranger

        Returns: (matching_rule, match_reason)
        """
        sender_email = sender_email.lower().strip()
        sender_domain = ""
        if "@" in sender_email:
            sender_domain = "@" + sender_email.split("@", 1)[1]

        # Level 1: Exact Email Match
        for rule in self.yaml_mgr.rules:
            if not rule.enabled or self._is_unclassified_rule(rule):
                continue
            all_emails = self.yaml_mgr.get_all_emails_for_rule(rule)
            if sender_email in all_emails:
                return rule, f"Exact Email Match: {sender_email}"

        # Level 2: Domain Match
        for rule in self.yaml_mgr.rules:
            if not rule.enabled or self._is_unclassified_rule(rule):
                continue
            all_domains = self.yaml_mgr.get_all_domains_for_rule(rule)
            matched_dom = match_email_domain(sender_email, all_domains)
            if matched_dom:
                return rule, f"Domain Match: {matched_dom}"

        # Level 3: Subject Keywords Match
        subj_lower = subject.lower()
        for rule in self.yaml_mgr.rules:
            if not rule.enabled or self._is_unclassified_rule(rule):
                continue
            for kw in rule.subject_keywords:
                if kw.lower() in subj_lower:
                    return rule, f"Subject Keyword Match: '{kw}'"

        # Level 4: Unclassified Pool Match (orphaned from deleted rules)
        if sender_email in self.yaml_mgr.unclassified_pool:
            for rule in self.yaml_mgr.rules:
                if rule.enabled and self._is_unclassified_rule(rule):
                    return rule, "Unclassified Pool (Orphaned Sender)"

        # Level 5: No Match (Stranger / Untracked)
        return None, "Untracked / Stranger"

