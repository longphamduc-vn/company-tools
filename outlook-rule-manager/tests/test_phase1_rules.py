"""Tests for Phase 1: condition-safe Outlook rule compilation and splitting."""
import os
import shutil
import tempfile
import tkinter as tk
import unittest
from datetime import datetime

from core.models import EmailMessage, MANAGED_PREFIX, RuleConfig
from core.outlook_client import MockOutlookClient, WindowsOutlookClient
from core.rule_splitter import split_rule_recipients
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager
from gui.triage_view import TriageView
from tests.fakes import FakeNamespace, FakeRule, FakeStore


class TestRuleSplitter(unittest.TestCase):
    """Tests for split_rule_recipients across edge sizes and domains."""

    def test_zero_emails_and_zero_domains(self):
        self.assertEqual(split_rule_recipients("EmptyRule", [], [], max_recipients=40), [])

    def test_one_email(self):
        res = split_rule_recipients("Single", ["a@x.com"], [], max_recipients=40)
        self.assertEqual(res, [("Single", ["a@x.com"], [])])

    def test_exact_threshold_40_emails(self):
        emails = [f"u{i}@x.com" for i in range(40)]
        res = split_rule_recipients("Forty", emails, [], max_recipients=40)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0][0], "Forty")
        self.assertEqual(len(res[0][1]), 40)

    def test_41_emails_splits_into_two_parts(self):
        emails = [f"u{i}@x.com" for i in range(41)]
        res = split_rule_recipients("FortyOne", emails, [], max_recipients=40)
        self.assertEqual([r[0] for r in res], ["FortyOne (Part 1)", "FortyOne (Part 2)"])
        self.assertEqual([len(r[1]) for r in res], [40, 1])

    def test_81_emails_splits_into_three_parts(self):
        emails = [f"u{i}@x.com" for i in range(81)]
        res = split_rule_recipients("EightyOne", emails, [], max_recipients=40)
        self.assertEqual(
            [r[0] for r in res],
            ["EightyOne (Part 1)", "EightyOne (Part 2)", "EightyOne (Part 3)"],
        )
        self.assertEqual([len(r[1]) for r in res], [40, 40, 1])

    def test_long_domain_list_splits_by_threshold(self):
        domains = [f"@d{i}.com" for i in range(85)]
        res = split_rule_recipients("Vendors", [], domains, max_recipients=40)
        self.assertEqual(
            [r[0] for r in res],
            [
                "Vendors (Domains) (Part 1)",
                "Vendors (Domains) (Part 2)",
                "Vendors (Domains) (Part 3)",
            ],
        )
        self.assertEqual([len(r[2]) for r in res], [40, 40, 5])
        self.assertTrue(all(r[1] == [] for r in res))

    def test_non_positive_max_recipients_falls_back_to_40(self):
        emails = [f"u{i}@x.com" for i in range(41)]
        for bad_limit in (0, -10):
            res = split_rule_recipients("Fallback", emails, [], max_recipients=bad_limit)
            self.assertEqual([len(r[1]) for r in res], [40, 1])


