"""Tests for Phase 5: get_native_rules SMTP/conditions, resolve_import_to_yaml, ConflictDialog, and save_native_rules resolve warnings."""
import os
import shutil
import tempfile
import tkinter as tk
import unittest
from tkinter import messagebox
from unittest.mock import patch

from core.conflict_detector import ConflictDetector, RuleConflict
from core.models import MANAGED_PREFIX, RuleConfig
from core.outlook_client import MockOutlookClient, WindowsOutlookClient
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager
from gui.conflict_dialog import ConflictDialog
from tests.fakes import (
    managed_name,
    FakeAddressEntry,
    FakeExchangeUser,
    FakeFolder,
    FakeNamespace,
    FakeRecipient,
    FakeRecipients,
    FakeRule,
    FakeStore,
)


class TestPhase5NativeRuleInspectionAndResolveWarnings(unittest.TestCase):
    """Tests WindowsOutlookClient.get_native_rules, save_native_rules warnings, and resolve_import_to_yaml."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        sample_config = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")
        shutil.copy2(sample_config, self.config_path)

        self.yaml_mgr = YamlConfigManager(self.config_path)
        self.store_path = self.yaml_mgr.stores["active_archive"].file_path
        self.archive_store = FakeStore("Archive 2025", self.store_path)
        self.default_store = FakeStore("Primary Mailbox", "", is_data_file=False)
        self.namespace = FakeNamespace(
            stores=[self.default_store, self.archive_store],
            default_store=self.default_store,
        )
        self.outlook = WindowsOutlookClient(namespace=self.namespace)
        self.sync_engine = SyncEngine(self.yaml_mgr, self.outlook)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_native_rules_extracts_smtp_domains_keywords_unresolved_and_unsupported(self):
        # Rule 1: From only (SMTP + ExchangeUser SMTP + unresolvable display name) -> supported
        r_from = FakeRule("Legacy From Rule", enabled=True)
        r_from.Conditions.From.Enabled = True
        r_from.Conditions.From.Recipients.Add("direct@vendor.com")
        r_from.Conditions.From.Recipients._items.append(
            FakeRecipient(
                Address="/O=EXCHANGELABS/OU=EXCHANGE/CN=RECIPIENTS/CN=A",
                Name="Nguyen Van A",
                AddressEntry=FakeAddressEntry(FakeExchangeUser("vana@company.com")),
            )
        )
        r_from.Conditions.From.Recipients._items.append(
            FakeRecipient(
                Address="/O=EXCHANGELABS/OU=EXCHANGE/CN=RECIPIENTS/CN=UNKNOWN",
                Name="Unknown Former Staff",
                AddressEntry=FakeAddressEntry(None),
            )
        )
        r_from.Actions.MoveToFolder.Enabled = True
        r_from.Actions.MoveToFolder.Folder = FakeFolder(
            "Omron_Unit", FolderPath=r"\\Archive 2025\Purchasing_Team\Vendor_Part\Omron_Unit"
        )

        # Rule 2: SenderAddress only with valid domain -> supported (olConditionSenderAddress = 17)
        r_dom = FakeRule("Legacy Domain Rule", enabled=True)
        r_dom.Conditions.SenderAddress.Enabled = True
        r_dom.Conditions.SenderAddress.Address = ["@Omron.COM"]
        r_dom.Actions.MoveToFolder.Enabled = True
        r_dom.Actions.MoveToFolder.Folder = FakeFolder("Omron", FolderPath=r"\\Archive 2025\Vendors\Omron")

        # Rule 3: SenderAddress with non-domain substring -> unsupported
        r_bad_dom = FakeRule("Legacy Substring Rule", enabled=True)
        r_bad_dom.Conditions.SenderAddress.Enabled = True
        r_bad_dom.Conditions.SenderAddress.Address = ["mitsubishi.com"]
        r_bad_dom.Actions.MoveToFolder.Enabled = True
        r_bad_dom.Actions.MoveToFolder.Folder = FakeFolder("Sub", FolderPath=r"\\Archive 2025\Sub")

        # Rule 4: Subject only -> supported
        r_subj = FakeRule("Legacy Subject Rule", enabled=True)
        r_subj.Conditions.Subject.Enabled = True
        r_subj.Conditions.Subject.Text = ["URGENT", "SCADA"]
        r_subj.Actions.MoveToFolder.Enabled = True
        r_subj.Actions.MoveToFolder.Folder = FakeFolder("Urgent", FolderPath=r"\\Archive 2025\Urgent")

        # Rule 5: MessageHeader enabled (ConditionType=15) -> unsupported
        r_hdr = FakeRule("Legacy Header Rule", enabled=True)
        r_hdr.Conditions.MessageHeader.Enabled = True
        r_hdr.Conditions.MessageHeader.Text = ["X-Custom-Header"]
        r_hdr.Actions.MoveToFolder.Enabled = True
        r_hdr.Actions.MoveToFolder.Folder = FakeFolder("Hdr", FolderPath=r"\\Archive 2025\Hdr")

        # Rule 6: From + Subject both enabled -> unsupported (AND vs OR mismatch)
        r_combo = FakeRule("Legacy Combo Rule", enabled=True)
        r_combo.Conditions.From.Enabled = True
        r_combo.Conditions.From.Recipients.Add("a@partner.com")
        r_combo.Conditions.Subject.Enabled = True
        r_combo.Conditions.Subject.Text = ["PO"]
        r_combo.Actions.MoveToFolder.Enabled = True
        r_combo.Actions.MoveToFolder.Folder = FakeFolder("Combo", FolderPath=r"\\Archive 2025\Combo")

        self.default_store.GetRules()._rules.extend([r_from, r_dom, r_bad_dom, r_subj, r_hdr, r_combo])

        native_rules = self.outlook.get_native_rules()
        by_name = {r["name"]: r for r in native_rules}

        self.assertEqual(by_name["Legacy From Rule"]["emails"], ["direct@vendor.com", "vana@company.com"])
        self.assertNotIn("Unknown Former Staff", by_name["Legacy From Rule"]["emails"])
        self.assertEqual(by_name["Legacy From Rule"]["unresolved_recipients"], ["Unknown Former Staff"])
        self.assertFalse(by_name["Legacy From Rule"]["has_unsupported_conditions"])

        self.assertEqual(by_name["Legacy Domain Rule"]["domains"], ["@omron.com"])
        self.assertFalse(by_name["Legacy Domain Rule"]["has_unsupported_conditions"])

        self.assertTrue(by_name["Legacy Substring Rule"]["has_unsupported_conditions"])

        self.assertEqual(by_name["Legacy Subject Rule"]["subject_keywords"], ["URGENT", "SCADA"])
        self.assertFalse(by_name["Legacy Subject Rule"]["has_unsupported_conditions"])

        self.assertTrue(by_name["Legacy Header Rule"]["has_unsupported_conditions"])
        self.assertTrue(by_name["Legacy Combo Rule"]["has_unsupported_conditions"])

    def test_resolve_import_to_yaml_preserves_relative_folder_and_all_supported_conditions(self):
        detector = ConflictDetector(self.yaml_mgr, self.outlook)
        conflict = RuleConflict(
            conflict_type="LEGACY_RULE",
            rule_name="Imported Multi",
            yaml_rule=None,
            outlook_rule_info={
                "name": "Imported Multi",
                "enabled": True,
                "target_folder": r"\\Archive 2025\Team\Part\Unit",
                "emails": ["a@vendor.com"],
                "domains": ["Vendor.COM", "  @Omron.com "],
                "subject_keywords": ["Invoice", "PO"],
                "unresolved_recipients": ["Old User"],
                "has_unsupported_conditions": True,
            },
        )
        res = detector.resolve_import_to_yaml(conflict)
        self.assertTrue(res)
        self.assertTrue(res.imported)
        self.assertTrue(res.has_unsupported_conditions)
        self.assertEqual(res.unresolved_recipients, ["Old User"])

        imported = next(r for r in self.yaml_mgr.rules if "Imported Multi" in r.known_names())
        self.assertFalse(imported.enabled)
        self.assertEqual(imported.target_folder, r"Team\Part\Unit")
        self.assertEqual(imported.emails, ["a@vendor.com"])
        self.assertEqual(imported.domains, ["@vendor.com", "@omron.com"])
        self.assertEqual(imported.subject_keywords, ["Invoice", "PO"])

    def test_from_and_subject_import_is_disabled_and_stays_disabled_after_push(self):
        combo = FakeRule("Combo Import", enabled=True)
        combo.Conditions.From.Enabled = True
        combo.Conditions.From.Recipients.Add("x@partner.com")
        combo.Conditions.Subject.Enabled = True
        combo.Conditions.Subject.Text = ["Urgent"]
        combo.Actions.MoveToFolder.Enabled = True
        combo.Actions.MoveToFolder.Folder = FakeFolder("Partner", FolderPath=r"\\Archive 2025\Partner")
        self.default_store.GetRules()._rules.append(combo)

        detector = ConflictDetector(self.yaml_mgr, self.outlook)
        conflicts = detector.detect_conflicts()
        combo_conflict = next(c for c in conflicts if c.rule_name == "Combo Import")
        res = detector.resolve_import_to_yaml(combo_conflict)
        self.assertTrue(res.has_unsupported_conditions)

        imported = next(r for r in self.yaml_mgr.rules if "Combo Import" in r.known_names())
        self.assertFalse(imported.enabled)

        ok, msg = self.sync_engine.push_to_outlook()
        self.assertTrue(ok, msg)
        by_name = {r.Name: r for r in self.default_store.GetRules()}
        self.assertFalse(by_name[managed_name(self.yaml_mgr, "Combo Import")].Enabled)
        self.assertFalse(by_name[managed_name(self.yaml_mgr, "Combo Import", " (Keywords)")].Enabled)

    def test_save_native_rules_collects_unresolved_recipient_warnings(self):
        # Case 1: ResolveAll returns False with unresolved recipient
        rule_a = FakeRule(f"{MANAGED_PREFIX}Rule A")
        rule_a.Conditions.From.Recipients = FakeRecipients(
            resolve_success=False,
            unresolved_addresses={"bad@invalid.local"},
        )
        # Case 2: ResolveAll returns True, yet one recipient remains Resolved=False
        rule_b = FakeRule(f"{MANAGED_PREFIX}Rule B")
        rule_b.Conditions.From.Recipients = FakeRecipients(
            resolve_success=True,
            unresolved_addresses={"ghost@missing.local"},
        )
        # Override ResolveAll to return True without touching Resolved on ghost@missing.local
        rule_b.Conditions.From.Recipients.ResolveAll = lambda: True

        self.default_store.GetRules()._rules.extend([rule_a, rule_b])

        ok, msg = self.outlook.save_native_rules(
            [
                {
                    "name": f"{MANAGED_PREFIX}Rule A",
                    "enabled": True,
                    "emails": ["ok@vendor.com", "bad@invalid.local"],
                    "domains": [],
                    "subject_keywords": [],
                    "target_folder": "Vendors",
                },
                {
                    "name": f"{MANAGED_PREFIX}Rule B",
                    "enabled": True,
                    "emails": ["ghost@missing.local"],
                    "domains": [],
                    "subject_keywords": [],
                    "target_folder": "Vendors",
                },
            ],
            self.store_path,
        )
        self.assertTrue(ok)
        self.assertIn(f"{MANAGED_PREFIX}Rule A", msg)
        self.assertIn("bad@invalid.local", msg)
        self.assertIn(f"{MANAGED_PREFIX}Rule B", msg)
        self.assertIn("ghost@missing.local", msg)


class TestPhase5ConflictDialogExecution(unittest.TestCase):
    """Tests ConflictDialog._execute_resolutions with IGNORE, IMPORT, OVERWRITE, MERGE and warning prompts."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        sample_config = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")
        shutil.copy2(sample_config, self.config_path)

        self.yaml_mgr = YamlConfigManager(self.config_path)
        self.store_path = self.yaml_mgr.stores["active_archive"].file_path
        self.archive_store = FakeStore("Archive 2025", self.store_path)
        self.default_store = FakeStore("Primary Mailbox", "", is_data_file=False)
        self.namespace = FakeNamespace(
            stores=[self.default_store, self.archive_store],
            default_store=self.default_store,
        )
        self.outlook = WindowsOutlookClient(namespace=self.namespace)
        self.sync_engine = SyncEngine(self.yaml_mgr, self.outlook)
        self.detector = ConflictDetector(self.yaml_mgr, self.outlook)

        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_dialog_with_conflicts(self, conflicts):
        with patch.object(self.detector, "detect_conflicts", return_value=conflicts):
            dlg = ConflictDialog(self.root, self.detector, self.sync_engine)
        return dlg

    def test_all_ignore_does_not_push_or_modify_yaml_and_reports_counts(self):
        legacy = FakeRule("Ignored Legacy", enabled=True)
        legacy.Conditions.From.Enabled = True
        legacy.Conditions.From.Recipients.Add("x@ext.com")
        self.default_store.GetRules()._rules.append(legacy)

        conflicts = [
            RuleConflict(
                conflict_type="LEGACY_RULE",
                rule_name="Ignored Legacy",
                yaml_rule=None,
                outlook_rule_info={"name": "Ignored Legacy", "target_folder": r"\\Archive 2025\Misc", "emails": ["x@ext.com"]},
                suggested_action="IGNORE",
            )
        ]
        dlg = self._make_dialog_with_conflicts(conflicts)
        initial_rule_count = len(self.yaml_mgr.rules)

        with patch.object(self.sync_engine, "push_to_outlook") as mock_push, \
             patch("gui.conflict_dialog.messagebox.showinfo") as mock_info:
            dlg._execute_resolutions()

        mock_push.assert_not_called()
        self.assertEqual(len(self.yaml_mgr.rules), initial_rule_count)
        summary_msg = mock_info.call_args[0][1]
        self.assertIn("Ignored / Skipped: 1", summary_msg)
        self.assertIn("Imported to YAML: 0", summary_msg)

    def test_overwrite_and_merge_push_without_import_and_report_counts(self):
        conflicts = [
            RuleConflict(
                conflict_type="NAME_COLLISION",
                rule_name="Executive Board",
                yaml_rule=self.yaml_mgr.rules[0],
                outlook_rule_info={"name": "Executive Board"},
                suggested_action="OVERWRITE",
            ),
            RuleConflict(
                conflict_type="SENDER_OVERLAP",
                rule_name="ceo@company.com (Executive Board vs Other)",
                yaml_rule=self.yaml_mgr.rules[0],
                outlook_rule_info={"name": "Other"},
                suggested_action="MERGE",
            ),
            RuleConflict(
                conflict_type="LEGACY_RULE",
                rule_name="Skip Me",
                yaml_rule=None,
                outlook_rule_info={"name": "Skip Me"},
                suggested_action="IGNORE",
            ),
        ]
        dlg = self._make_dialog_with_conflicts(conflicts)

        with patch.object(self.sync_engine, "push_to_outlook", wraps=self.sync_engine.push_to_outlook) as mock_push, \
             patch("gui.conflict_dialog.messagebox.askyesno") as mock_ask, \
             patch("gui.conflict_dialog.messagebox.showinfo") as mock_info:
            dlg._execute_resolutions()

        mock_ask.assert_not_called()
        mock_push.assert_called_once_with(remove_legacy=False, remove_legacy_names=None)
        summary_msg = mock_info.call_args[0][1]
        self.assertIn("Imported to YAML: 0", summary_msg)
        self.assertIn("Overwritten in Outlook: 1", summary_msg)
        self.assertIn("Merged via Outlook sync: 1", summary_msg)
        self.assertIn("Ignored / Skipped: 1", summary_msg)

    def test_clean_import_asks_once_and_removes_original_outlook_rule_when_confirmed(self):
        legacy = FakeRule("Clean Legacy", enabled=True)
        legacy.Conditions.From.Enabled = True
        legacy.Conditions.From.Recipients.Add("clean@vendor.com")
        legacy.Actions.MoveToFolder.Enabled = True
        legacy.Actions.MoveToFolder.Folder = FakeFolder("Clean", FolderPath=r"\\Archive 2025\Vendors\Clean")
        self.default_store.GetRules()._rules.append(legacy)

        conflicts = self.detector.detect_conflicts()
        dlg = self._make_dialog_with_conflicts(conflicts)

        with patch("gui.conflict_dialog.messagebox.askyesno", return_value=True) as mock_ask, \
             patch("gui.conflict_dialog.messagebox.showinfo") as mock_info:
            dlg._execute_resolutions()

        mock_ask.assert_called_once()
        self.assertIn("Remove the original Outlook rules for the clean imports listed below?", mock_ask.call_args[0][1])
        self.assertIn("Clean Legacy", mock_ask.call_args[0][1])
        remaining_names = {r.Name for r in self.default_store.GetRules()}
        self.assertNotIn("Clean Legacy", remaining_names)
        self.assertIn(managed_name(self.yaml_mgr, "Clean Legacy"), remaining_names)
        self.assertIn("Imported to YAML: 1", mock_info.call_args[0][1])

    def test_all_problematic_imports_do_not_ask_to_delete_and_warn_user(self):
        prob_rule = FakeRule("SentTo Legacy", enabled=True)
        prob_rule.Conditions.From.Enabled = True
        prob_rule.Conditions.From.Recipients.Add("a@ext.com")
        prob_rule.Conditions.SentTo.Enabled = True
        prob_rule.Conditions.SentTo.Recipients.Add("team@company.com")
        prob_rule.Actions.MoveToFolder.Enabled = True
        prob_rule.Actions.MoveToFolder.Folder = FakeFolder("Team", FolderPath=r"\\Archive 2025\Team")
        self.default_store.GetRules()._rules.append(prob_rule)

        conflicts = self.detector.detect_conflicts()
        dlg = self._make_dialog_with_conflicts(conflicts)

        with patch("gui.conflict_dialog.messagebox.askyesno") as mock_ask, \
             patch("gui.conflict_dialog.messagebox.showwarning") as mock_warn, \
             patch("gui.conflict_dialog.messagebox.showinfo"):
            dlg._execute_resolutions()

        # Must NOT ask to delete when all imported rules have warnings
        mock_ask.assert_not_called()
        mock_warn.assert_called_once()
        warn_text = mock_warn.call_args[0][1]
        self.assertIn("SentTo Legacy", warn_text)
        self.assertIn("DISABLED", warn_text)
        # Original Outlook rule is preserved
        self.assertIn("SentTo Legacy", {r.Name for r in self.default_store.GetRules()})

    def test_mixed_clean_and_problematic_imports_warn_and_default_to_no(self):
        clean_rule = FakeRule("Clean Rule", enabled=True)
        clean_rule.Conditions.From.Enabled = True
        clean_rule.Conditions.From.Recipients.Add("clean@ext.com")
        clean_rule.Actions.MoveToFolder.Enabled = True
        clean_rule.Actions.MoveToFolder.Folder = FakeFolder("Clean", FolderPath=r"\\Archive 2025\Clean")

        bad_rule = FakeRule("Unresolved Rule", enabled=True)
        bad_rule.Conditions.From.Enabled = True
        bad_rule.Conditions.From.Recipients._items.append(
            FakeRecipient(Address="/O=EXCHANGELABS/X", Name="Missing Person", AddressEntry=None)
        )
        bad_rule.Actions.MoveToFolder.Enabled = True
        bad_rule.Actions.MoveToFolder.Folder = FakeFolder("Bad", FolderPath=r"\\Archive 2025\Bad")

        self.default_store.GetRules()._rules.extend([clean_rule, bad_rule])

        conflicts = self.detector.detect_conflicts()
        dlg = self._make_dialog_with_conflicts(conflicts)

        with patch("gui.conflict_dialog.messagebox.askyesno", return_value=False) as mock_ask, \
             patch("gui.conflict_dialog.messagebox.showinfo"):
            dlg._execute_resolutions()

        mock_ask.assert_called_once()
        prompt_text = mock_ask.call_args[0][1]
        self.assertIn("Unresolved Rule", prompt_text)
        self.assertIn("Missing Person", prompt_text)
        self.assertIn("Clean Rule", prompt_text)
        self.assertIn("Remove the original Outlook rules for the clean imports listed below?", prompt_text)
        self.assertEqual(mock_ask.call_args[1].get("default"), messagebox.NO)
        # Neither original Outlook rule deleted when user keeps default No
        remaining = {r.Name for r in self.default_store.GetRules()}
        self.assertIn("Clean Rule", remaining)
        self.assertIn("Unresolved Rule", remaining)

    def test_targeted_legacy_removal_deletes_only_clean_imported_rule_not_problematic_or_other_legacy(self):
        # 1. Clean importable Outlook rule
        clean_rule = FakeRule("Clean Import Rule", enabled=True)
        clean_rule.Conditions.From.Enabled = True
        clean_rule.Conditions.From.Recipients.Add("clean@ext.com")
        clean_rule.Actions.MoveToFolder.Enabled = True
        clean_rule.Actions.MoveToFolder.Folder = FakeFolder("Clean", FolderPath=r"\\Archive 2025\Vendors\Clean")

        # 2. Problematic importable Outlook rule (From + Subject)
        prob_rule = FakeRule("Problem Import Rule", enabled=True)
        prob_rule.Conditions.From.Enabled = True
        prob_rule.Conditions.From.Recipients.Add("prob@ext.com")
        prob_rule.Conditions.Subject.Enabled = True
        prob_rule.Conditions.Subject.Text = ["Alert"]
        prob_rule.Actions.MoveToFolder.Enabled = True
        prob_rule.Actions.MoveToFolder.Folder = FakeFolder("Prob", FolderPath=r"\\Archive 2025\Vendors\Prob")

        # 3. Another existing unprefixed legacy rule matching YAML "Executive Board"
        other_legacy = FakeRule("Executive Board", enabled=True)
        other_legacy.Conditions.From.Enabled = True
        other_legacy.Conditions.From.Recipients.Add("ceo@company.com")
        other_legacy.Actions.MoveToFolder.Enabled = True
        other_legacy.Actions.MoveToFolder.Folder = FakeFolder(
            "Directors", FolderPath=r"\\Archive 2025\Management\Executive_Board\Directors"
        )

        self.default_store.GetRules()._rules.extend([clean_rule, prob_rule, other_legacy])

        # Only Clean Import Rule and Problem Import Rule are detected as LEGACY_RULE
        conflicts = [
            c for c in self.detector.detect_conflicts()
            if c.conflict_type == "LEGACY_RULE"
        ]
        self.assertEqual({c.rule_name for c in conflicts}, {"Clean Import Rule", "Problem Import Rule"})
        dlg = self._make_dialog_with_conflicts(conflicts)

        with patch("gui.conflict_dialog.messagebox.askyesno", return_value=True) as mock_ask, \
             patch("gui.conflict_dialog.messagebox.showinfo"):
            dlg._execute_resolutions()

        prompt_text = mock_ask.call_args[0][1]
        self.assertIn("DISABLED", prompt_text)
        self.assertIn("Remove the original Outlook rules for the clean imports listed below?", prompt_text)

        remaining = {r.Name: r for r in self.default_store.GetRules()}
        # Only Clean Import Rule was deleted; Problem Import Rule and Executive Board remain
        self.assertNotIn("Clean Import Rule", remaining)
        self.assertIn("Problem Import Rule", remaining)
        self.assertIn("Executive Board", remaining)
        # Managed rules: Clean Import Rule enabled, Problem Import Rule disabled
        self.assertTrue(remaining[managed_name(self.yaml_mgr, "Clean Import Rule")].Enabled)
        self.assertFalse(remaining[managed_name(self.yaml_mgr, "Problem Import Rule")].Enabled)
        self.assertFalse(remaining[managed_name(self.yaml_mgr, "Problem Import Rule", " (Keywords)")].Enabled)

        # Verify MockOutlookClient also respects remove_legacy_names
        mock = MockOutlookClient()
        ok, _ = mock.save_native_rules(
            [{"name": f"{MANAGED_PREFIX}New", "emails": ["a@b.com"], "target_folder": "X"}],
            "/mock/data/longp_Archive_2025.pst",
            remove_legacy=True,
            legacy_base_names=["Executive Board", "Engineering"],
            remove_legacy_names=["Executive Board"],
        )
        self.assertTrue(ok)
        mock_names = {r["name"] for r in mock.get_native_rules()}
        self.assertNotIn("Executive Board", mock_names)
        self.assertIn("Engineering", mock_names)
