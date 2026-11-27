"""Unit tests for Rule Manager, Folder Hierarchy, and Drag-and-Drop operations."""
import unittest
import os
import shutil
import tempfile
import tkinter as tk

from core.yaml_manager import YamlConfigManager
from core.outlook_client import MockOutlookClient
from core.sync_engine import SyncEngine
from gui.rule_manager_view import RuleManagerView


class TestRuleManagerAndFolderOperations(unittest.TestCase):
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

    def test_move_rule_to_folder(self):
        rule_id = r"rule_purchasing_team\vendor_part\omron_unit"
        # Moving to an occupied folder is refused
        ok_dup, msg_dup = self.yaml_mgr.move_rule_to_folder(rule_id, r"Engineering_Team\SCADA_Part\PLC_Unit")
        self.assertFalse(ok_dup)
        self.assertIn("already has a rule", msg_dup)

        # Moving to an empty folder succeeds and renames the rule
        target_folder = r"Engineering_Team\SCADA_Part"
        ok, _ = self.yaml_mgr.move_rule_to_folder(rule_id, target_folder)
        self.assertTrue(ok)

        rule = next(r for r in self.yaml_mgr.rules if r.id == rule_id)
        self.assertEqual(rule.target_folder, target_folder)
        self.assertEqual(rule.name, "Engineering_Team_SCADA_Part")

    def test_move_folder_hierarchy(self):
        # Move SCADA_Part from Engineering_Team to Purchasing_Team
        source = r"Engineering_Team\SCADA_Part"
        dest_parent = "Purchasing_Team"
        ok, new_path = self.yaml_mgr.move_folder_hierarchy(source, dest_parent)
        self.assertTrue(ok)
        self.assertEqual(new_path, r"Purchasing_Team\SCADA_Part")

        # Verify child rule path was updated
        eng_rule = next(r for r in self.yaml_mgr.rules if r.id == r"rule_engineering_team\scada_part\plc_unit")
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

        eng_rule = next(r for r in self.yaml_mgr.rules if r.id == r"rule_engineering_team\scada_part\plc_unit")
        self.assertEqual(eng_rule.target_folder, r"Engineering_Team\Robotics_Part\PLC_Unit")

    def test_delete_folder_hierarchy_and_repool(self):
        target_fld = r"Management\Executive_Board\Directors"
        affected = self.yaml_mgr.delete_folder_hierarchy(target_fld, repool_addresses=True)
        self.assertGreaterEqual(affected, 1)

        # Verify executive rule addresses were repooled
        self.assertIn("ceo@company.com", self.yaml_mgr.unclassified_pool)
        self.assertIn("coo@company.com", self.yaml_mgr.unclassified_pool)

    def test_gui_drag_and_drop_flow(self):
        view = RuleManagerView(self.root, self.yaml_mgr, self.sync_engine)
        view.pack()

        # Check hierarchy tree populated (no __GROUPS__)
        children = view.tree.get_children()
        self.assertIn("__HIERARCHY__", children)
        self.assertNotIn("__GROUPS__", children)
        self.assertIn("__POOL__", children)

        sup_iid = r"rule_rule_purchasing_team\vendor_part\omron_unit"
        eng_iid = r"rule_rule_engineering_team\scada_part\plc_unit"
        exec_iid = r"rule_rule_management\executive_board\directors"

        # Folders with a rule are one merged node: "📁 Omron_Unit  (rule: Purchasing_Team_Vendor_Part_Omron_Unit)"
        self.assertEqual(view.folder_nodes_map[sup_iid], r"Purchasing_Team\Vendor_Part\Omron_Unit")
        self.assertIn("(rule: Purchasing_Team_Vendor_Part_Omron_Unit)", view.tree.item(sup_iid, "text"))
        self.assertFalse(view.tree.exists(r"fld_purchasing_team\vendor_part\omron_unit"))

        # Dragging it onto the PLC_Unit node moves the folder (with its rule) below PLC_Unit
        view._execute_drop(sup_iid, eng_iid)
        sup_rule = next(r for r in self.yaml_mgr.rules if r.id == r"rule_purchasing_team\vendor_part\omron_unit")
        self.assertEqual(sup_rule.target_folder, r"Engineering_Team\SCADA_Part\PLC_Unit\Omron_Unit")
        # PLC_Unit still stays a merged node, with Omron_Unit as its child
        self.assertTrue(view.tree.exists(eng_iid))
        self.assertEqual(view.tree.parent(sup_iid), eng_iid)

        # Drag pool address onto executive rule
        pool_iid = "pool_former.contractor@vendor.com"
        view._execute_drop(pool_iid, exec_iid)
        exec_rule = next(r for r in self.yaml_mgr.rules if r.id == r"rule_management\executive_board\directors")
        self.assertIn("former.contractor@vendor.com", self.yaml_mgr.get_all_emails_for_rule(exec_rule))
        self.assertNotIn("former.contractor@vendor.com", self.yaml_mgr.unclassified_pool)

    def test_gui_single_mode_inspector_widgets(self):
        view = RuleManagerView(self.root, self.yaml_mgr, self.sync_engine)
        view.pack()

        # Select a rule and verify single-mode condition text widgets are active
        view.tree.selection_set(r"rule_rule_management\executive_board\directors")
        view._on_tree_select()

        self.assertFalse(hasattr(view, "_set_condition_mode"))
        self.assertFalse(hasattr(view, "condition_mode"))
        self.assertEqual(view.lbl_rule_name.cget("text"), "[Companion] Management_Executive_Board_Directors")
        self.assertEqual(view.lbl_rule_emails_hdr.cget("text"), "Emails (2)")
        self.assertEqual(view.lbl_rule_domains_hdr.cget("text"), "Domains (0)")
        self.assertEqual(view.lbl_rule_keywords_hdr.cget("text"), "Subject Keywords (0)")

        view.txt_emails.insert(tk.END, "\ndirect@company.com\n")
        view._on_rule_text_changed()
        self.assertEqual(view.lbl_rule_emails_hdr.cget("text"), "Emails (3)")

    def test_dynamic_arbitrary_level_shifts(self):
        exec_id = r"rule_management\executive_board\directors"
        # 1. Level 3 to Level 1 (Promote to Root)
        ok, res = self.yaml_mgr.promote_folder_to_root(r"Management\Executive_Board\Directors")
        self.assertTrue(ok)
        self.assertEqual(res, "Directors")
        exec_rule = next(r for r in self.yaml_mgr.rules if r.id == exec_id)
        self.assertEqual(exec_rule.target_folder, "Directors")  # Now at Level 1!

        # 2. Level 1 to Level 4 (Move into Level 3)
        ok, res = self.yaml_mgr.move_folder_hierarchy("Directors", r"Engineering_Team\SCADA_Part\PLC_Unit")
        self.assertTrue(ok)
        self.assertEqual(res, r"Engineering_Team\SCADA_Part\PLC_Unit\Directors")
        self.assertEqual(len(res.split("\\")), 4)  # Level 4!
        exec_rule = next(r for r in self.yaml_mgr.rules if r.id == exec_id)
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

        sup_id = r"rule_purchasing_team\vendor_part\omron_unit"
        sup_iid = f"rule_{sup_id}"
        eng_iid = r"rule_rule_engineering_team\scada_part\plc_unit"

        # Drag Omron_Unit (Level 3, shown merged with its rule) onto __HIERARCHY__ (Root)
        view._execute_drop(sup_iid, "__HIERARCHY__")

        sup_rule = next(r for r in self.yaml_mgr.rules if r.id == sup_id)
        self.assertEqual(sup_rule.target_folder, "Omron_Unit")  # Now at Level 1!

        # Now drag Omron_Unit (Level 1) onto Engineering_Team\SCADA_Part\PLC_Unit (Level 3) -> Becomes Level 4!
        view._execute_drop(sup_iid, eng_iid)
        sup_rule = next(r for r in self.yaml_mgr.rules if r.id == sup_id)
        self.assertEqual(sup_rule.target_folder, r"Engineering_Team\SCADA_Part\PLC_Unit\Omron_Unit")
        self.assertEqual(len(sup_rule.target_folder.split("\\")), 4)  # Level 4!

    def test_drag_rule_into_occupied_folder_is_refused_and_yaml_unchanged(self):
        view = RuleManagerView(self.root, self.yaml_mgr, self.sync_engine)
        view.pack()

        before_yaml = open(self.config_path, "r", encoding="utf-8").read()
        # Dragging rule_unclassified onto an occupied folder (e.g. PLC_Unit) is refused
        view._execute_drop("rule_rule_unclassified", r"rule_rule_engineering_team\scada_part\plc_unit")
        self.assertIn("already has a rule", view.lbl_toast.cget("text"))
        after_yaml = open(self.config_path, "r", encoding="utf-8").read()
        self.assertEqual(before_yaml, after_yaml)

    def test_f2_on_rule_node_renames_folder_and_rule_name(self):
        from unittest.mock import patch

        view = RuleManagerView(self.root, self.yaml_mgr, self.sync_engine)
        view.pack()
        sup_id = r"rule_purchasing_team\vendor_part\omron_unit"
        view.tree.selection_set(f"rule_{sup_id}")
        view._on_tree_select()

        with patch("gui.rule_manager_view.simpledialog.askstring", return_value="Yaskawa_Unit"):
            view._on_rename_key()

        rule = next(r for r in self.yaml_mgr.rules if r.id == sup_id)
        self.assertEqual(rule.target_folder, r"Purchasing_Team\Vendor_Part\Yaskawa_Unit")
        self.assertEqual(rule.name, "Purchasing_Team_Vendor_Part_Yaskawa_Unit")



if __name__ == "__main__":
    unittest.main()
