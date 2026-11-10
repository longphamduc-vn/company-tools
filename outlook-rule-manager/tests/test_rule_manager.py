"""Unit tests for Rule Manager, Folder Hierarchy, and Drag-and-Drop operations."""
import unittest
import os
import shutil
import tempfile
import tkinter as tk

from core.yaml_manager import YamlConfigManager
from core.outlook_client import get_outlook_client
from core.sync_engine import SyncEngine
from gui.rule_manager_view import RuleManagerView


class TestRuleManagerAndFolderOperations(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        sample_config = os.path.join(os.path.dirname(__file__), "..", "config", "rules.yaml")
        shutil.copy2(sample_config, self.config_path)

        self.yaml_mgr = YamlConfigManager(self.config_path)
        self.outlook = get_outlook_client()
        self.sync_engine = SyncEngine(self.yaml_mgr, self.outlook)

        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_move_rule_to_folder(self):
        rule_id = "rule_suppliers"
        target_folder = r"Engineering_Team\SCADA_Part\PLC_Unit"
        ok = self.yaml_mgr.move_rule_to_folder(rule_id, target_folder)
        self.assertTrue(ok)

        rule = next(r for r in self.yaml_mgr.rules if r.id == rule_id)
        self.assertEqual(rule.target_folder, target_folder)

    def test_move_folder_hierarchy(self):
        # Move SCADA_Part from Engineering_Team to Purchasing_Team
        source = r"Engineering_Team\SCADA_Part"
        dest_parent = "Purchasing_Team"
        ok, new_path = self.yaml_mgr.move_folder_hierarchy(source, dest_parent)
        self.assertTrue(ok)
        self.assertEqual(new_path, r"Purchasing_Team\SCADA_Part")

        # Verify child rule path was updated
        eng_rule = next(r for r in self.yaml_mgr.rules if r.id == "rule_engineering")
        self.assertEqual(eng_rule.target_folder, r"Purchasing_Team\SCADA_Part\PLC_Unit")

    def test_prevent_circular_nesting(self):
        source = "Engineering_Team"
        dest_parent = r"Engineering_Team\SCADA_Part"
        ok, msg = self.yaml_mgr.move_folder_hierarchy(source, dest_parent)
        self.assertFalse(ok)
        self.assertIn("Cannot move a folder into itself", msg)

    def test_rename_folder_hierarchy(self):
        old_path = r"Engineering_Team\SCADA_Part"
        ok, new_path = self.yaml_mgr.rename_folder_hierarchy(old_path, "Robotics_Part")
        self.assertTrue(ok)
        self.assertEqual(new_path, r"Engineering_Team\Robotics_Part")

        eng_rule = next(r for r in self.yaml_mgr.rules if r.id == "rule_engineering")
        self.assertEqual(eng_rule.target_folder, r"Engineering_Team\Robotics_Part\PLC_Unit")

    def test_delete_folder_hierarchy_and_repool(self):
        target_fld = r"Management\Executive_Board\Directors"
        affected = self.yaml_mgr.delete_folder_hierarchy(target_fld, repool_addresses=True)
        self.assertGreaterEqual(affected, 1)

        # Verify executive rule addresses were repooled
        self.assertIn("ceo@company.com", self.yaml_mgr.unclassified_pool)
        self.assertIn("coo@company.com", self.yaml_mgr.unclassified_pool)

    def test_duplicate_rule(self):
        dup = self.yaml_mgr.duplicate_rule("rule_executive")
        self.assertIsNotNone(dup)
        self.assertTrue(dup.name.startswith("Copy of"))
        self.assertEqual(dup.target_folder, r"Management\Executive_Board\Directors")

    def test_gui_drag_and_drop_flow(self):
        view = RuleManagerView(self.root, self.yaml_mgr, self.sync_engine)
        view.pack()

        # Check hierarchy tree populated
        children = view.tree.get_children()
        self.assertIn("__HIERARCHY__", children)
        self.assertIn("__GROUPS__", children)
        self.assertIn("__POOL__", children)

        # Drag rule_suppliers onto Engineering_Team\SCADA_Part\PLC_Unit folder node
        dest_iid = r"fld_engineering_team\scada_part\plc_unit"
        view._execute_drop("rule_rule_suppliers", dest_iid)

        sup_rule = next(r for r in self.yaml_mgr.rules if r.id == "rule_suppliers")
        self.assertEqual(sup_rule.target_folder, r"Engineering_Team\SCADA_Part\PLC_Unit")

        # Drag pool address onto rule_executive
        pool_iid = "pool_former.contractor@vendor.com"
        view._execute_drop(pool_iid, "rule_rule_executive")
        exec_rule = next(r for r in self.yaml_mgr.rules if r.id == "rule_executive")
        self.assertIn("former.contractor@vendor.com", self.yaml_mgr.get_all_emails_for_rule(exec_rule))
        self.assertNotIn("former.contractor@vendor.com", self.yaml_mgr.unclassified_pool)

    def test_gui_condition_mode_switching(self):
        view = RuleManagerView(self.root, self.yaml_mgr, self.sync_engine)
        view.pack()

        # Select a rule
        view.tree.selection_set("rule_rule_executive")
        view._on_tree_select()

        # Switch to bulk mode
        view._set_condition_mode("bulk")
        self.assertEqual(view.condition_mode, "bulk")

        # Switch to visual mode
        view._set_condition_mode("visual")
        self.assertEqual(view.condition_mode, "visual")

    def test_dynamic_arbitrary_level_shifts(self):
        # 1. Level 3 to Level 1 (Promote to Root)
        # Directors is initially at Management\Executive_Board\Directors (Level 3)
        ok, res = self.yaml_mgr.promote_folder_to_root(r"Management\Executive_Board\Directors")
        self.assertTrue(ok)
        self.assertEqual(res, "Directors")
        exec_rule = next(r for r in self.yaml_mgr.rules if r.id == "rule_executive")
        self.assertEqual(exec_rule.target_folder, "Directors")  # Now at Level 1!

        # 2. Level 1 to Level 4 (Move into Level 3)
        # Move Directors (Level 1) into Engineering_Team\SCADA_Part\PLC_Unit (Level 3) -> Becomes Level 4!
        ok, res = self.yaml_mgr.move_folder_hierarchy("Directors", r"Engineering_Team\SCADA_Part\PLC_Unit")
        self.assertTrue(ok)
        self.assertEqual(res, r"Engineering_Team\SCADA_Part\PLC_Unit\Directors")
        self.assertEqual(len(res.split("\\")), 4)  # Level 4!
        exec_rule = next(r for r in self.yaml_mgr.rules if r.id == "rule_executive")
        self.assertEqual(exec_rule.target_folder, r"Engineering_Team\SCADA_Part\PLC_Unit\Directors")

        # 3. Level 4 to Level 3 (Move Up 1 Level)
        ok, res = self.yaml_mgr.move_folder_up_one_level(r"Engineering_Team\SCADA_Part\PLC_Unit\Directors")
        self.assertTrue(ok)
        self.assertEqual(res, r"Engineering_Team\SCADA_Part\Directors")
        self.assertEqual(len(res.split("\\")), 3)  # Level 3!

        # 4. Level 3 to Level 2 (Move Up 1 Level again)
        ok, res = self.yaml_mgr.move_folder_up_one_level(r"Engineering_Team\SCADA_Part\Directors")
        self.assertTrue(ok)
        self.assertEqual(res, r"Engineering_Team\Directors")
        self.assertEqual(len(res.split("\\")), 2)  # Level 2!

        # 5. Level 2 to Level 1 (Move Up 1 Level again)
        ok, res = self.yaml_mgr.move_folder_up_one_level(r"Engineering_Team\Directors")
        self.assertTrue(ok)
        self.assertEqual(res, "Directors")
        self.assertEqual(len(res.split("\\")), 1)  # Level 1!

    def test_gui_drag_folder_to_root_and_arbitrary_depth(self):
        view = RuleManagerView(self.root, self.yaml_mgr, self.sync_engine)
        view.pack()

        # Drag Omron_Unit (Level 3: Purchasing_Team\Vendor_Part\Omron_Unit) onto __HIERARCHY__ (Root)
        source_iid = r"fld_purchasing_team\vendor_part\omron_unit"
        view._execute_drop(source_iid, "__HIERARCHY__")

        sup_rule = next(r for r in self.yaml_mgr.rules if r.id == "rule_suppliers")
        self.assertEqual(sup_rule.target_folder, "Omron_Unit")  # Now at Level 1!

        # Now drag Omron_Unit (Level 1) onto Engineering_Team\SCADA_Part\PLC_Unit (Level 3) -> Becomes Level 4!
        view._execute_drop("fld_omron_unit", r"fld_engineering_team\scada_part\plc_unit")
        sup_rule = next(r for r in self.yaml_mgr.rules if r.id == "rule_suppliers")
        self.assertEqual(sup_rule.target_folder, r"Engineering_Team\SCADA_Part\PLC_Unit\Omron_Unit")
        self.assertEqual(len(sup_rule.target_folder.split("\\")), 4)  # Level 4!



if __name__ == "__main__":
    unittest.main()
