"""Rule UX Phase 2: in-memory Undo and refusing moves into the Unclassified folder."""
import os
import shutil
import tempfile
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.outlook_client import MockOutlookClient
from core.yaml_manager import YamlConfigManager

EXEC_ID = r"rule_management\executive_board\directors"
ENG_ID = r"rule_engineering_team\scada_part\plc_unit"
SUP_ID = r"rule_purchasing_team\vendor_part\omron_unit"


def _copy_fixture(temp_dir):
    path = os.path.join(temp_dir, "rules.yaml")
    shutil.copy2(os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml"), path)
    return path


class TestUndoCore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.y = YamlConfigManager(_copy_fixture(self.temp_dir))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _folder(self, rid):
        return next(r for r in self.y.rules if r.id == rid).target_folder

    def test_undo_folder_move_restores_rules_and_file(self):
        before = self._folder(ENG_ID)
        ok, _ = self.y.move_folder_hierarchy("Engineering_Team", "Purchasing_Team")
        self.assertTrue(ok)
        self.assertNotEqual(self._folder(ENG_ID), before)
        self.assertEqual(self.y.undo_label(), "Move folder 'Engineering_Team' to 'Purchasing_Team\\Engineering_Team'")

        label = self.y.undo()
        self.assertTrue(label.startswith("Move folder"))
        self.assertEqual(self._folder(ENG_ID), before)
        self.assertEqual(
            next(r for r in YamlConfigManager(self.y.config_path).rules if r.id == ENG_ID).target_folder,
            before,
        )
        self.assertFalse(self.y.can_undo())

    def test_multi_step_undo_and_limit(self):
        for i in range(self.y.UNDO_LIMIT + 1):
            self.y.add_folder(f"Tmp_{i}")
        self.assertEqual(len(self.y._undo_stack), self.y.UNDO_LIMIT)
        self.y.undo()
        self.y.undo()
        self.assertNotIn(f"Tmp_{self.y.UNDO_LIMIT}", self.y.folders)
        self.assertNotIn(f"Tmp_{self.y.UNDO_LIMIT - 1}", self.y.folders)
        self.assertIn(f"Tmp_{self.y.UNDO_LIMIT - 2}", self.y.folders)

    def test_undo_delete_rule_restores_rule_and_pool(self):
        self.y.remove_rule_and_repool(EXEC_ID)
        self.assertIn("ceo@company.com", self.y.unclassified_pool)
        self.assertEqual(self.y.undo(), "Delete rule 'Management_Executive_Board_Directors'")
        self.assertTrue(any(r.id == EXEC_ID for r in self.y.rules))
        self.assertNotIn("ceo@company.com", self.y.unclassified_pool)

    def test_save_without_change_adds_no_undo_step_and_empty_undo_is_noop(self):
        self.y.save()
        self.assertFalse(self.y.can_undo())
        self.assertIsNone(self.y.undo())

    def test_reload_clears_history(self):
        self.y.add_folder("X")
        self.y.load()
        self.assertFalse(self.y.can_undo())

    def test_refuse_moves_into_unclassified(self):
        ok1, _ = self.y.move_rule_to_folder(EXEC_ID, "_Unclassified\\Management")
        ok2, _ = self.y.move_rule_to_folder(EXEC_ID, "_unclassified")
        self.assertFalse(ok1)
        self.assertFalse(ok2)
        ok, msg = self.y.move_folder_hierarchy("Management", "_Unclassified")
        self.assertFalse(ok)
        self.assertIn("_Unclassified", msg)
        ok, _ = self.y.move_folder_hierarchy("_Unclassified", "Management")
        self.assertFalse(ok)
        self.assertEqual(self._folder(EXEC_ID), "Management\\Executive_Board\\Directors")
        ok_unc, _ = self.y.move_rule_to_folder("rule_unclassified", "_Unclassified")
        self.assertTrue(ok_unc)


class TestUndoGui(unittest.TestCase):
    def setUp(self):
        from gui.main_window import MainWindow

        self.temp_dir = tempfile.mkdtemp()
        self.win = MainWindow(_copy_fixture(self.temp_dir), outlook_client=MockOutlookClient())
        self.win.update()

    def tearDown(self):
        try:
            self.win.destroy()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rules_tab_drag_folder_then_undo_button(self):
        rv = self.win.tab_rules
        self.assertEqual(str(rv.btn_undo.cget("state")), "disabled")
        src = next(i for i, p in rv.folder_nodes_map.items() if p == "Engineering_Team")
        dst = next(i for i, p in rv.folder_nodes_map.items() if p == "Purchasing_Team")
        rv._execute_drop(src, dst)
        self.assertEqual(str(rv.btn_undo.cget("state")), "normal")
        self.assertIn("Move folder", rv.btn_undo.cget("text"))

        rv.btn_undo.invoke()
        rule = next(r for r in self.win.yaml_mgr.rules if r.id == ENG_ID)
        self.assertEqual(rule.target_folder, "Engineering_Team\\SCADA_Part\\PLC_Unit")
        self.assertIn("Undone:", rv.lbl_toast.cget("text"))
        self.assertIsNone(rv.selected_rule)

    def test_drop_into_unclassified_is_refused_with_toast(self):
        rv = self.win.tab_rules
        src = next(i for i, p in rv.folder_nodes_map.items() if p == "Management")
        dst = next(i for i, p in rv.folder_nodes_map.items() if p == "_Unclassified")
        with patch("gui.rule_manager_view.messagebox.showwarning") as warn:
            rv._execute_drop(src, dst)
        warn.assert_not_called()
        self.assertIn("cannot be moved into", rv.lbl_toast.cget("text"))
        self.assertFalse(self.win.yaml_mgr.can_undo())

    def test_ctrl_z_ignored_in_text_widgets_and_works_elsewhere(self):
        self.win.yaml_mgr.add_folder("Tmp")
        text_event = SimpleNamespace(widget=tk.Text(self.win))
        self.assertIsNone(self.win._on_ctrl_z(text_event))
        self.assertTrue(self.win.yaml_mgr.can_undo())
        self.assertEqual(self.win._on_ctrl_z(SimpleNamespace(widget=self.win)), "break")
        self.assertNotIn("Tmp", self.win.yaml_mgr.folders)

    def test_apply_is_one_undo_step(self):
        tv = self.win.tab_triage
        msgs = [m for m in tv.messages if m.entry_id in ("MSG_004", "MSG_005")]
        tv.drop_messages_on_target(f"rule_{SUP_ID}", msgs)

        def _answer(title, *_a, **_k):
            return title == "Apply Batch Changes"

        with patch("gui.triage_view.messagebox.askyesno", side_effect=_answer), \
                patch("gui.triage_view.messagebox.showinfo"):
            tv._apply_all_staged()
        self.assertEqual(self.win.yaml_mgr.undo_label(), "Apply 2 inbox changes")
        self.assertEqual(str(self.win.tab_rules.btn_undo.cget("state")), "normal")
        label = self.win.undo_last()
        self.assertEqual(label, "Apply 2 inbox changes")
        rule = next(r for r in self.win.yaml_mgr.rules if r.id == SUP_ID)
        self.assertNotIn("sato@sato-automation.jp", self.win.yaml_mgr.get_all_emails_for_rule(rule))
        self.assertIn("emails already moved", tv.last_status_message)


if __name__ == "__main__":
    unittest.main()