class TestSaveNativeRulesWithFakes(unittest.TestCase):
    """Tests WindowsOutlookClient.save_native_rules and SyncEngine using FakeNamespace."""

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

    def test_domain_only_rule_enables_sender_address_and_disables_from(self):
        self.yaml_mgr.rules = [
            RuleConfig(
                id="r_dom",
                name="Omron Domain",
                enabled=True,
                domains=["@omron.com"],
                target_folder="Vendors\\Omron",
            )
        ]
        ok, msg = self.sync_engine.push_to_outlook()
        self.assertTrue(ok, msg)

        rules = list(self.default_store.GetRules())
        self.assertEqual(len(rules), 1)
        rule = rules[0]
        self.assertEqual(rule.Name, f"{MANAGED_PREFIX}Omron Domain (Domains)")
        self.assertTrue(rule.Conditions.SenderAddress.Enabled)
        self.assertEqual(rule.Conditions.SenderAddress.Address, ["@omron.com"])
        self.assertFalse(rule.Conditions.From.Enabled)
        self.assertEqual(rule.Conditions.From.Recipients.Count, 0)
        self.assertFalse(rule.Conditions.Subject.Enabled)

    def test_empty_rule_is_not_created_and_warns_in_message(self):
        self.yaml_mgr.rules = [
            RuleConfig(
                id="rule_unclassified",
                name="[Unclassified]",
                enabled=True,
                target_folder="_Unclassified",
            ),
            RuleConfig(
                id="rule_empty",
                name="Empty_Folder",
                enabled=True,
                target_folder="Empty_Folder",
            ),
        ]
        self.yaml_mgr.unclassified_pool = []

        ok, msg = self.sync_engine.push_to_outlook()
        self.assertTrue(ok, msg)
        self.assertEqual(self.default_store.GetRules().Count, 0)
        self.assertIn("skipped rules with no conditions: Empty_Folder", msg)
        # An empty unclassified pool is normal and must not be reported
        self.assertNotIn("[Unclassified]", msg)

    def test_save_native_rules_defensive_empty_rule_disables_existing_and_warns(self):
        existing = FakeRule("OrphanRule", enabled=True)
        existing.Conditions.From.Enabled = True
        existing.Conditions.From.Recipients.Add("old@vendor.com")
        self.default_store.GetRules()._rules.append(existing)

        ok, msg = self.outlook.save_native_rules(
            [
                {"name": "NewEmpty", "enabled": True, "emails": [], "domains": [], "subject_keywords": []},
                {"name": "OrphanRule", "enabled": True, "emails": [], "domains": [], "subject_keywords": []},
            ],
            self.store_path,
        )
        self.assertTrue(ok, msg)
        rules_by_name = {r.Name: r for r in self.default_store.GetRules()}
        self.assertNotIn("NewEmpty", rules_by_name)
        self.assertFalse(rules_by_name["OrphanRule"].Enabled)
        self.assertIn("NewEmpty", msg)
        self.assertIn("OrphanRule", msg)

    def test_email_and_domain_and_keyword_compile_to_separate_subrules(self):
        self.yaml_mgr.rules = [
            RuleConfig(
                id="r_mixed",
                name="Mixed Rule",
                enabled=True,
                emails=["lead@omron.com"],
                domains=["@omron.com"],
                subject_keywords=["SCADA"],
                target_folder="Vendors\\Omron",
            )
        ]
        ok, msg = self.sync_engine.push_to_outlook()
        self.assertTrue(ok, msg)

        rules = {r.Name: r for r in self.default_store.GetRules()}
        self.assertEqual(
            set(rules.keys()),
            {
                f"{MANAGED_PREFIX}Mixed Rule",
                f"{MANAGED_PREFIX}Mixed Rule (Domains)",
                f"{MANAGED_PREFIX}Mixed Rule (Keywords)",
            },
        )

        # Email sub-rule
        r_email = rules[f"{MANAGED_PREFIX}Mixed Rule"]
        self.assertTrue(r_email.Conditions.From.Enabled)
        self.assertEqual([rec.Address for rec in r_email.Conditions.From.Recipients], ["lead@omron.com"])
        self.assertFalse(r_email.Conditions.SenderAddress.Enabled)
        self.assertFalse(r_email.Conditions.Subject.Enabled)

        # Domain sub-rule
        r_dom = rules[f"{MANAGED_PREFIX}Mixed Rule (Domains)"]
        self.assertFalse(r_dom.Conditions.From.Enabled)
        self.assertTrue(r_dom.Conditions.SenderAddress.Enabled)
        self.assertEqual(r_dom.Conditions.SenderAddress.Address, ["@omron.com"])
        self.assertFalse(r_dom.Conditions.Subject.Enabled)

        # Keyword sub-rule
        r_kw = rules[f"{MANAGED_PREFIX}Mixed Rule (Keywords)"]
        self.assertFalse(r_kw.Conditions.From.Enabled)
        self.assertFalse(r_kw.Conditions.SenderAddress.Enabled)
        self.assertTrue(r_kw.Conditions.Subject.Enabled)
        self.assertEqual(r_kw.Conditions.Subject.Text, ["SCADA"])

    def test_clearing_emails_on_existing_rule_disables_from_and_clears_recipients(self):
        existing = FakeRule("VendorRule", enabled=True)
        existing.Conditions.From.Enabled = True
        existing.Conditions.From.Recipients.Add("stale1@vendor.com")
        existing.Conditions.From.Recipients.Add("stale2@vendor.com")
        existing.Conditions.Subject.Enabled = True
        existing.Conditions.Subject.Text = ["OLD_KW"]
        self.default_store.GetRules()._rules.append(existing)

        ok, msg = self.outlook.save_native_rules(
            [
                {
                    "name": "VendorRule",
                    "enabled": True,
                    "emails": [],
                    "domains": ["@vendor.com"],
                    "subject_keywords": [],
                    "target_folder": "Vendors",
                }
            ],
            self.store_path,
        )
        self.assertTrue(ok, msg)
        self.assertFalse(existing.Conditions.From.Enabled)
        self.assertEqual(existing.Conditions.From.Recipients.Count, 0)
        self.assertFalse(existing.Conditions.Subject.Enabled)
        self.assertEqual(existing.Conditions.Subject.Text, [])
        self.assertTrue(existing.Conditions.SenderAddress.Enabled)
        self.assertEqual(existing.Conditions.SenderAddress.Address, ["@vendor.com"])

        # Now update back to email-only and verify SenderAddress is disabled and cleared
        ok2, msg2 = self.outlook.save_native_rules(
            [
                {
                    "name": "VendorRule",
                    "enabled": True,
                    "emails": ["new@vendor.com"],
                    "domains": [],
                    "subject_keywords": [],
                    "target_folder": "Vendors",
                }
            ],
            self.store_path,
        )
        self.assertTrue(ok2, msg2)
        self.assertFalse(existing.Conditions.SenderAddress.Enabled)
        self.assertEqual(existing.Conditions.SenderAddress.Address, [])
        self.assertTrue(existing.Conditions.From.Enabled)
        self.assertEqual([r.Address for r in existing.Conditions.From.Recipients], ["new@vendor.com"])

    def test_empty_array_assignment_error_does_not_fail_sync(self):
        class StrictEmptySenderAddress:
            def __init__(self):
                self.Enabled = True
                self._address = ["@old.com"]

            @property
            def Address(self):
                return self._address

            @Address.setter
            def Address(self, value):
                if value == []:
                    raise RuntimeError("COM does not accept empty array")
                self._address = value

        class StrictEmptySubject:
            def __init__(self):
                self.Enabled = True
                self._text = ["OLD"]

            @property
            def Text(self):
                return self._text

            @Text.setter
            def Text(self, value):
                if value == []:
                    raise RuntimeError("COM does not accept empty array")
                self._text = value

        existing = FakeRule("StrictComRule", enabled=True)
        existing.Conditions.SenderAddress = StrictEmptySenderAddress()
        existing.Conditions.Subject = StrictEmptySubject()
        self.default_store.GetRules()._rules.append(existing)

        ok, msg = self.outlook.save_native_rules(
            [
                {
                    "name": "StrictComRule",
                    "enabled": True,
                    "emails": ["only@vendor.com"],
                    "domains": [],
                    "subject_keywords": [],
                    "target_folder": "Vendors",
                }
            ],
            self.store_path,
        )
        self.assertTrue(ok, msg)
        self.assertFalse(existing.Conditions.SenderAddress.Enabled)
        self.assertFalse(existing.Conditions.Subject.Enabled)
        self.assertTrue(existing.Conditions.From.Enabled)


class TestTriageDefaultMatchMode(unittest.TestCase):
    """Ensure TriageView defaults new rule match_mode to 'email' without domain heuristics."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        sample_config = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")
        shutil.copy2(sample_config, self.config_path)

        self.yaml_mgr = YamlConfigManager(self.config_path)
        self.outlook = MockOutlookClient()
        self.sync_engine = SyncEngine(self.yaml_mgr, self.outlook)
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_stage_create_new_rule_defaults_to_email_for_vendor_domains(self):
        view = TriageView(self.root, self.yaml_mgr, self.outlook, self.sync_engine)
        msg = EmailMessage(
            entry_id="MSG_OMRON",
            subject="Sensor Quote",
            sender_name="Sales",
            sender_email="sales@omron.com",
            received_time=datetime.now(),
        )
        view._stage_create_new_rule(msg)
        self.assertEqual(len(view.staged_actions), 1)
        self.assertEqual(view.staged_actions[0].match_mode, "email")
