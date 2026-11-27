"""Rule names follow the folder (A\\B\\C -> A_B_C); in Outlook they carry the [Companion] prefix."""
import os
import shutil
import tempfile
import unittest

from core.models import MANAGED_PREFIX, outlook_rule_name, rule_name_from_folder
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

    def _rule_for(self, folder):
        return self.y.rule_for_folder(folder)

    def test_helpers(self):
        self.assertEqual(rule_name_from_folder("Team\\Part/Unit"), "Team_Part_Unit")
        self.assertEqual(outlook_rule_name("Team_Part"), f"{MANAGED_PREFIX}Team_Part")

    def test_names_follow_folders_on_load_and_old_names_are_remembered(self):
        exec_rule = self._rule_for("Management\\Executive_Board\\Directors")
        self.assertEqual(exec_rule.name, "Management_Executive_Board_Directors")
        self.assertIn("Executive Board", self.y.legacy_rule_names)
        # The Unclassified fallback keeps its own name
        unc = next(r for r in self.y.rules if r.id == "rule_unclassified")
        self.assertEqual(unc.name, "[Unclassified]")
        # legacy_rule_names survive a save + reload
        self.y.save()
        reloaded = YamlConfigManager(self.config_path)
        self.assertIn("Executive Board", reloaded.legacy_rule_names)

    def test_moving_or_renaming_folder_renames_rule(self):
        suppliers = self._rule_for("Purchasing_Team\\Vendor_Part\\Omron_Unit")
        ok, _ = self.y.move_rule_to_folder(suppliers.id, "Vendors\\Omron")
        self.assertTrue(ok)
        self.assertEqual(self._rule_for("Vendors\\Omron").name, "Vendors_Omron")
        ok, _ = self.y.rename_folder_hierarchy("Vendors", "Suppliers")
        self.assertTrue(ok)
        rule = self._rule_for("Suppliers\\Omron")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.name, "Suppliers_Omron")

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
