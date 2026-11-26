"""Tests for Phase 2: managed rule lifecycle, reconciliation, legacy migration, and conflict matching."""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from core.conflict_detector import ConflictDetector
from core.models import MANAGED_PREFIX, RuleConfig
from core.outlook_client import WindowsOutlookClient
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager
from gui.main_window import MainWindow
from tests.fakes import FakeFolder, FakeNamespace, FakeRule, FakeStore


class TestPhase2LifecycleAndReconcile(unittest.TestCase):
    """Tests managed rule reconcile, disabled rules, execution order, and migration using fakes."""

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

    def test_shrinking_split_rule_removes_excess_parts(self):
        # First push with 85 emails (3 parts with threshold 40)
        emails_85 = [f"user{i}@vendor.com" for i in range(85)]
        self.yaml_mgr.rules = [
            RuleConfig(
                id="r_big",
                name="Big Vendor",
                enabled=True,
                emails=emails_85,
                target_folder="Vendors\\Big",
            )
        ]
        ok, msg = self.sync_engine.push_to_outlook()
        self.assertTrue(ok, msg)
        self.assertEqual(
            {r.Name for r in self.default_store.GetRules()},
            {
                f"{MANAGED_PREFIX}Big Vendor (Part 1)",
                f"{MANAGED_PREFIX}Big Vendor (Part 2)",
                f"{MANAGED_PREFIX}Big Vendor (Part 3)",
            },
        )

        # Shrink to 45 emails (2 parts -> Part 3 removed)
        self.yaml_mgr.rules[0].emails = emails_85[:45]
        ok, msg = self.sync_engine.push_to_outlook()
        self.assertTrue(ok, msg)
        self.assertEqual(
            {r.Name for r in self.default_store.GetRules()},
            {
                f"{MANAGED_PREFIX}Big Vendor (Part 1)",
                f"{MANAGED_PREFIX}Big Vendor (Part 2)",
            },
        )
        self.assertIn("Removed: 1", msg)

        # Shrink to 3 emails (1 rule without Part suffix -> Part 1 and Part 2 both removed safely)
        self.yaml_mgr.rules[0].emails = emails_85[:3]
        ok, msg = self.sync_engine.push_to_outlook()
        self.assertTrue(ok, msg)
        self.assertEqual(
            {r.Name for r in self.default_store.GetRules()},
            {f"{MANAGED_PREFIX}Big Vendor"},
        )
        self.assertIn("Removed: 2", msg)

    def test_deleted_and_renamed_yaml_rules_remove_old_managed_outlook_rules(self):
        self.yaml_mgr.rules = [
            RuleConfig(id="r1", name="Alpha", enabled=True, emails=["a@x.com"], target_folder="F1"),
            RuleConfig(id="r2", name="Beta", enabled=True, emails=["b@x.com"], target_folder="F2"),
            RuleConfig(id="r3", name="Gamma", enabled=True, emails=["c@x.com"], target_folder="F3"),
        ]
        ok, _ = self.sync_engine.push_to_outlook()
        self.assertTrue(ok)
        self.assertEqual(self.default_store.GetRules().Count, 3)

        # Delete Alpha & Beta, rename Gamma -> GammaRenamed (tests consecutive removals in FakeRules)
        self.yaml_mgr.rules = [
            RuleConfig(id="r3", name="GammaRenamed", enabled=True, emails=["c@x.com"], target_folder="F3"),
        ]
        ok, msg = self.sync_engine.push_to_outlook()
        self.assertTrue(ok, msg)
        self.assertEqual(
            {r.Name for r in self.default_store.GetRules()},
            {f"{MANAGED_PREFIX}GammaRenamed"},
        )
        self.assertIn("Removed: 3", msg)

    def test_disabled_yaml_rule_is_compiled_and_disabled_in_outlook(self):
        self.yaml_mgr.rules = [
            RuleConfig(id="r1", name="Paused Rule", enabled=True, emails=["a@x.com"], target_folder="F1")
        ]
        ok, _ = self.sync_engine.push_to_outlook()
        self.assertTrue(ok)
        self.assertTrue(list(self.default_store.GetRules())[0].Enabled)

        # Disable in YAML and sync again -> must remain in Outlook with Enabled=False
        self.yaml_mgr.rules[0].enabled = False
        ok, msg = self.sync_engine.push_to_outlook()
        self.assertTrue(ok, msg)
        rules = list(self.default_store.GetRules())
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].Name, f"{MANAGED_PREFIX}Paused Rule")
        self.assertFalse(rules[0].Enabled)
        self.assertIn("Disabled: 1", msg)

    def test_user_created_unprefixed_rule_is_untouched(self):
        user_rule = FakeRule("My Personal Filter", enabled=True, execution_order=99)
        user_rule.Conditions.From.Enabled = True
        user_rule.Conditions.From.Recipients.Add("friend@gmail.com")
        user_rule.Actions.MoveToFolder.Enabled = True
        user_rule.Actions.MoveToFolder.Folder = FakeFolder("Personal")
        user_rule.Actions.Stop.Enabled = False
        self.default_store.GetRules()._rules.append(user_rule)

        ok, msg = self.sync_engine.push_to_outlook(remove_legacy=True)
        self.assertTrue(ok, msg)

        rules_by_name = {r.Name: r for r in self.default_store.GetRules()}
        self.assertIn("My Personal Filter", rules_by_name)
        preserved = rules_by_name["My Personal Filter"]
        self.assertTrue(preserved.Enabled)
        self.assertFalse(preserved.Actions.Stop.Enabled)
        self.assertEqual(preserved.ExecutionOrder, 99)
        self.assertEqual([r.Address for r in preserved.Conditions.From.Recipients], ["friend@gmail.com"])

    def test_execution_order_stop_enabled_and_match_message_alignment(self):
        self.yaml_mgr.rules = [
            RuleConfig(
                id="r_dom_first",
                name="Domain First In Yaml",
                enabled=True,
                domains=["@vendor.com"],
                subject_keywords=["Invoice"],
                target_folder="Vendors",
            ),
            RuleConfig(
                id="r_email_second",
                name="Exact VIP Second",
                enabled=True,
                emails=["vip@vendor.com"],
                target_folder="VIP",
            ),
            RuleConfig(
                id="rule_unclassified",
                name="[Unclassified]",
                enabled=True,
                target_folder="_Unclassified",
            ),
        ]
        self.yaml_mgr.unclassified_pool = ["orphan@other.com"]

        # Place unclassified first initially in YAML to verify ExecutionOrder puts it last
        self.yaml_mgr.rules = [
            self.yaml_mgr.rules[2],
            self.yaml_mgr.rules[0],
            self.yaml_mgr.rules[1],
        ]

        ok, msg = self.sync_engine.push_to_outlook()
        self.assertTrue(ok, msg)

        rules_by_name = {r.Name: r for r in self.default_store.GetRules()}
        r_email = rules_by_name[f"{MANAGED_PREFIX}Exact VIP Second"]
        r_domain = rules_by_name[f"{MANAGED_PREFIX}Domain First In Yaml (Domains)"]
        r_kw = rules_by_name[f"{MANAGED_PREFIX}Domain First In Yaml (Keywords)"]
        r_unclass = rules_by_name[f"{MANAGED_PREFIX}[Unclassified]"]

        for r in (r_email, r_domain, r_kw, r_unclass):
            self.assertTrue(r.Actions.Stop.Enabled)

        self.assertEqual(r_email.ExecutionOrder, 1)
        self.assertEqual(r_domain.ExecutionOrder, 2)
        self.assertEqual(r_kw.ExecutionOrder, 3)
        self.assertEqual(r_unclass.ExecutionOrder, 4)

        # match_message must also pick exact email over domain regardless of YAML order
        matched, _ = self.sync_engine.match_message("vip@vendor.com", "Invoice #1")
        self.assertIsNotNone(matched)
        self.assertEqual(matched.id, "r_email_second")

    def test_execution_order_places_managed_rules_after_user_unprefixed_rules(self):
        user_rule_1 = FakeRule("User Priority 1", enabled=True, execution_order=1)
        user_rule_1.Conditions.From.Enabled = True
        user_rule_1.Conditions.From.Recipients.Add("boss@company.com")
        user_rule_2 = FakeRule("User Priority 2", enabled=True, execution_order=2)
        user_rule_2.Conditions.Subject.Enabled = True
        user_rule_2.Conditions.Subject.Text = ["Payroll"]
        self.default_store.GetRules()._rules.extend([user_rule_1, user_rule_2])

        self.yaml_mgr.rules = [
            RuleConfig(
                id="r_dom",
                name="Vendors",
                enabled=True,
                domains=["@vendor.com"],
                target_folder="Vendors",
            ),
            RuleConfig(
                id="r_email",
                name="VIP",
                enabled=True,
                emails=["vip@vendor.com"],
                target_folder="VIP",
            ),
        ]

        ok, msg = self.sync_engine.push_to_outlook()
        self.assertTrue(ok, msg)

        # User rules keep their ExecutionOrder untouched; managed rules start at 2 + 1
        self.assertEqual(user_rule_1.ExecutionOrder, 1)
        self.assertEqual(user_rule_2.ExecutionOrder, 2)
        rules_by_name = {r.Name: r for r in self.default_store.GetRules()}
        self.assertEqual(rules_by_name[f"{MANAGED_PREFIX}VIP"].ExecutionOrder, 3)
        self.assertEqual(rules_by_name[f"{MANAGED_PREFIX}Vendors (Domains)"].ExecutionOrder, 4)

    def test_legacy_rule_with_sentto_condition_or_unreadable_conditions_is_not_disabled(self):
        sentto_legacy = FakeRule("Executive Board", enabled=True)
        sentto_legacy.Conditions.SentTo.Enabled = True
        sentto_legacy.Conditions.SentTo.Recipients.Add("board-alias@company.com")
        sentto_legacy.Actions.MoveToFolder.Enabled = True
        sentto_legacy.Actions.MoveToFolder.Folder = FakeFolder("Directors")

        class UnreadableConditions:
            @property
            def Count(self):
                raise RuntimeError("COM E_FAIL")

        unreadable_legacy = FakeRule("SCADA PLC Maintenance", enabled=True)
        unreadable_legacy.Conditions = UnreadableConditions()
        unreadable_legacy.Actions.MoveToFolder.Enabled = True
        unreadable_legacy.Actions.MoveToFolder.Folder = FakeFolder("PLC_Unit")

        self.default_store.GetRules()._rules.extend([sentto_legacy, unreadable_legacy])

        ok, msg = self.sync_engine.push_to_outlook(remove_legacy=False)
        self.assertTrue(ok, msg)
        self.assertTrue(sentto_legacy.Enabled)
        self.assertTrue(unreadable_legacy.Enabled)
        self.assertNotIn("Disabled broken", msg)

    def test_broken_conditionless_legacy_rule_is_disabled_immediately_and_removed_only_with_flag(self):
        broken_legacy = FakeRule("Executive Board", enabled=True)
        broken_legacy.Conditions.From.Enabled = False
        broken_legacy.Conditions.SenderAddress.Enabled = False
        broken_legacy.Conditions.Subject.Enabled = False
        broken_legacy.Actions.MoveToFolder.Enabled = True
        broken_legacy.Actions.MoveToFolder.Folder = FakeFolder("Directors")

        healthy_legacy = FakeRule("SCADA PLC Maintenance (Part 1)", enabled=True)
        healthy_legacy.Conditions.From.Enabled = True
        healthy_legacy.Conditions.From.Recipients.Add("eng1@company.com")
        healthy_legacy.Actions.MoveToFolder.Enabled = True
        healthy_legacy.Actions.MoveToFolder.Folder = FakeFolder("PLC_Unit")

        self.default_store.GetRules()._rules.extend([broken_legacy, healthy_legacy])

        # Sync without remove_legacy: broken rule MUST be disabled immediately, neither deleted yet
        ok, msg = self.sync_engine.push_to_outlook(remove_legacy=False)
        self.assertTrue(ok, msg)
        rules_by_name = {r.Name: r for r in self.default_store.GetRules()}

        self.assertIn("Executive Board", rules_by_name)
        self.assertFalse(rules_by_name["Executive Board"].Enabled)
        self.assertIn("Executive Board", msg)

        self.assertIn("SCADA PLC Maintenance (Part 1)", rules_by_name)
        self.assertTrue(rules_by_name["SCADA PLC Maintenance (Part 1)"].Enabled)
        self.assertIn("SCADA PLC Maintenance (Part 1)", msg)

        self.assertIn(f"{MANAGED_PREFIX}Executive Board", rules_by_name)

        # find_legacy_rules lists both unprefixed legacy rules matching YAML
        self.assertEqual(
            set(self.sync_engine.find_legacy_rules()),
            {"Executive Board", "SCADA PLC Maintenance (Part 1)"},
        )

        # Sync with remove_legacy=True removes both legacy rules, keeps managed rules
        ok2, msg2 = self.sync_engine.push_to_outlook(remove_legacy=True)
        self.assertTrue(ok2, msg2)
        remaining_names = {r.Name for r in self.default_store.GetRules()}
        self.assertNotIn("Executive Board", remaining_names)
        self.assertNotIn("SCADA PLC Maintenance (Part 1)", remaining_names)
        self.assertIn(f"{MANAGED_PREFIX}Executive Board", remaining_names)

    def test_conflict_detector_does_not_flag_split_rules_as_legacy_or_overlap(self):
        # Push managed rules including a split rule (> 40 emails)
        many_emails = [f"sup{i}@vendor.com" for i in range(45)]
        self.yaml_mgr.rules = [
            RuleConfig(
                id="rule_suppliers",
                name="Omron Equipment",
                enabled=True,
                emails=many_emails,
                domains=["@omron.com"],
                target_folder=r"Purchasing_Team\Vendor_Part\Omron_Unit",
            )
        ]
        ok, _ = self.sync_engine.push_to_outlook()
        self.assertTrue(ok)

        # Also add an unprefixed split rule and one truly unknown legacy rule
        unprefixed_split = FakeRule("Omron Equipment (Part 2)", enabled=True)
        unprefixed_split.Conditions.From.Enabled = True
        unprefixed_split.Conditions.From.Recipients.Add("sup41@vendor.com")
        unprefixed_split.Actions.MoveToFolder.Enabled = True
        unprefixed_split.Actions.MoveToFolder.Folder = FakeFolder(
            "Omron_Unit", FolderPath=r"\\Archive 2025\Purchasing_Team\Vendor_Part\Omron_Unit"
        )

        unknown_legacy = FakeRule("Adhoc Personal Rule", enabled=True)
        unknown_legacy.Conditions.From.Enabled = True
        unknown_legacy.Conditions.From.Recipients.Add("stranger@example.com")
        unknown_legacy.Actions.MoveToFolder.Enabled = True
        unknown_legacy.Actions.MoveToFolder.Folder = FakeFolder("Misc")

        self.default_store.GetRules()._rules.extend([unprefixed_split, unknown_legacy])

        detector = ConflictDetector(self.yaml_mgr, self.outlook)
        conflicts = detector.detect_conflicts()

        legacy_names = [c.rule_name for c in conflicts if c.conflict_type == "LEGACY_RULE"]
        overlap_names = [c.rule_name for c in conflicts if c.conflict_type == "SENDER_OVERLAP"]
        self.assertEqual(legacy_names, ["Adhoc Personal Rule"])
        self.assertEqual(overlap_names, [])

    def test_main_window_sync_prompts_once_for_legacy_cleanup(self):
        legacy = FakeRule("Executive Board", enabled=True)
        legacy.Conditions.From.Enabled = True
        legacy.Conditions.From.Recipients.Add("ceo@company.com")
        legacy.Actions.MoveToFolder.Enabled = True
        legacy.Actions.MoveToFolder.Folder = FakeFolder("Directors")
        self.default_store.GetRules()._rules.append(legacy)

        with patch("gui.main_window.YamlConfigManager", return_value=self.yaml_mgr), \
             patch("gui.main_window.get_outlook_client", return_value=self.outlook), \
             patch("gui.main_window.messagebox.askyesno", side_effect=[True, True]) as mock_ask, \
             patch("gui.main_window.messagebox.showinfo") as mock_info:
            app = MainWindow(self.config_path)
            app.withdraw()
            try:
                app._sync_to_outlook()
            finally:
                app.destroy()

        self.assertEqual(mock_ask.call_count, 2)
        second_prompt = mock_ask.call_args_list[1][0][1]
        self.assertIn("Executive Board", second_prompt)
        mock_info.assert_called_once()
        self.assertNotIn("Executive Board", {r.Name for r in self.default_store.GetRules()})
        self.assertIn(f"{MANAGED_PREFIX}Executive Board", {r.Name for r in self.default_store.GetRules()})
