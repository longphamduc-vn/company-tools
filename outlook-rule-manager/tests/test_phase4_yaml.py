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

from core.config_format import parse_folders
from core.models import EmailMessage, RuleConfig
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
        self.assertEqual([r.id for r in parse_folders(first_backup_data).rules], initial_rule_ids)

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
            r = self.yaml_mgr.ensure_rule_for_folder(rf"BulkTeam\SubPart\F{i}")
            r.emails = [f"batch{i}@vendor.com"]
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

    def test_domain_normalization_on_load_and_add_and_dryrun_matching(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        data["folders"]["Vendors"] = ["@Vendor.com", "  @Supplier.IO "]
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)

        mgr = YamlConfigManager(self.config_path)
        dom_rule = mgr.rule_for_folder("Vendors")
        self.assertIsNotNone(dom_rule)
        self.assertEqual(dom_rule.domains, ["@supplier.io", "@vendor.com"])

        # @Vendor.com in YAML matches x@vendor.com
        engine = SyncEngine(mgr, MockOutlookClient())
        matched, _ = engine.match_message("x@vendor.com", "Hello")
        self.assertIsNotNone(matched)
        self.assertEqual(matched.id, dom_rule.id)

        # add_sender_to_rule_or_group normalizes domains, skips empty, leaves emails unchanged
        mgr.add_sender_to_rule_or_group("  Alice@NewCorp.COM ", dom_rule.id, as_domain=True)
        mgr.add_sender_to_rule_or_group("NoAtSign.ORG", dom_rule.id, as_domain=True)
        mgr.add_sender_to_rule_or_group("   ", dom_rule.id, as_domain=True)
        mgr.add_sender_to_rule_or_group("  Bob@ExactMail.COM ", dom_rule.id, as_domain=False)
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

    def test_triage_commit_35_add_to_rule_actions_creates_only_one_backup(self):
        self.yaml_mgr.settings["backup_versions"] = 30
        self.yaml_mgr.save()
        before_backups = sorted(
            glob.glob(os.path.join(self.yaml_mgr.backup_dir, "rules_*.yaml")),
            key=os.path.basename,
        )
        self.assertEqual(len(before_backups), 1)
        pre_commit_backup = before_backups[0]

        exec_id = r"rule_management\executive_board\directors"
        view = TriageView(self.root, self.yaml_mgr, self.outlook, self.sync_engine)
        view.staged_actions = [
            StagedAction(
                action_type="add_to_rule",
                rule_name="Management_Executive_Board_Directors",
                rule_id=exec_id,
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

        exec_rule = next(r for r in self.yaml_mgr.rules if r.id == exec_id)
        all_exec_emails = self.yaml_mgr.get_all_emails_for_rule(exec_rule)
        for i in range(35):
            self.assertIn(f"exec{i}@company.com", all_exec_emails)

    def test_rule_manager_save_rule_form_normalizes_domains(self):
        view = RuleManagerView(self.root, self.yaml_mgr, self.sync_engine)
        view.pack()

        exec_id = r"rule_management\executive_board\directors"
        # Select rule and enter unnormalized domains in single-mode inspector
        view.tree.selection_set(f"rule_{exec_id}")
        view._on_tree_select()
        view.txt_domains.delete("1.0", tk.END)
        view.txt_domains.insert(tk.END, "Vendor.com\n  @Omron.COM \n\n   \n")
        view._save_rule_changes()

        exec_rule = next(r for r in self.yaml_mgr.rules if r.id == exec_id)
        self.assertEqual(exec_rule.domains, ["@omron.com", "@vendor.com"])

        # Save a second set of unnormalized domains via the same single-mode box
        view.tree.selection_set(f"rule_{exec_id}")
        view._on_tree_select()
        view.txt_domains.delete("1.0", tk.END)
        view.txt_domains.insert(tk.END, "Partner.ORG\n  \n")
        view._save_rule_changes()
        self.assertEqual(exec_rule.domains, ["@partner.org"])
