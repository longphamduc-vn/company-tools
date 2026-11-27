"""Rule names follow the folder (A\\B\\C -> A_B_C); in Outlook they carry the [Companion] prefix."""
import os
import shutil
import tempfile
import unittest

from core.models import MANAGED_PREFIX, RuleConfig, outlook_rule_name, rule_name_from_folder
from core.outlook_client import WindowsOutlookClient
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager
from tests.fakes import FakeFolder, FakeNamespace, FakeRule, FakeStore

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")


class TestAutoRuleNames(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        shutil.copy2(FIXTURE, self.config_path)
        self.y = YamlConfigManager(self.config_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _rule(self, rule_id):
        return next(r for r in self.y.rules if r.id == rule_id)

    def test_helpers(self):
        self.assertEqual(rule_name_from_folder("Team\\Part/Unit"), "Team_Part_Unit")
        self.assertEqual(outlook_rule_name("Team_Part"), f"{MANAGED_PREFIX}Team_Part")

    def test_names_follow_folders_on_load_and_old_names_are_remembered(self):
        exec_rule = self._rule("rule_executive")
        self.assertEqual(exec_rule.name, "Management_Executive_Board_Directors")
        self.assertEqual(exec_rule.former_names, ["Executive Board"])
        # The Unclassified fallback keeps its own name
        self.assertEqual(self._rule("rule_unclassified").name, "[Unclassified]")
        # former_names survive a save + reload
        self.y.save()
        reloaded = YamlConfigManager(self.config_path)
        self.assertEqual(next(r for r in reloaded.rules if r.id == "rule_executive").former_names,
                         ["Executive Board"])

    def test_second_rule_in_folder_gets_suffix(self):
        folder = self._rule("rule_executive").target_folder
        self.assertEqual(self.y.auto_rule_name(folder), "Management_Executive_Board_Directors_2")
        self.y.rules.append(RuleConfig(id="rule_b", name="anything", target_folder=folder))
        self.y.save()
        self.assertEqual(self._rule("rule_b").name, "Management_Executive_Board_Directors_2")

    def test_moving_or_renaming_folder_renames_rule(self):
        self.y.move_rule_to_folder("rule_suppliers", "Vendors\\Omron")
        self.assertEqual(self._rule("rule_suppliers").name, "Vendors_Omron")
        ok, _ = self.y.rename_folder_hierarchy("Vendors", "Suppliers")
        self.assertTrue(ok)
        rule = self._rule("rule_suppliers")
        self.assertEqual(rule.name, "Suppliers_Omron")
        self.assertIn("Omron Equipment", rule.former_names)
        self.assertIn("Vendors_Omron", rule.former_names)

    def test_auto_naming_can_be_switched_off(self):
        self.y.settings["auto_rule_names"] = False
        rule = self._rule("rule_executive")
        rule.name = "Board"
        self.y.save()
        self.assertEqual(self._rule("rule_executive").name, "Board")

    def test_sync_renames_outlook_rule_and_still_finds_old_hand_made_rule(self):
        store_path = self.y.stores["active_archive"].file_path
        default_store = FakeStore("Primary Mailbox", "", is_data_file=False)
        ns = FakeNamespace(stores=[default_store, FakeStore("Archive 2025", store_path)], default_store=default_store)
        outlook = WindowsOutlookClient(namespace=ns)
        # Outlook still has the old managed rule and a hand-made rule with the old name
        old_managed = FakeRule(f"{MANAGED_PREFIX}Executive Board")
        hand_made = FakeRule("Executive Board")
        hand_made.Conditions.From.Enabled = True
        hand_made.Conditions.From.Recipients.Add("ceo@company.com")
        hand_made.Actions.MoveToFolder.Enabled = True
        hand_made.Actions.MoveToFolder.Folder = FakeFolder("Directors")
        user_rule = FakeRule("My own newsletter rule")
        default_store.GetRules()._rules.extend([old_managed, hand_made, user_rule])

        engine = SyncEngine(self.y, outlook)
        self.assertIn("Executive Board", engine.find_legacy_rules())
        ok, msg = engine.push_to_outlook(remove_legacy=True)
        self.assertTrue(ok, msg)
        names = {r.Name for r in default_store.GetRules()}
        self.assertIn(f"{MANAGED_PREFIX}Management_Executive_Board_Directors", names)
        self.assertNotIn(f"{MANAGED_PREFIX}Executive Board", names)   # old managed copy removed
        self.assertNotIn("Executive Board", names)                    # old hand-made copy cleaned
        self.assertIn("My own newsletter rule", names)                # user's own rules untouched


if __name__ == "__main__":
    unittest.main()
