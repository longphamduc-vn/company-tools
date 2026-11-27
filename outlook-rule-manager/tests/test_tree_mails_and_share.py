"""Tree layout 'folder > subfolder (rule) > mail' and export / import of rules for sharing."""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import yaml

from core.outlook_client import MockOutlookClient
from core.yaml_manager import YamlConfigManager
from gui.main_window import MainWindow

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")


class TestTreeWithMails(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        shutil.copy2(FIXTURE, self.config_path)
        self.win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        self.win.update()
        self.tv = self.win.tab_triage
        self.rv = self.win.tab_rules
        self.tree = self.rv.tree

    def tearDown(self):
        try:
            self.win.destroy()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_leaf_folder_with_one_rule_is_one_node_with_its_mails(self):
        self.assertEqual(self.tree.parent("rule_rule_engineering"), "fld_engineering_team\\scada_part")
        self.assertEqual(self.tree.item("rule_rule_engineering", "text"),
                         "📁 PLC_Unit  (rule: Engineering_Team_SCADA_Part_PLC_Unit)")
        self.assertEqual(self.tree.parent("mail::MSG_001"), "rule_rule_engineering")
        self.assertEqual(self.tree.parent("mail::MSG_002"), "rule_rule_suppliers")
        # The unclassified folder is never merged
        self.assertTrue(self.tree.exists("fld__unclassified"))
        self.assertEqual(self.tree.parent("rule_rule_unclassified"), "fld__unclassified")

    def test_group_senders_are_shown_read_only_in_the_rule_inspector(self):
        self.tree.selection_set("rule_rule_suppliers")
        self.tree.focus("rule_rule_suppliers")
        self.rv._on_tree_select(None)
        self.win.update()
        # Tree: emails and domains are counted separately, like the inspector
        self.assertEqual(self.tree.set("rule_rule_suppliers", "Details"), "1 sender, 2 domains")
        # Own boxes stay empty; the group's senders are listed under them, not inside them
        self.assertEqual(self.rv.txt_emails.get("1.0", "end").strip(), "")
        self.assertEqual(self.rv.lbl_rule_emails_hdr.cget("text"), "Emails (0 + 1 from groups)")
        self.assertEqual(self.rv.lbl_rule_domains_hdr.cget("text"), "Domains (0 + 2 from groups)")
        self.assertIn("sales@vendor.com", self.rv.lbl_group_emails.cget("text"))
        self.assertIn("Equipment Suppliers", self.rv.lbl_group_domains.cget("text"))
        self.assertIn("@omron.com", self.rv.lbl_group_domains.cget("text"))
        self.assertEqual(self.rv.lbl_group_emails.winfo_manager(), "pack")
        self.assertFalse(self.rv.is_rule_dirty())
        # Unlinking the group (before saving) removes the read-only list right away
        self.rv.lst_rule_groups.selection_set(0)
        self.rv._unlink_group_from_rule()
        self.win.update()
        self.assertEqual(self.rv.lbl_rule_emails_hdr.cget("text"), "Emails (0)")
        self.assertEqual(self.rv.lbl_group_emails.winfo_manager(), "")

    def test_folder_with_two_rules_is_not_merged(self):
        y = self.win.yaml_mgr
        y.rules.append(type(y.rules[0])(id="rule_second", name="Second", target_folder="Purchasing_Team\\Vendor_Part\\Omron_Unit"))
        y.save()
        self.rv.refresh_all()
        fld = "fld_purchasing_team\\vendor_part\\omron_unit"
        self.assertTrue(self.tree.exists(fld))
        self.assertEqual(self.tree.parent("rule_rule_suppliers"), fld)
        self.assertEqual(self.tree.parent("rule_rule_second"), fld)
        self.assertNotIn("rule_rule_suppliers", self.rv.merged_nodes)

    def test_staged_mail_moves_under_its_new_rule(self):
        msg = next(m for m in self.tv.messages if m.entry_id == "MSG_004")
        self.tv.drop_messages_on_target("rule_rule_suppliers", [msg])
        self.assertEqual(self.tree.parent("mail::MSG_004"), "rule_rule_suppliers")
        self.assertTrue(self.tree.item("mail::MSG_004", "text").startswith("* "))
        self.assertIn("mail_staged", self.tree.item("mail::MSG_004", "tags"))

    def test_click_mail_in_tree_shows_it_in_reader(self):
        self.win.show_rule_details()
        self.tree.selection_set("mail::MSG_003")
        self.rv._on_tree_select()
        self.win.update()
        self.assertEqual(self.win.details_mode, "mail")
        self.assertEqual(self.tv.selected_message.entry_id, "MSG_003")
        self.assertEqual(self.tv.tree_inbox.selection(), ("MSG_003",))

    def test_drag_mail_inside_tree_onto_other_rule_restages_it(self):
        self.rv._drop_ctrl = False
        self.rv._execute_drop("mail::MSG_003", "rule_rule_suppliers")
        action = next(a for a in self.tv.staged_actions if a.message_id == "MSG_003")
        self.assertEqual((action.action_type, action.rule_id), ("add_to_rule", "rule_suppliers"))
        self.assertEqual(self.tree.parent("mail::MSG_003"), "rule_rule_suppliers")
        # Dropping on a mail means its rule
        self.rv._execute_drop("mail::MSG_003", "mail::MSG_001")
        action = next(a for a in self.tv.staged_actions if a.message_id == "MSG_003")
        self.assertEqual(action.rule_id, "rule_engineering")
        self.assertEqual(self.rv.resolve_drop_iid("mail::MSG_001"), ("rule", "rule_engineering"))

    def test_mail_dragged_to_parent_folder_shows_under_pending_new_rule(self):
        vendor_part = "fld_purchasing_team\\vendor_part"
        self.rv._drop_ctrl = False
        self.rv._execute_drop("mail::MSG_002", vendor_part)
        pending = "pending::purchasing_team\\vendor_part"
        self.assertTrue(self.tree.exists(pending))
        self.assertEqual(self.tree.parent(pending), vendor_part)
        self.assertIn("Purchasing_Team_Vendor_Part", self.tree.item(pending, "text"))
        self.assertEqual(self.tree.parent("mail::MSG_002"), pending)   # the mail stays visible
        # A second mail dropped on the pending rule joins it
        self.rv._execute_drop("mail::MSG_003", pending)
        self.assertEqual(self.tree.parent("mail::MSG_003"), pending)
        self.assertEqual({a.target_folder for a in self.tv.staged_actions}, {"Purchasing_Team\\Vendor_Part"})
        # Clearing the queue removes the pending node and puts the mails back under their rules
        self.tv.staged_actions.clear()
        self.tv._populate_inbox_table()
        self.assertFalse(self.tree.exists(pending))
        self.assertEqual(self.tree.parent("mail::MSG_002"), "rule_rule_suppliers")

    def test_drop_where_item_already_is_changes_nothing(self):
        self.rv._drop_ctrl = False
        # Folder / merged folder+rule onto its own parent, top-level folder onto root
        self.rv._execute_drop("rule_rule_suppliers", "fld_purchasing_team\\vendor_part")
        self.assertIn("already in", self.rv.lbl_toast.cget("text"))
        self.rv._execute_drop("fld_engineering_team\\scada_part", "fld_engineering_team")
        self.assertIn("already in", self.rv.lbl_toast.cget("text"))
        self.rv._execute_drop("fld_engineering_team", "__HIERARCHY__")
        self.assertIn("already a top-level folder", self.rv.lbl_toast.cget("text"))
        # Mail onto the rule it already goes to
        self.rv._execute_drop("mail::MSG_001", "rule_rule_engineering")
        self.assertIn("already goes to this rule", self.rv.lbl_toast.cget("text"))
        self.assertEqual(self.tv.staged_actions, [])
        self.assertFalse(self.win.yaml_mgr.can_undo())

    def test_automatic_rename_is_not_an_unsaved_edit(self):
        self.rv.selected_folder_path = "Management\\Executive_Board\\Directors"
        self.rv._add_rule_in_selected_folder()            # "..._Directors_2", shown in the editor
        self.assertEqual(self.rv.var_rule_name.get(), "Management_Executive_Board_Directors_2")
        self.win.yaml_mgr.remove_rule_and_repool("rule_executive")   # it becomes the first rule
        self.rv.refresh_all()
        self.assertEqual(self.rv.var_rule_name.get(), "Management_Executive_Board_Directors")
        self.assertFalse(self.rv.is_rule_dirty())

    def test_collapsed_rule_stays_collapsed_after_refresh(self):
        self.tree.item("rule_rule_executive", open=False)
        self.rv.refresh_all()
        self.assertFalse(self.tree.item("rule_rule_executive", "open"))
        self.assertTrue(self.tree.item("rule_rule_engineering", "open"))


class TestExportImport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mine = os.path.join(self.temp_dir, "mine", "rules.yaml")
        self.theirs = os.path.join(self.temp_dir, "theirs", "rules.yaml")
        for p in (self.mine, self.theirs):
            os.makedirs(os.path.dirname(p))
            shutil.copy2(FIXTURE, p)
        self.shared = os.path.join(self.temp_dir, "shared.yaml")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_export_leaves_out_pst_paths(self):
        y = YamlConfigManager(self.mine)
        info = y.export_config(self.shared)
        self.assertEqual(info["rules"], len(y.rules))
        with open(self.shared, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["stores"]["active_archive"]["file_path"], "")
        self.assertIn("exported_at", data)
        self.assertEqual([r["id"] for r in data["rules"]], [r.id for r in y.rules])
        # Exporting does not touch my own file or undo history
        self.assertFalse(y.can_undo())

    def test_replace_takes_their_rules_but_keeps_my_pst(self):
        theirs = YamlConfigManager(self.theirs)
        theirs.rules = [r for r in theirs.rules if r.id != "rule_suppliers"]
        theirs.save()
        theirs.export_config(self.shared)

        mine = YamlConfigManager(self.mine)
        my_pst = mine.stores["active_archive"].file_path
        summary = mine.import_config(self.shared, mode="replace")
        self.assertEqual(summary["rules_added"], len(theirs.rules))
        self.assertNotIn("rule_suppliers", [r.id for r in mine.rules])
        self.assertEqual(mine.stores["active_archive"].file_path, my_pst)
        # Undo brings my rules back
        self.assertIn("Import", mine.undo_label())
        mine.undo()
        self.assertIn("rule_suppliers", [r.id for r in mine.rules])

    def test_merge_adds_new_rules_and_senders_without_duplicates(self):
        theirs = YamlConfigManager(self.theirs)
        exec_rule = next(r for r in theirs.rules if r.id == "rule_executive")
        exec_rule.emails.append("cfo@company.com")
        theirs.rules.append(type(exec_rule)(id="rule_executive", name="Keyence",
                                            domains=["@keyence.co.jp"], target_folder="Vendors\\Keyence",
                                            target_store="their_store"))
        theirs.save()
        theirs.export_config(self.shared)

        mine = YamlConfigManager(self.mine)
        before = len(mine.rules)
        summary = mine.import_config(self.shared, mode="merge")
        self.assertEqual(summary["rules_added"], 1)
        self.assertEqual(summary["rules_merged"], before)
        self.assertEqual(len(mine.rules), before + 1)
        my_exec = next(r for r in mine.rules if r.id == "rule_executive")
        self.assertIn("cfo@company.com", my_exec.emails)
        self.assertEqual(my_exec.groups, ["executive"])
        keyence = next(r for r in mine.rules if "Keyence" in r.known_names())
        self.assertNotEqual(keyence.id, "rule_executive")      # id clash -> fresh id
        self.assertEqual(keyence.target_store, "active_archive")  # unknown store -> mine
        self.assertEqual(summary["duplicate_senders"], 0)
        # Saved to disk
        reloaded = YamlConfigManager(self.mine)
        self.assertIn("Vendors_Keyence", [r.name for r in reloaded.rules])

    def test_merge_reports_senders_claimed_by_two_rules(self):
        theirs = YamlConfigManager(self.theirs)
        theirs.rules = [type(theirs.rules[0])(id="rule_x", name="Other", emails=["ceo@company.com"],
                                              target_folder="Elsewhere")]
        theirs.save()
        theirs.export_config(self.shared)
        mine = YamlConfigManager(self.mine)
        summary = mine.import_config(self.shared, mode="merge")
        self.assertEqual(summary["duplicate_senders"], 1)

    def test_invalid_file_is_refused(self):
        bad = os.path.join(self.temp_dir, "bad.yaml")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("just: text\n")
        mine = YamlConfigManager(self.mine)
        with self.assertRaises(ValueError):
            mine.import_config(bad)
        self.assertFalse(mine.can_undo())

    def test_main_window_import_flow(self):
        YamlConfigManager(self.theirs).export_config(self.shared)
        win = MainWindow(self.mine, outlook_client=MockOutlookClient())
        try:
            win.update()
            with patch.object(win, "_ask_import_path", return_value=self.shared), \
                    patch.object(win, "_ask_import_mode", return_value="merge"):
                win._import_rules()
            self.assertIn("Imported (merge)", win.tab_rules.lbl_toast.cget("text"))
            with patch.object(win, "_ask_export_path", return_value=os.path.join(self.temp_dir, "out.yaml")):
                win._export_rules()
            self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "out.yaml")))
            self.assertIn("Exported", win.tab_rules.lbl_toast.cget("text"))
            # Cancelled dialogs change nothing
            with patch.object(win, "_ask_import_path", return_value=""):
                win._import_rules()
        finally:
            win.destroy()


if __name__ == "__main__":
    unittest.main()
