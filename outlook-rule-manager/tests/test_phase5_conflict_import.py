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
from core.outlook_client import WindowsOutlookClient
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager
from gui.conflict_dialog import ConflictDialog
from tests.fakes import (
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
        # Rule 1: SMTP + ExchangeUser SMTP + unresolvable display name + domains + keywords (no unsupported)
        r1 = FakeRule("Legacy Rich Rule", enabled=True)
        r1.Conditions.From.Enabled = True
        r1.Conditions.From.Recipients.Add("direct@vendor.com")
        r1.Conditions.From.Recipients._items.append(
            FakeRecipient(
                Address="/O=EXCHANGELABS/OU=EXCHANGE/CN=RECIPIENTS/CN=A",
                Name="Nguyen Van A",
                AddressEntry=FakeAddressEntry(FakeExchangeUser("vana@company.com")),
            )
        )
        r1.Conditions.From.Recipients._items.append(
            FakeRecipient(
                Address="/O=EXCHANGELABS/OU=EXCHANGE/CN=RECIPIENTS/CN=UNKNOWN",
                Name="Unknown Former Staff",
                AddressEntry=FakeAddressEntry(None),
            )
        )
        r1.Conditions.SenderAddress.Enabled = True
        r1.Conditions.SenderAddress.Address = ["@Omron.COM", "mitsubishi.com"]
        r1.Conditions.Subject.Enabled = True
        r1.Conditions.Subject.Text = ["URGENT", "SCADA"]
        r1.Actions.MoveToFolder.Enabled = True
        r1.Actions.MoveToFolder.Folder = FakeFolder(
            "Omron_Unit", FolderPath=r"\\Archive 2025\Purchasing_Team\Vendor_Part\Omron_Unit"
        )

        # Rule 2: Unsupported condition (SentTo enabled)
        r2 = FakeRule("Legacy SentTo Rule", enabled=True)
        r2.Conditions.From.Enabled = True
        r2.Conditions.From.Recipients.Add("sender@partner.com")
        r2.Conditions.SentTo.Enabled = True
        r2.Conditions.SentTo.Recipients.Add("alias@company.com")
        r2.Actions.MoveToFolder.Enabled = True
        r2.Actions.MoveToFolder.Folder = FakeFolder("Alias", FolderPath=r"\\Archive 2025\Team\Alias")

        self.default_store.GetRules()._rules.extend([r1, r2])

        native_rules = self.outlook.get_native_rules()
        by_name = {r["name"]: r for r in native_rules}

        info1 = by_name["Legacy Rich Rule"]
        self.assertEqual(info1["emails"], ["direct@vendor.com", "vana@company.com"])
        self.assertNotIn("Unknown Former Staff", info1["emails"])
        self.assertEqual(info1["unresolved_recipients"], ["Unknown Former Staff"])
        self.assertEqual(info1["domains"], ["@omron.com", "mitsubishi.com"])
        self.assertEqual(info1["subject_keywords"], ["URGENT", "SCADA"])
        self.assertFalse(info1["has_unsupported_conditions"])

        info2 = by_name["Legacy SentTo Rule"]
        self.assertTrue(info2["has_unsupported_conditions"])

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

        imported = next(r for r in self.yaml_mgr.rules if r.name == "Imported Multi")
        self.assertEqual(imported.target_folder, r"Team\Part\Unit")
        self.assertEqual(imported.emails, ["a@vendor.com"])
        self.assertEqual(imported.domains, ["@vendor.com", "@omron.com"])
        self.assertEqual(imported.subject_keywords, ["Invoice", "PO"])

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
        mock_push.assert_called_once_with(remove_legacy=False)
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
        self.assertIn("Clean Legacy", mock_ask.call_args[0][1])
        remaining_names = {r.Name for r in self.default_store.GetRules()}
        self.assertNotIn("Clean Legacy", remaining_names)
        self.assertIn(f"{MANAGED_PREFIX}Clean Legacy", remaining_names)
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
        self.assertIn("SentTo Legacy", mock_warn.call_args[0][1])
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
        self.assertEqual(mock_ask.call_args[1].get("default"), messagebox.NO)
        # Neither original Outlook rule deleted when user keeps default No
        remaining = {r.Name for r in self.default_store.GetRules()}
        self.assertIn("Clean Rule", remaining)
        self.assertIn("Unresolved Rule", remaining)
