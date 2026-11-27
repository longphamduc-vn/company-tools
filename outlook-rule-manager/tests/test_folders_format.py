"""Tests for the v3 'folders:' configuration format and v2 -> v3 migration."""
import copy
import os
import shutil
import tempfile
import unittest
import yaml

from core.config_format import dump_folders, dump_yaml, migrate_v2, parse_folders
from core.outlook_client import MockOutlookClient
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager


GOAL_YAML = """\
version: '3.0'
settings:
  auto_split_threshold: 40
  unclassified_folder: _Unclassified
  backup_versions: 30
stores:
  active_archive:
    name: Archive 2025
    file_path: D:\\Outlook_Data\\longp_Archive_2025.pst
folders:
  Management: []
  Engineering:
    - em@company.com
    - Pol_Process:
        - employees1@company.com
        - employees2@company.com
        - "@techpartner.com"
        - _subject: [PLC alarm, SCADA]
        - _enabled: false
unclassified:
  - former.contractor@vendor.com
legacy_rule_names:
  - Executive Board
"""


class TestFoldersFormat(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.tmpdir, ignore_errors=True))
        self.v2_fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "rules_sample_v2.yaml"
        )

    def test_goal_example_parses_correctly(self):
        data = yaml.safe_load(GOAL_YAML)
        parsed = parse_folders(data)
        self.assertEqual(parsed.warnings, [])
        self.assertEqual(
            parsed.folders,
            ["Management", "Engineering", "Engineering\\Pol_Process"],
        )
        non_unc = [r for r in parsed.rules if r.id != "rule_unclassified"]
        self.assertEqual([r.name for r in non_unc], ["Engineering", "Engineering_Pol_Process"])

        eng = non_unc[0]
        self.assertEqual(eng.emails, ["em@company.com"])
        self.assertEqual(eng.domains, [])
        self.assertTrue(eng.enabled)

        pol = non_unc[1]
        self.assertEqual(pol.emails, ["employees1@company.com", "employees2@company.com"])
        self.assertEqual(pol.domains, ["@techpartner.com"])
        self.assertEqual(pol.subject_keywords, ["PLC alarm", "SCADA"])
        self.assertFalse(pol.enabled)

        unc = [r for r in parsed.rules if r.id == "rule_unclassified"][0]
        self.assertEqual(unc.emails, ["former.contractor@vendor.com"])
        self.assertEqual(parsed.legacy_rule_names, ["Executive Board"])

    def test_round_trip_and_serialization_order(self):
        parsed1 = parse_folders(yaml.safe_load(GOAL_YAML))
        dumped = dump_folders(
            parsed1.rules,
            parsed1.folders,
            parsed1.unclassified,
            parsed1.legacy_rule_names,
            parsed1.settings,
            parsed1.stores,
        )
        yaml_text = dump_yaml(dumped)
        parsed2 = parse_folders(yaml.safe_load(yaml_text))

        self.assertEqual(parsed1.folders, parsed2.folders)
        self.assertEqual(parsed1.rules, parsed2.rules)
        self.assertEqual(parsed1.unclassified, parsed2.unclassified)
        self.assertEqual(parsed1.legacy_rule_names, parsed2.legacy_rule_names)

        # Verify item order inside Engineering: emails -> _subject -> _enabled -> subfolders
        eng_list = dumped["folders"]["Engineering"]
        self.assertEqual(eng_list[0], "em@company.com")
        self.assertIsInstance(eng_list[1], dict)
        self.assertIn("Pol_Process", eng_list[1])
        pol_list = eng_list[1]["Pol_Process"]
        self.assertEqual(
            pol_list,
            [
                "employees1@company.com",
                "employees2@company.com",
                "@techpartner.com",
                {"_subject": ["PLC alarm", "SCADA"]},
                {"_enabled": False},
            ],
        )
        self.assertEqual(dumped["folders"]["Management"], [])

    def test_empty_folder_variants_valid(self):
        raw = """\
version: '3.0'
folders:
  A: {}
  B:
  C: []
"""
        parsed = parse_folders(yaml.safe_load(raw))
        self.assertEqual(parsed.folders, ["A", "B", "C"])
        self.assertEqual([r.id for r in parsed.rules], ["rule_unclassified"])
        self.assertEqual(parsed.warnings, [])

    def test_underscore_folder_and_invalid_sender_warn_and_skip(self):
        raw = """\
version: '3.0'
folders:
  _Hidden:
    - a@b.com
  _Unclassified:
    - c@d.com
  Valid:
    - not-an-email
    - good@example.com
    - _SubHidden:
        - x@y.com
"""
        parsed = parse_folders(yaml.safe_load(raw))
        self.assertEqual(parsed.folders, ["Valid"])
        non_unc = [r for r in parsed.rules if r.id != "rule_unclassified"]
        self.assertEqual(len(non_unc), 1)
        self.assertEqual(non_unc[0].emails, ["good@example.com"])
        self.assertTrue(any("_Hidden" in w for w in parsed.warnings))
        self.assertTrue(any("_Unclassified" in w for w in parsed.warnings))
        self.assertTrue(any("not-an-email" in w for w in parsed.warnings))
        self.assertTrue(any("_SubHidden" in w for w in parsed.warnings))

    def test_duplicate_sender_kept_in_first_folder_with_warning(self):
        raw = """\
version: '3.0'
folders:
  A:
    - x@y.com
  B:
    - x@y.com
    - other@y.com
"""
        parsed = parse_folders(yaml.safe_load(raw))
        non_unc = {r.target_folder: r for r in parsed.rules if r.id != "rule_unclassified"}
        self.assertEqual(non_unc["A"].emails, ["x@y.com"])
        self.assertEqual(non_unc["B"].emails, ["other@y.com"])
        self.assertIn("x@y.com: in A and B - kept in A", parsed.warnings)

    def test_invalid_types_raise_value_error_with_path(self):
        with self.assertRaises(ValueError) as ctx1:
            parse_folders({"folders": 5})
        self.assertIn("folders", str(ctx1.exception))

        with self.assertRaises(ValueError) as ctx2:
            parse_folders({"folders": {"Team": [["nested"]]}})
        self.assertIn("Team", str(ctx2.exception))

        with self.assertRaises(ValueError) as ctx3:
            parse_folders({"folders": {"Team": [{"A": [], "B": []}]}})
        self.assertIn("Team", str(ctx3.exception))

        with self.assertRaises(ValueError) as ctx4:
            parse_folders({"folders": {"Team": 123}})
        self.assertIn("Team", str(ctx4.exception))

    def test_migrate_v2_sample_fixture(self):
        with open(self.v2_fixture, "r", encoding="utf-8") as f:
            v2_data = yaml.safe_load(f)

        # Add custom_folders and two rules in the same folder to exercise all migration rules
        v2_aug = copy.deepcopy(v2_data)
        v2_aug["settings"]["custom_folders"] = ["Empty_Folder\\Sub"]
        v2_aug["rules"].append({
            "id": "rule_exec_extra",
            "name": "Extra Exec",
            "enabled": False,
            "groups": [],
            "emails": ["board@company.com"],
            "domains": [],
            "subject_keywords": ["Board"],
            "target_store": "active_archive",
            "target_folder": "Management\\Executive_Board\\Directors",
        })

        v3 = migrate_v2(v2_aug)
        parsed = parse_folders(v3)
        self.assertIn("Empty_Folder\\Sub", parsed.folders)
        self.assertIn("Executive Board", parsed.legacy_rule_names)
        self.assertIn("Extra Exec", parsed.legacy_rule_names)

        directors = next(r for r in parsed.rules if r.target_folder == "Management\\Executive_Board\\Directors")
        self.assertTrue(directors.enabled)  # one was enabled, one disabled -> enabled
        self.assertEqual(directors.emails, ["board@company.com", "ceo@company.com", "coo@company.com"])
        self.assertEqual(directors.subject_keywords, ["Board"])

    def test_v2_file_auto_migrates_with_single_bak(self):
        cfg_path = os.path.join(self.tmpdir, "rules.yaml")
        shutil.copy2(self.v2_fixture, cfg_path)
        bak_path = f"{cfg_path}.v2.bak"

        mgr = YamlConfigManager(cfg_path)
        self.assertTrue(os.path.exists(bak_path))
        self.assertEqual(mgr.version, "3.0")
        with open(cfg_path, "r", encoding="utf-8") as f:
            saved = yaml.safe_load(f)
        self.assertIn("folders", saved)
        self.assertNotIn("rules", saved)

        # Modify bak sentinel to verify reload does not overwrite existing .v2.bak
        with open(bak_path, "a", encoding="utf-8") as f:
            f.write("\n# sentinel\n")
        mgr.load()
        with open(bak_path, "r", encoding="utf-8") as f:
            self.assertIn("# sentinel", f.read())

    def test_migration_preserves_match_message_invariant(self):
        with open(self.v2_fixture, "r", encoding="utf-8") as f:
            v2_data = yaml.safe_load(f)

        # Collect all senders in v2
        senders = []
        for g in (v2_data.get("groups") or {}).values():
            senders.extend(g.get("emails") or [])
            for d in (g.get("domains") or []):
                senders.append(f"user{d}")
        for r in (v2_data.get("rules") or []):
            senders.extend(r.get("emails") or [])
            for d in (r.get("domains") or []):
                senders.append(f"user{d}")
        senders.extend(v2_data.get("unclassified_pool") or [])

        # Expected folder from v2 (exact email -> domain -> unclassified)
        def _v2_match(sender: str) -> str:
            s = sender.lower()
            groups = v2_data.get("groups") or {}
            for r in v2_data.get("rules") or []:
                if r.get("id") == "rule_unclassified" or not r.get("enabled", True):
                    continue
                emails = list(r.get("emails") or [])
                for gid in r.get("groups") or []:
                    emails.extend(groups.get(gid, {}).get("emails") or [])
                if s in [e.lower() for e in emails]:
                    return r["target_folder"]
            for r in v2_data.get("rules") or []:
                if r.get("id") == "rule_unclassified" or not r.get("enabled", True):
                    continue
                doms = list(r.get("domains") or [])
                for gid in r.get("groups") or []:
                    doms.extend(groups.get(gid, {}).get("domains") or [])
                if any(s.endswith(d.lower()) for d in doms):
                    return r["target_folder"]
            if s in [e.lower() for e in (v2_data.get("unclassified_pool") or [])]:
                return "_Unclassified"
            return ""

        cfg_path = os.path.join(self.tmpdir, "rules.yaml")
        shutil.copy2(self.v2_fixture, cfg_path)
        mgr = YamlConfigManager(cfg_path)
        engine = SyncEngine(mgr, MockOutlookClient())

        for sender in senders:
            matched, _ = engine.match_message(sender, "Test subject")
            got_folder = matched.target_folder if matched else ""
            self.assertEqual(got_folder, _v2_match(sender), f"Mismatch for {sender}")

    def test_sync_recognizes_legacy_rule_names(self):
        cfg_path = os.path.join(self.tmpdir, "rules.yaml")
        shutil.copy2(self.v2_fixture, cfg_path)
        mgr = YamlConfigManager(cfg_path)
        outlook = MockOutlookClient()
        outlook.get_native_rules = lambda: [
            {"name": "Executive Board", "enabled": True, "emails": ["ceo@company.com"], "target_folder": "Directors"},
        ]
        engine = SyncEngine(mgr, outlook)
        self.assertIn("Executive Board", engine.find_legacy_rules())

    # --- review fixes -------------------------------------------------
    def _write(self, text):
        path = os.path.join(self.tmpdir, "rules.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_senders_without_dashes_are_warned_not_merged_into_one(self):
        y = YamlConfigManager(self._write(
            "version: '3.0'\nfolders:\n  Eng:\n    - \"a@company.com b@company.com\"\n    - c@company.com\n"
            "unclassified:\n  - \"x@y.com z@y.com\"\n"
        ))
        self.assertEqual(y.rule_for_folder("Eng").emails, ["c@company.com"])
        self.assertEqual(y.unclassified_pool, [])
        self.assertEqual(sum("one sender per line" in w for w in y.load_warnings), 2)
        # The same mistake as a whole block (no '- ' at all) is a clear error, not a silent rule
        with self.assertRaises(ValueError) as ctx:
            YamlConfigManager(self._write(
                "version: '3.0'\nfolders:\n  Eng:\n    Pol:\n      a@company.com\n      b@company.com\n"
            ))
        self.assertIn("Eng\\Pol", str(ctx.exception))
        self.assertIn("'- '", str(ctx.exception))

    def test_broken_yaml_is_a_value_error(self):
        with self.assertRaises(ValueError):
            YamlConfigManager(self._write("folders:\n  Eng: [a@b.com\n"))
        with self.assertRaises(ValueError):
            YamlConfigManager(self._write("- just\n- a list\n"))

    def test_slash_in_folder_key_is_a_nested_path(self):
        y = YamlConfigManager(self._write("version: '3.0'\nfolders:\n  Eng:\n    - Sub/Child:\n        - x@y.com\n"))
        self.assertEqual(y.rule_for_folder("Eng\\Sub\\Child").name, "Eng_Sub_Child")
        y.save()
        self.assertEqual(YamlConfigManager(y.config_path).rule_for_folder("Eng\\Sub\\Child").emails, ["x@y.com"])

    def test_new_rule_in_folder_a_moved_rule_left_gets_its_own_id(self):
        y = YamlConfigManager(self._write(GOAL_YAML))
        rule = y.rule_for_folder("Engineering")
        ok, _ = y.move_rule_to_folder(rule.id, "Moved")
        self.assertTrue(ok)
        new = y.ensure_rule_for_folder("Engineering")
        ids = [r.id for r in y.rules]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotEqual(new.id, rule.id)

    def test_import_merge_gives_unique_ids(self):
        y = YamlConfigManager(self._write(GOAL_YAML))
        rule = y.rule_for_folder("Engineering")
        y.move_rule_to_folder(rule.id, "Moved")      # keeps id rule_engineering
        shared = os.path.join(self.tmpdir, "shared.yaml")
        with open(shared, "w", encoding="utf-8") as f:
            f.write("version: '3.0'\nfolders:\n  Engineering:\n    - new@company.com\n")
        y.import_config(shared, "merge")
        ids = [r.id for r in y.rules]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(y.rule_for_folder("Engineering").emails, ["new@company.com"])

    def test_migration_warns_about_unclassified_domains(self):
        data = {"version": "2.0", "rules": [
            {"id": "rule_unclassified", "name": "[Unclassified]", "target_folder": "_Unclassified",
             "emails": ["a@x.com"], "domains": ["@spam.com"]},
        ]}
        from core.config_format import migrate_v2_with_warnings
        out, warnings = migrate_v2_with_warnings(data)
        self.assertEqual(out["unclassified"], ["a@x.com"])
        self.assertTrue(any("@spam.com" in w for w in warnings))


class TestStartupConfigError(unittest.TestCase):
    def test_main_shows_error_instead_of_crashing(self):
        from unittest.mock import patch
        import main as app_main

        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        cfg = os.path.join(tmp, "rules.yaml")
        with open(cfg, "w", encoding="utf-8") as f:
            f.write("version: '3.0'\nfolders:\n  Eng:\n    - _enabled: 'no'\n")
        with patch("sys.argv", ["main.py", "--config", cfg]), \
                patch.object(app_main, "show_config_error") as shown, \
                patch.object(app_main, "MainWindow") as window:
            with self.assertRaises(SystemExit):
                app_main.main()
        shown.assert_called_once()
        self.assertIn("_enabled", str(shown.call_args.args[1]))
        window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
