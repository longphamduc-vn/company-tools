"""Tests for Phase 3: safe store lookup, rollover rollback, folder hierarchy preservation, and move_message."""
import os
import shutil
import tempfile
import unittest

from core.models import MANAGED_PREFIX, RuleConfig
from core.outlook_client import MockOutlookClient, WindowsOutlookClient
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager
from tests.fakes import FakeFolder, FakeNamespace, FakeRule, FakeStore


class _FakeMailItem:
    """Minimal MailItem double recording Move(folder) calls."""

    def __init__(self):
        self.moved_to = None

    def Move(self, folder):
        self.moved_to = folder


class TestPhase3SafeRolloverAndStoreLookup(unittest.TestCase):
    """Tests _find_store, store_exists, perform_rollover, save_native_rules, and move_message."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        sample_config = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")
        shutil.copy2(sample_config, self.config_path)

        self.yaml_mgr = YamlConfigManager(self.config_path)
        self.store_2025_path = self.yaml_mgr.stores["active_archive"].file_path
        self.store_2026_path = r"C:\Outlook_Data\longp_Archive_2026.pst"

        self.default_store = FakeStore("Primary Mailbox", "", is_data_file=False)
        self.store_2025_old = FakeStore("Archive 2025 Old", r"C:\Outlook_Data\Archive_2025_Old.pst")
        self.store_2026 = FakeStore("Archive 2026", self.store_2026_path)

        self.namespace = FakeNamespace(
            stores=[self.default_store, self.store_2025_old, self.store_2026],
            default_store=self.default_store,
        )
        self.outlook = WindowsOutlookClient(namespace=self.namespace)
        self.sync_engine = SyncEngine(self.yaml_mgr, self.outlook)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_exact_store_matching_does_not_match_substring(self):
        # "Archive 2025" must NOT match "Archive 2025 Old"
        self.assertIsNone(self.outlook._find_store("Archive 2025"))
        self.assertFalse(self.outlook.store_exists("Archive 2025"))

        # Exact DisplayName match (case-insensitive)
        found_old = self.outlook._find_store("archive 2025 old")
        self.assertIs(found_old, self.store_2025_old)
        self.assertTrue(self.outlook.store_exists("ARCHIVE 2025 OLD"))

        # Exact FilePath match (normalized slashes/case)
        found_2026 = self.outlook._find_store("c:/outlook_data/LONGP_ARCHIVE_2026.PST")
        self.assertIs(found_2026, self.store_2026)

        # Empty identifier returns DefaultStore for _find_store, False for store_exists
        self.assertIs(self.outlook._find_store(""), self.default_store)
        self.assertFalse(self.outlook.store_exists(""))

        # MockOutlookClient.store_exists also uses exact matching
        mock = MockOutlookClient()
        self.assertFalse(mock.store_exists("Archive 2025"))
        self.assertTrue(mock.store_exists("longp Archive 2025"))
        self.assertTrue(mock.store_exists("/mock/data/longp_Archive_2025.pst"))

    def test_wrong_store_path_rollover_returns_false_without_touching_yaml_or_default_store(self):
        # First create a managed rule pointing to Archive 2025 Old
        self.yaml_mgr.stores["active_archive"].name = "Archive 2025 Old"
        self.yaml_mgr.stores["active_archive"].file_path = r"C:\Outlook_Data\Archive_2025_Old.pst"
        self.yaml_mgr.rules = [
            RuleConfig(
                id="r1",
                name="Team Rule",
                enabled=True,
                emails=["lead@company.com"],
                target_folder=r"Team\Part\Unit",
            )
        ]
        self.yaml_mgr.save()
        ok, msg = self.sync_engine.push_to_outlook()
        self.assertTrue(ok, msg)

        yaml_before = open(self.config_path, "r", encoding="utf-8").read()
        rule_obj = list(self.default_store.GetRules())[0]
        folder_before = rule_obj.Actions.MoveToFolder.Folder

        # Attempt rollover to non-existent store path
        ok, msg = self.sync_engine.perform_rollover("Archive 2099", r"C:\Outlook_Data\Missing_2099.pst")
        self.assertFalse(ok)
        self.assertIn("Missing_2099.pst", msg)

        # Memory & disk YAML unchanged, rule folder unchanged, DefaultStore has no folders created
        self.assertEqual(self.yaml_mgr.stores["active_archive"].name, "Archive 2025 Old")
        self.assertEqual(self.yaml_mgr.stores["active_archive"].file_path, r"C:\Outlook_Data\Archive_2025_Old.pst")
        self.assertEqual(open(self.config_path, "r", encoding="utf-8").read(), yaml_before)
        self.assertIs(rule_obj.Actions.MoveToFolder.Folder, folder_before)
        self.assertEqual(self.default_store.GetRootFolder().Folders.Count, 0)

    def test_rollover_failure_during_outlook_save_restores_memory_and_skips_yaml_save(self):
        self.yaml_mgr.stores["active_archive"].name = "Archive 2025 Old"
        self.yaml_mgr.stores["active_archive"].file_path = r"C:\Outlook_Data\Archive_2025_Old.pst"
        self.yaml_mgr.rules = [
            RuleConfig(id="r1", name="Team Rule", enabled=True, emails=["a@b.com"], target_folder=r"Team\Part\Unit")
        ]
        self.yaml_mgr.save()
        yaml_before = open(self.config_path, "r", encoding="utf-8").read()

        def fail_save(ShowProgress=False):
            raise RuntimeError("COM save failed")

        self.default_store.GetRules().Save = fail_save

        ok, msg = self.sync_engine.perform_rollover("Archive 2026", self.store_2026_path)
        self.assertFalse(ok)
        self.assertIn("COM save failed", msg)
        self.assertEqual(self.yaml_mgr.stores["active_archive"].name, "Archive 2025 Old")
        self.assertEqual(self.yaml_mgr.stores["active_archive"].file_path, r"C:\Outlook_Data\Archive_2025_Old.pst")
        self.assertEqual(open(self.config_path, "r", encoding="utf-8").read(), yaml_before)

    def test_rollover_preserves_nested_folder_hierarchy_and_leaves_unprefixed_rules_untouched(self):
        # Set up unprefixed user rule pointing to a folder in DefaultStore
        personal_folder = FakeFolder("PersonalFolder", FolderPath=r"\\Primary Mailbox\PersonalFolder")
        user_rule = FakeRule("User Personal Rule", enabled=True, execution_order=1)
        user_rule.Conditions.From.Enabled = True
        user_rule.Conditions.From.Recipients.Add("friend@gmail.com")
        user_rule.Actions.MoveToFolder.Enabled = True
        user_rule.Actions.MoveToFolder.Folder = personal_folder
        self.default_store.GetRules()._rules.append(user_rule)

        self.yaml_mgr.stores["active_archive"].name = "Archive 2025 Old"
        self.yaml_mgr.stores["active_archive"].file_path = r"C:\Outlook_Data\Archive_2025_Old.pst"
        self.yaml_mgr.rules = [
            RuleConfig(
                id="r_nested",
                name="Nested Unit",
                enabled=True,
                emails=["eng@company.com"],
                target_folder=r"Team\Part\Unit",
            )
        ]

        ok, msg = self.sync_engine.perform_rollover("Archive 2026", self.store_2026_path)
        self.assertTrue(ok, msg)

        # Managed rule points to Team\Part\Unit inside Archive 2026
        rules_by_name = {r.Name: r for r in self.default_store.GetRules()}
        managed_rule = rules_by_name[f"{MANAGED_PREFIX}Nested Unit"]
        self.assertEqual(
            managed_rule.Actions.MoveToFolder.Folder.FolderPath,
            r"\\Archive 2026\Team\Part\Unit",
        )
        # Unprefixed rule is completely untouched
        self.assertIs(rules_by_name["User Personal Rule"].Actions.MoveToFolder.Folder, personal_folder)
        self.assertEqual(self.default_store.GetRootFolder().Folders.Count, 0)

        # YAML saved with new store info
        reloaded = YamlConfigManager(self.config_path)
        self.assertEqual(reloaded.stores["active_archive"].name, "Archive 2026")
        self.assertEqual(reloaded.stores["active_archive"].file_path, self.store_2026_path)

    def test_save_native_rules_missing_store_returns_false_and_does_not_mutate_rules_or_default_store(self):
        existing_managed = FakeRule(f"{MANAGED_PREFIX}Existing Rule", enabled=True)
        existing_managed.Conditions.From.Enabled = True
        existing_managed.Conditions.From.Recipients.Add("keep@company.com")
        existing_managed.Actions.MoveToFolder.Enabled = True
        existing_folder = FakeFolder("KeepFolder")
        existing_managed.Actions.MoveToFolder.Folder = existing_folder
        self.default_store.GetRules()._rules.append(existing_managed)

        # Even if rules_data doesn't include Existing Rule (which reconcile would delete),
        # missing store must abort BEFORE touching/deleting any rules or creating folders.
        ok, msg = self.outlook.save_native_rules(
            [
                {
                    "name": f"{MANAGED_PREFIX}New Rule",
                    "enabled": True,
                    "emails": ["new@company.com"],
                    "domains": [],
                    "subject_keywords": [],
                    "target_folder": r"Team\NewFolder",
                }
            ],
            r"C:\Outlook_Data\DoesNotExist.pst",
        )
        self.assertFalse(ok)
        self.assertIn("DoesNotExist.pst", msg)
        self.assertEqual([r.Name for r in self.default_store.GetRules()], [f"{MANAGED_PREFIX}Existing Rule"])
        self.assertIs(existing_managed.Actions.MoveToFolder.Folder, existing_folder)
        self.assertEqual(self.default_store.GetRootFolder().Folders.Count, 0)

    def test_move_message_missing_store_returns_false_without_creating_folder_in_default_store(self):
        mail = _FakeMailItem()
        self.namespace._items["MSG_1"] = mail

        ok = self.outlook.move_message("MSG_1", r"Team\Part\Unit", r"C:\Outlook_Data\Missing.pst")
        self.assertFalse(ok)
        self.assertIsNone(mail.moved_to)
        self.assertEqual(self.default_store.GetRootFolder().Folders.Count, 0)

        # Valid target store moves message into that store's folder hierarchy
        ok_valid = self.outlook.move_message("MSG_1", r"Team\Part\Unit", self.store_2026_path)
        self.assertTrue(ok_valid)
        self.assertIsNotNone(mail.moved_to)
        self.assertEqual(mail.moved_to.FolderPath, r"\\Archive 2026\Team\Part\Unit")
        self.assertEqual(self.default_store.GetRootFolder().Folders.Count, 0)

    def test_mock_outlook_client_succeeds_with_copy_of_real_rules_yaml(self):
        real_config_src = os.path.join(os.path.dirname(__file__), "..", "config", "rules.yaml")
        real_config_copy = os.path.join(self.temp_dir, "real_rules_copy.yaml")
        shutil.copy2(real_config_src, real_config_copy)

        yaml_mgr = YamlConfigManager(real_config_copy)
        mock_client = MockOutlookClient()
        engine = SyncEngine(yaml_mgr, mock_client)

        store_path = yaml_mgr.stores["active_archive"].file_path
        ok, msg = engine.push_to_outlook()
        self.assertTrue(ok, msg)

        moved = mock_client.move_message("MSG_001", r"Management\Directors", store_path)
        self.assertTrue(moved)
