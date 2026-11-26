"""Tests for Phase 4: atomic YAML save, microsecond backups, unique IDs, group deletion, and domain normalization."""
import glob
import os
import shutil
import tempfile
import tkinter as tk
import unittest
from datetime import datetime
from unittest.mock import patch

import yaml

from core.conflict_detector import ConflictDetector, RuleConflict
from core.models import AddressGroup, EmailMessage, RuleConfig
from core.outlook_client import MockOutlookClient
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager
from gui.rule_manager_view import RuleManagerView
from gui.triage_view import StagedAction, TriageView


class TestPhase4YamlIntegrityAndIds(unittest.TestCase):
    """Tests backup versioning, atomic replace, store_id, single-save folder delete, IDs, groups, and domains."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        sample_config = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")
        shutil.copy2(sample_config, self.config_path)
        self.yaml_mgr = YamlConfigManager(self.config_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_multiple_saves_in_same_second_create_distinct_backups_and_keep_initial_state(self):
        initial_rule_ids = [r.id for r in self.yaml_mgr.rules]

        for idx in range(5):
            if idx == 0:
                # Delete first rule right before first save
                self.yaml_mgr.rules = self.yaml_mgr.rules[1:]
            else:
                self.yaml_mgr.unclassified_pool.append(f"extra{idx}@vendor.com")
            self.yaml_mgr.save()

        backups = sorted(
            glob.glob(os.path.join(self.yaml_mgr.backup_dir, "rules_*.yaml")),
            key=os.path.basename,
        )
        self.assertEqual(len(backups), 5)
        for path in backups:
            self.assertRegex(os.path.basename(path), r"^rules_\d{8}_\d{6}_\d{6}(?:_\d+)?\.yaml$")

        # First backup holds state BEFORE the first deletion
        with open(backups[0], "r", encoding="utf-8") as f:
            first_backup_data = yaml.safe_load(f)
        self.assertEqual([r["id"] for r in first_backup_data["rules"]], initial_rule_ids)

    def test_prune_backups_with_mixed_legacy_and_microsecond_formats(self):
        self.yaml_mgr.settings["backup_versions"] = 3
        mixed_names = [
            "rules_20261109_145516.yaml",
            "rules_20261109_145516_000001.yaml",
            "rules_20261109_145517.yaml",
            "rules_20261109_145517_500000.yaml",
            "rules_20261109_145518.yaml",
        ]
        for name in mixed_names:
            with open(os.path.join(self.yaml_mgr.backup_dir, name), "w", encoding="utf-8") as f:
                f.write("version: '2.0'\n")

        self.yaml_mgr._prune_backups()
        remaining = sorted(os.listdir(self.yaml_mgr.backup_dir))
        self.assertEqual(
            remaining,
            [
                "rules_20261109_145517.yaml",
                "rules_20261109_145517_500000.yaml",
                "rules_20261109_145518.yaml",
            ],
        )

    def test_atomic_save_permission_error_removes_tmp_and_preserves_original_yaml(self):
        original_content = open(self.config_path, "r", encoding="utf-8").read()
        self.yaml_mgr.unclassified_pool.append("unsaved@vendor.com")

        with patch("core.yaml_manager.os.replace", side_effect=PermissionError("Access is denied")):
            with self.assertRaises(RuntimeError) as ctx:
                self.yaml_mgr.save()

        self.assertIn("Failed to save configuration atomically", str(ctx.exception))
        self.assertFalse(os.path.exists(f"{self.config_path}.tmp"))
        self.assertEqual(open(self.config_path, "r", encoding="utf-8").read(), original_content)

    def test_store_id_persisted_when_non_empty_and_omitted_when_empty(self):
        # Empty store_id should not dirty YAML
        self.yaml_mgr.save()
        with open(self.config_path, "r", encoding="utf-8") as f:
            raw_without_id = yaml.safe_load(f)
        self.assertNotIn("store_id", raw_without_id["stores"]["active_archive"])

        # Non-empty store_id must survive load -> save -> load
        self.yaml_mgr.stores["active_archive"].store_id = "0000000038A1BB1005E5101AA1BB08002B2A56C2"
        self.yaml_mgr.save()
        reloaded = YamlConfigManager(self.config_path)
        self.assertEqual(
            reloaded.stores["active_archive"].store_id,
            "0000000038A1BB1005E5101AA1BB08002B2A56C2",
        )

    def test_delete_folder_hierarchy_five_rules_creates_single_backup(self):
        for i in range(5):
            self.yaml_mgr.rules.append(
                RuleConfig(
                    id=f"rule_batch_{i}",
                    name=f"Batch {i}",
                    emails=[f"batch{i}@vendor.com"],
                    target_folder=r"BulkTeam\SubPart",
                )
            )
        self.yaml_mgr.save()

        # Clear backups created during setup
        for b in glob.glob(os.path.join(self.yaml_mgr.backup_dir, "rules_*.yaml")):
            os.remove(b)

        affected = self.yaml_mgr.delete_folder_hierarchy(r"BulkTeam\SubPart", repool_addresses=True)
        self.assertEqual(affected, 5)
        backups = glob.glob(os.path.join(self.yaml_mgr.backup_dir, "rules_*.yaml"))
        self.assertEqual(len(backups), 1)
        for i in range(5):
            self.assertIn(f"batch{i}@vendor.com", self.yaml_mgr.unclassified_pool)

    def test_generate_rule_id_slugification_and_uniqueness_across_call_sites(self):
        # Slug normalization & empty fallback
        self.assertEqual(self.yaml_mgr.generate_rule_id(""), "rule_new")
        self.assertEqual(self.yaml_mgr.generate_rule_id("!!!   ---"), "rule_new")
        self.assertEqual(self.yaml_mgr.generate_rule_id("rule_"), "rule_new")
        self.assertEqual(self.yaml_mgr.generate_rule_id("A___B  !! C"), "rule_a_b_c")
        self.assertEqual(self.yaml_mgr.generate_rule_id("rule_executive"), "rule_executive_1")

        # Deleting a rule then duplicating never reuses or collides with existing IDs
        dup1 = self.yaml_mgr.duplicate_rule("rule_executive")
        self.assertIsNotNone(dup1)
        self.yaml_mgr.remove_rule_and_repool("rule_executive")
        dup2 = self.yaml_mgr.duplicate_rule(dup1.id)
        self.assertIsNotNone(dup2)
        all_ids = [r.id for r in self.yaml_mgr.rules]
        self.assertEqual(len(all_ids), len(set(all_ids)))

        # ConflictDetector.resolve_import_to_yaml generates unique IDs on repeated imports
        detector = ConflictDetector(self.yaml_mgr, MockOutlookClient())
        conflict = RuleConflict(
            conflict_type="LEGACY_RULE",
            rule_name="Legacy Vendor",
            yaml_rule=None,
            outlook_rule_info={"name": "Legacy Vendor", "target_folder": "Archive\\Vendors", "emails": ["a@v.com"]},
        )
        self.assertTrue(detector.resolve_import_to_yaml(conflict))
        self.assertTrue(detector.resolve_import_to_yaml(conflict))
        imported_ids = [r.id for r in self.yaml_mgr.rules if r.name == "Legacy Vendor"]
        self.assertEqual(imported_ids, ["rule_legacy_vendor", "rule_legacy_vendor_1"])

    def test_delete_group_and_add_sender_fallback_behavior(self):
        # Rule referencing two groups where the first does not exist
        self.yaml_mgr.groups["secondary"] = AddressGroup(id="secondary", name="Secondary", domains=[], emails=[])
        self.yaml_mgr.rules.append(
            RuleConfig(
                id="rule_multi_grp",
                name="Multi Group",
                groups=["executive", "secondary"],
                target_folder="Test",
            )
        )

        # Delete executive WITH repool=False -> detached from rules, emails not repooled
        ok = self.yaml_mgr.delete_group("executive", repool_emails=False)
        self.assertTrue(ok)
        self.assertNotIn("executive", self.yaml_mgr.groups)
        for r in self.yaml_mgr.rules:
            self.assertNotIn("executive", r.groups)
        self.assertNotIn("ceo@company.com", self.yaml_mgr.unclassified_pool)

        # Rule formerly using 'executive' can still receive senders without KeyError
        self.yaml_mgr.add_sender_to_rule_or_group("new.exec@company.com", "rule_executive")
        exec_rule = next(r for r in self.yaml_mgr.rules if r.id == "rule_executive")
        self.assertIn("new.exec@company.com", exec_rule.emails)

        # Dangling first group skips to first valid group ('secondary')
        multi_rule = next(r for r in self.yaml_mgr.rules if r.id == "rule_multi_grp")
        multi_rule.groups = ["ghost_group", "secondary"]
        self.yaml_mgr.add_sender_to_rule_or_group("fallback@partner.com", "rule_multi_grp")
        self.assertIn("fallback@partner.com", self.yaml_mgr.groups["secondary"].emails)

        # Delete 'secondary' WITH repool_emails=True
        ok2 = self.yaml_mgr.delete_group("secondary", repool_emails=True)
        self.assertTrue(ok2)
        self.assertIn("fallback@partner.com", self.yaml_mgr.unclassified_pool)
        self.assertNotIn("secondary", multi_rule.groups)

        # When only nonexistent group remains, add_sender writes directly to rule without error
        self.yaml_mgr.add_sender_to_rule_or_group("direct@partner.com", "rule_multi_grp")
        self.assertIn("direct@partner.com", multi_rule.emails)

    def test_domain_normalization_on_load_and_add_and_dryrun_matching(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        data["groups"]["engineering"]["domains"] = ["  @TechPartner.COM  ", "sub.Vendor.org", "", "   "]
        data["rules"].append({
            "id": "rule_case_domain",
            "name": "Case Domain",
            "enabled": True,
            "groups": [],
            "emails": [],
            "domains": ["@Vendor.com", "  Supplier.IO ", ""],
            "subject_keywords": [],
            "target_store": "active_archive",
            "target_folder": "Vendors",
        })
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)

        mgr = YamlConfigManager(self.config_path)
        self.assertEqual(mgr.groups["engineering"].domains, ["@techpartner.com", "@sub.vendor.org"])
        dom_rule = next(r for r in mgr.rules if r.id == "rule_case_domain")
        self.assertEqual(dom_rule.domains, ["@vendor.com", "@supplier.io"])

        # @Vendor.com in YAML matches x@vendor.com
        engine = SyncEngine(mgr, MockOutlookClient())
        matched, _ = engine.match_message("x@vendor.com", "Hello")
        self.assertIsNotNone(matched)
        self.assertEqual(matched.id, "rule_case_domain")

        # add_sender_to_rule_or_group normalizes domains, skips empty, leaves emails unchanged
        mgr.add_sender_to_rule_or_group("  Alice@NewCorp.COM ", "rule_case_domain", as_domain=True)
        mgr.add_sender_to_rule_or_group("NoAtSign.ORG", "rule_case_domain", as_domain=True)
        mgr.add_sender_to_rule_or_group("   ", "rule_case_domain", as_domain=True)
        mgr.add_sender_to_rule_or_group("  Bob@ExactMail.COM ", "rule_case_domain", as_domain=False)
        self.assertIn("@newcorp.com", dom_rule.domains)
        self.assertIn("@noatsign.org", dom_rule.domains)
        self.assertEqual(dom_rule.emails, ["bob@exactmail.com"])


class TestPhase4GuiIntegration(unittest.TestCase):
    """Tests RuleManagerView and TriageView Phase 4 behaviors (unique IDs and askyesnocancel)."""

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

    def test_rule_manager_add_rule_uses_unique_id_and_delete_group_askyesnocancel(self):
        view = RuleManagerView(self.root, self.yaml_mgr, self.sync_engine)
        view.pack()

        # Creating a rule, deleting another, then creating again must never collide
        view.selected_folder_path = r"Management\Executive_Board\Directors"
        view._add_rule_in_selected_folder()
        self.yaml_mgr.remove_rule_and_repool("rule_executive")
        view._add_rule_in_selected_folder()
        rule_ids = [r.id for r in self.yaml_mgr.rules]
        self.assertEqual(len(rule_ids), len(set(rule_ids)))

        # Group deletion askyesnocancel: Cancel (None) keeps group
        view.selected_group = self.yaml_mgr.groups["engineering"]
        with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=None):
            view._delete_selected_group()
        self.assertIn("engineering", self.yaml_mgr.groups)

        # No (False) deletes without repooling
        view.selected_group = self.yaml_mgr.groups["engineering"]
        with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=False):
            view._delete_selected_group()
        self.assertNotIn("engineering", self.yaml_mgr.groups)
        self.assertNotIn("eng1@company.com", self.yaml_mgr.unclassified_pool)

        # Yes (True) deletes and repools emails
        view.selected_group = self.yaml_mgr.groups["suppliers"]
        with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=True):
            view._delete_selected_group()
        self.assertNotIn("suppliers", self.yaml_mgr.groups)
        self.assertIn("sales@vendor.com", self.yaml_mgr.unclassified_pool)

    def test_triage_generates_unique_ids_at_commit_time_for_duplicate_staged_names(self):
        view = TriageView(self.root, self.yaml_mgr, self.outlook, self.sync_engine)
        msg1 = EmailMessage(
            entry_id="M1",
            subject="Sub 1",
            sender_name="Alice",
            sender_email="alice@omron.com",
            received_time=datetime.now(),
        )
        msg2 = EmailMessage(
            entry_id="M2",
            subject="Sub 2",
            sender_name="Bob",
            sender_email="bob@omron.com",
            received_time=datetime.now(),
        )
        view._stage_create_new_rule(msg1)
        view._stage_create_new_rule(msg2)

        # Both actions stage with deferred ID and identical suggested rule_name ("Omron")
        self.assertEqual([a.rule_name for a in view.staged_actions], ["Omron", "Omron"])
        self.assertEqual([a.rule_id for a in view.staged_actions], ["", ""])

        with patch("gui.triage_view.messagebox.askyesno", return_value=True), \
             patch("gui.triage_view.messagebox.showinfo"):
            # Bypass conflict prompt by having no conflicts or answering No to inspector then Yes to apply
            with patch.object(view.conflict_detector, "detect_conflicts", return_value=[]):
                view._apply_all_staged()

        omron_rules = [r for r in self.yaml_mgr.rules if r.name == "Omron"]
        self.assertEqual([r.id for r in omron_rules], ["rule_omron", "rule_omron_1"])

    def test_triage_commit_35_add_to_rule_actions_creates_only_one_backup(self):
        self.yaml_mgr.settings["backup_versions"] = 30
        self.yaml_mgr.save()
        before_backups = sorted(
            glob.glob(os.path.join(self.yaml_mgr.backup_dir, "rules_*.yaml")),
            key=os.path.basename,
        )
        self.assertEqual(len(before_backups), 1)
        pre_commit_backup = before_backups[0]

        view = TriageView(self.root, self.yaml_mgr, self.outlook, self.sync_engine)
        view.staged_actions = [
            StagedAction(
                action_type="add_to_rule",
                rule_name="Executive Board",
                rule_id="rule_executive",
                target_folder=r"Management\Executive_Board\Directors",
                sender_email=f"exec{i}@company.com",
                sender_domain="@company.com",
                match_mode="email",
                message_id=f"MSG_{i}",
                subject=f"Subject {i}",
            )
            for i in range(35)
        ]

        with patch("gui.triage_view.messagebox.askyesno", return_value=True), \
             patch("gui.triage_view.messagebox.showinfo"), \
             patch.object(view.conflict_detector, "detect_conflicts", return_value=[]):
            view._apply_all_staged()

        after_backups = sorted(
            glob.glob(os.path.join(self.yaml_mgr.backup_dir, "rules_*.yaml")),
            key=os.path.basename,
        )
        self.assertEqual(len(after_backups), len(before_backups) + 1)
        self.assertTrue(os.path.exists(pre_commit_backup))

        exec_rule = next(r for r in self.yaml_mgr.rules if r.id == "rule_executive")
        all_exec_emails = self.yaml_mgr.get_all_emails_for_rule(exec_rule)
        for i in range(35):
            self.assertIn(f"exec{i}@company.com", all_exec_emails)

    def test_rule_manager_save_rule_and_group_forms_normalize_domains(self):
        view = RuleManagerView(self.root, self.yaml_mgr, self.sync_engine)
        view.pack()

        # Select rule and enter unnormalized domains in bulk mode
        view.tree.selection_set("rule_rule_executive")
        view._on_tree_select()
        view._set_condition_mode("bulk")
        view.txt_bulk_domains.delete("1.0", tk.END)
        view.txt_bulk_domains.insert(tk.END, "Vendor.com\n  @Omron.COM \n\n   \n")
        view._save_rule_changes()

        exec_rule = next(r for r in self.yaml_mgr.rules if r.id == "rule_executive")
        self.assertEqual(exec_rule.domains, ["@omron.com", "@vendor.com"])

        # Also check visual mode save path
        view.tree.selection_set("rule_rule_executive")
        view._on_tree_select()
        view._set_condition_mode("visual")
        view.lst_domains.delete(0, tk.END)
        view.lst_domains.insert(tk.END, "Partner.ORG")
        view.lst_domains.insert(tk.END, "  ")
        view._save_rule_changes()
        self.assertEqual(exec_rule.domains, ["@partner.org"])

        # Select group and enter unnormalized domains
        view.tree.selection_set("grp_suppliers")
        view._on_tree_select()
        view.txt_group_domains.delete("1.0", tk.END)
        view.txt_group_domains.insert(tk.END, "Vendor.com\n  @Omron.COM \n\n")
        view._save_group_changes()

        self.assertEqual(self.yaml_mgr.groups["suppliers"].domains, ["@omron.com", "@vendor.com"])
