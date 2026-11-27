"""Drag & drop of emails from the mail list onto the Rules navigator (single-screen layout)."""
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.outlook_client import MockOutlookClient
from gui.main_window import MainWindow

CTRL = 0x0004
EXEC_ID = r"rule_management\executive_board\directors"
SUP_ID = r"rule_purchasing_team\vendor_part\omron_unit"


class TestInboxDragDrop(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        sample = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")
        shutil.copy2(sample, self.config_path)
        self.win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        self.win.geometry("1280x760+0+0")
        self.win.update()
        self.tv = self.win.tab_triage
        self.rv = self.win.tab_rules

    def tearDown(self):
        try:
            self.win.destroy()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # helpers -------------------------------------------------------------
    def _row_root_xy(self, tree, iid, column=None):
        tree.see(iid)
        self.win.update()
        x, y, w, h = tree.bbox(iid, column) if column else tree.bbox(iid)
        return tree.winfo_rootx() + x + min(w // 2, 60), tree.winfo_rooty() + y + h // 2, y + h // 2

    def _drag(self, inbox_iid, to_xy, state=0, steps=3):
        tree = self.tv.tree_inbox
        x_root, y_root, y_local = self._row_root_xy(tree, inbox_iid)
        current = tree.selection()
        self.tv._on_drag_press(SimpleNamespace(x=5, y=y_local, x_root=x_root, y_root=y_root, state=state))
        if inbox_iid not in current or len(current) > 1:
            tree.selection_set(inbox_iid)
            self.win.update()
        tx, ty = to_xy
        for i in range(1, steps + 1):
            mx = x_root + (tx - x_root) * i // steps
            my = y_root + (ty - y_root) * i // steps
            self.tv._on_drag_motion(SimpleNamespace(x_root=mx, y_root=my, state=state))
        self.tv._on_drag_release(SimpleNamespace(x_root=tx, y_root=ty, state=state))
        self.win.update()

    def _rule_xy(self, rule_id):
        x, y, _ = self._row_root_xy(self.rv.tree, f"rule_{rule_id}", "#0")
        return x, y

    # tests ---------------------------------------------------------------
    def test_navigator_resolves_rules_folders_and_root(self):
        self.assertEqual(self.rv.resolve_drop_iid(f"rule_{SUP_ID}"), ("rule", SUP_ID))
        fld = next(i for i, p in self.rv.folder_nodes_map.items() if p == "Purchasing_Team")
        self.assertEqual(self.rv.resolve_drop_iid(fld), ("folder", "Purchasing_Team"))
        self.assertEqual(self.rv.resolve_drop_iid("__HIERARCHY__"), ("new", None))
        self.assertIsNone(self.rv.resolve_drop_iid("__POOL__"))

    def test_drag_one_email_onto_rule_stages_sender(self):
        self._drag("MSG_004", self._rule_xy(SUP_ID))
        self.assertEqual(len(self.tv.staged_actions), 1)
        action = self.tv.staged_actions[0]
        self.assertEqual((action.action_type, action.rule_id, action.match_mode), ("add_to_rule", SUP_ID, "email"))
        self.assertEqual(action.sender_email, "sato@sato-automation.jp")
        self.assertTrue(self.tv.pending_bar.winfo_ismapped())
        self.assertTrue(str(self.tv.tree_inbox.set("MSG_004", "WillGoTo")).startswith("* "))
        self.assertIn("Purchasing_Team_Vendor_Part_Omron_Unit", self.rv.lbl_toast.cget("text"))
        # Ghost window and hover cleaned up
        self.assertIsNone(self.tv._drag_ghost)
        self.assertFalse(self.tv._drag_active)
        self.assertNotIn("drop_hover", self.rv.tree.item(f"rule_{SUP_ID}", "tags"))

    def test_ctrl_drop_stages_whole_domain(self):
        self._drag("MSG_004", self._rule_xy(SUP_ID), state=CTRL)
        self.assertEqual(self.tv.staged_actions[0].match_mode, "domain")
        self.assertEqual(self.tv.staged_actions[0].sender_domain, "@sato-automation.jp")

    def test_drag_multi_selection_stages_all_and_keeps_selection(self):
        self.tv.tree_inbox.selection_set(("MSG_004", "MSG_005"))
        self.win.update()
        self._drag("MSG_005", self._rule_xy(EXEC_ID))
        staged = sorted(a.message_id for a in self.tv.staged_actions)
        self.assertEqual(staged, ["MSG_004", "MSG_005"])
        self.assertEqual(set(self.tv.tree_inbox.selection()), {"MSG_004", "MSG_005"})

    def test_drop_on_root_opens_new_rule_dialog(self):
        root_xy = self._row_root_xy(self.rv.tree, "__HIERARCHY__", "#0")[:2]
        with patch.object(self.tv, "_open_create_hierarchical_rule_dialog") as dlg:
            self._drag("MSG_004", root_xy)
        dlg.assert_called_once()
        self.assertEqual(dlg.call_args[0][0].entry_id, "MSG_004")
        self.assertEqual(self.tv.staged_actions, [])

    def test_release_outside_navigator_or_tiny_move_does_nothing(self):
        inbox = self.tv.tree_inbox
        outside = (inbox.winfo_rootx() + 20, inbox.winfo_rooty() + 40)
        self._drag("MSG_004", outside)
        x, y, y_local = self._row_root_xy(inbox, "MSG_004")
        self.tv._on_drag_press(SimpleNamespace(x=5, y=y_local, x_root=x, y_root=y, state=0))
        self.tv._on_drag_motion(SimpleNamespace(x_root=x + 3, y_root=y + 2, state=0))
        self.assertFalse(self.tv._drag_active)
        self.tv._on_drag_release(SimpleNamespace(x_root=x + 3, y_root=y + 2, state=0))
        self.assertEqual(self.tv.staged_actions, [])
        self.assertIsNone(self.tv._drag_ghost)

    def test_apply_after_drop_writes_sender_into_yaml_and_refreshes_tree(self):
        self._drag("MSG_004", self._rule_xy(SUP_ID))

        def _answer(title, *_args, **_kwargs):
            return title == "Apply Batch Changes"

        with patch("gui.triage_view.messagebox.askyesno", side_effect=_answer), \
                patch("gui.triage_view.messagebox.showinfo"):
            self.tv._apply_all_staged()
        rule = next(r for r in self.win.yaml_mgr.rules if r.id == SUP_ID)
        self.assertIn("sato@sato-automation.jp", self.win.yaml_mgr.get_all_emails_for_rule(rule))
        self.assertEqual(self.rv.tree.set(f"rule_{SUP_ID}", "Details"), "2 senders, 2 domains")

    def test_clicks_switch_right_pane_between_mail_and_rule(self):
        self.assertEqual(self.win.details_mode, "mail")
        self.rv.tree.selection_set(f"rule_{SUP_ID}")
        self.rv._on_tree_select()
        self.rv._notify_item_activated()
        self.win.update()
        self.assertEqual(self.win.details_mode, "rule")
        self.assertTrue(self.win.inspector_host.winfo_ismapped())
        self.tv.tree_inbox.selection_set("MSG_001")
        self.tv._notify_message_activated()
        self.win.update()
        self.assertEqual(self.win.details_mode, "mail")
        self.assertTrue(self.win.reader_host.winfo_ismapped())


if __name__ == "__main__":
    unittest.main()
