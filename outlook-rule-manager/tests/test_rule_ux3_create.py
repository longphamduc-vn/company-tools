"""Rule UX Phase 3: create rules fast (drop on a folder, Quick New Rule dialog)."""
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from core.models import EmailMessage
from core.outlook_client import MockOutlookClient
from gui.quick_rule_dialog import QuickRuleDialog


def _msg(entry_id, name, email, subject="Hello"):
    return EmailMessage(entry_id=entry_id, subject=subject, sender_name=name, sender_email=email,
                        received_time=datetime.now())


class TestCreateRulesFast(unittest.TestCase):
    def setUp(self):
        from gui.main_window import MainWindow

        self.temp_dir = tempfile.mkdtemp()
        path = os.path.join(self.temp_dir, "rules.yaml")
        shutil.copy2(os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml"), path)
        self.win = MainWindow(path, outlook_client=MockOutlookClient())
        self.win.update()
        self.tv = self.win.tab_triage
        self.y = self.win.yaml_mgr

    def tearDown(self):
        try:
            self.win.destroy()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _folder_iid(self, path):
        return next(i for i, p in self.win.tab_rules.folder_nodes_map.items() if p == path)

    def _apply(self):
        def _answer(title, *_a, **_k):
            return title == "Apply Batch Changes"

        with patch("gui.triage_view.messagebox.askyesno", side_effect=_answer), \
                patch("gui.triage_view.messagebox.showinfo"), patch("gui.triage_view.messagebox.showwarning"):
            self.tv._apply_all_staged()

    def test_drop_on_empty_folder_stages_rule_named_after_folder_path(self):
        folder = "Purchasing_Team"
        msg = next(m for m in self.tv.messages if m.entry_id == "MSG_004")  # Kenji Sato (Sato Automation)
        n = self.tv.drop_messages_on_target(self._folder_iid(folder), [msg])
        self.assertEqual(n, 1)
        action = self.tv.staged_actions[0]
        self.assertEqual((action.action_type, action.rule_name, action.target_folder),
                         ("create_rule", "Purchasing_Team", folder))
        self._apply()
        rule = next(r for r in self.y.rules if r.name == "Purchasing_Team")
        self.assertEqual(rule.target_folder, folder)
        matched, _ = self.win.sync_engine.match_message(msg.sender_email, msg.subject)
        self.assertEqual(matched.id, rule.id)
        self.assertEqual(self.tv.last_apply_mismatches, [])

    def test_ctrl_drop_on_folder_gives_one_rule_for_all_mails(self):
        folder = "Purchasing_Team\\Vendor_Part"
        a = _msg("A1", "Anna", "anna@keyence.co.jp")
        b = _msg("B1", "Ben", "ben@keyence.co.jp")
        self.tv.messages.extend([a, b])
        self.tv.drop_messages_on_target(self._folder_iid(folder), [a, b], whole_domain=True)
        self.assertEqual([x.rule_name for x in self.tv.staged_actions],
                         ["Purchasing_Team_Vendor_Part", "Purchasing_Team_Vendor_Part"])
        self._apply()
        rules = [r for r in self.y.rules if r.name == "Purchasing_Team_Vendor_Part"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].domains, ["@keyence.co.jp"])

    def test_drop_on_folder_with_one_rule_adds_to_that_rule(self):
        folder = "Purchasing_Team\\Vendor_Part\\Omron_Unit"   # shown as one node with its rule
        msg = next(m for m in self.tv.messages if m.entry_id == "MSG_004")
        self.tv.drop_messages_on_target(self._folder_iid(folder), [msg])
        action = self.tv.staged_actions[0]
        self.assertEqual((action.action_type, action.rule_id), ("add_to_rule", "rule_suppliers"))

    def test_drop_on_folder_reuses_rule_with_same_name(self):
        folder = "Management\\Executive_Board\\Directors"
        m = _msg("X1", "Executive Board", "chair@company.com")
        self.tv.messages.append(m)
        self.tv.drop_messages_on_target(self._folder_iid(folder), [m])
        action = self.tv.staged_actions[0]
        self.assertEqual((action.action_type, action.rule_id), ("add_to_rule", "rule_executive"))

    def test_drop_on_unclassified_folder_is_refused(self):
        msg = next(m for m in self.tv.messages if m.entry_id == "MSG_004")
        n = self.tv.drop_messages_on_target(self._folder_iid("_Unclassified"), [msg])
        self.assertEqual(n, 0)
        self.assertEqual(self.tv.staged_actions, [])
        self.assertIn("cannot", self.tv.last_status_message)

    def test_new_rule_menu_uses_quick_dialog_with_smart_defaults(self):
        msg = next(m for m in self.tv.messages if m.entry_id == "MSG_002")  # ha.pham@omron.com
        with patch.object(self.tv, "_ask_quick_rule", return_value=("Omron Sales", "Vendors\\Omron", "email")) as ask:
            self.tv._open_create_hierarchical_rule_dialog(msg)
        kwargs = ask.call_args.kwargs
        self.assertEqual(kwargs["default_name"], "Pham Thu Ha")
        self.assertEqual(kwargs["default_folder"], "Purchasing_Team\\Vendor_Part\\Omron_Unit")  # rule already handling @omron.com
        self.assertNotIn("_Unclassified", kwargs["folders"])
        action = self.tv.staged_actions[0]
        self.assertEqual((action.rule_name, action.target_folder, action.match_mode),
                         ("Omron Sales", "Vendors\\Omron", "email"))
        # Unknown domain falls back to the last folder used
        other = _msg("Z9", "Zed", "zed@unknown.example")
        self.assertEqual(self.tv._default_folder_for(other), "Vendors\\Omron")

    def test_cancel_quick_dialog_stages_nothing(self):
        msg = next(m for m in self.tv.messages if m.entry_id == "MSG_002")
        with patch.object(self.tv, "_ask_quick_rule", return_value=None):
            self.tv._open_create_hierarchical_rule_dialog(msg)
        self.assertEqual(self.tv.staged_actions, [])

    def test_rules_tab_new_rule_is_named_after_folder_and_name_is_locked(self):
        rv = self.win.tab_rules
        self.win.show_rule_details()
        self.win.update()
        rv.selected_folder_path = "Management\Executive_Board\Directors"
        rv._add_rule_in_selected_folder()
        self.win.update()
        # The folder already has a rule, so the new one gets _2
        self.assertEqual(rv.var_rule_name.get(), "Management_Executive_Board_Directors_2")
        self.assertEqual(str(rv.ent_rule_name.cget("state")), "readonly")
        self.assertEqual(rv.lbl_rule_prefix.cget("text"), "[Companion]")
        # A typed name never sticks: names always follow the folder
        rv.selected_rule.name = "Board Secretary"
        self.y.save()
        self.assertFalse(any(r.name == "Board Secretary" for r in self.y.rules))

    def test_rules_tab_manual_names_when_auto_naming_is_off(self):
        self.y.settings["auto_rule_names"] = False
        rv = self.win.tab_rules
        rv.selected_folder_path = "Management\Executive_Board\Directors"
        with patch.object(rv, "_focus_new_rule_name"):
            rv._add_rule_in_selected_folder()
        self.assertEqual(str(rv.ent_rule_name.cget("state")), "normal")
        rv.ent_rule_name.delete(0, "end")
        rv.ent_rule_name.insert(0, "Board Secretary")
        self.assertTrue(rv.ent_rule_name.bind("<Return>"))
        rv._save_rule_changes()
        self.assertTrue(any(r.name == "Board Secretary" for r in self.y.rules))

    def test_rules_tab_new_rule_refused_inside_unclassified(self):
        rv = self.win.tab_rules
        rv.selected_folder_path = "_Unclassified"
        before = len(self.y.rules)
        rv._add_rule_in_selected_folder()
        self.assertEqual(len(self.y.rules), before)
        self.assertIn("cannot", rv.lbl_toast.cget("text"))


class TestQuickRuleDialog(unittest.TestCase):
    def setUp(self):
        import tkinter as tk

        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def _dialog(self, **kw):
        base = dict(folders=["Team\\A", "Team\\B", "Other"], default_name="Alice", default_folder="",
                    sender_email="alice@x.com", sender_domain="@x.com")
        base.update(kw)
        return QuickRuleDialog(self.root, **base)

    def test_folder_hint_and_filtering(self):
        d = self._dialog()
        self.assertIn("Pick a folder", d.lbl_folder_hint.cget("text"))
        d.var_folder.set("team")
        d._on_folder_typed()
        self.assertEqual(list(d.cbo_folder.cget("values")), ["Team\\A", "Team\\B"])
        d.var_folder.set("Team\\A")
        d._update_folder_hint()
        self.assertEqual(d.lbl_folder_hint.cget("text"), "Existing folder.  Outlook rule: [Companion] Team_A")
        d.var_folder.set("Team/New")
        d._update_folder_hint()
        self.assertEqual(d.lbl_folder_hint.cget("text"),
                         "New folder will be created.  Outlook rule: [Companion] Team_New")
        d.destroy()

    def test_auto_name_dialog_name_is_folder_and_locked(self):
        d = self._dialog(default_folder="Team\\A")
        self.assertEqual(str(d.ent_name.cget("state")), "readonly")
        self.assertEqual(d.var_name.get(), "Team_A")
        d.var_folder.set("Team\\B")
        d._on_folder_typed()
        self.assertEqual(d.var_name.get(), "Team_B")
        d.ok()
        self.assertEqual(d.result, ("Team_B", "Team\\B", "email"))

    def test_name_follows_folder_until_typed(self):
        d = self._dialog(default_folder="Team\\A", auto_name=False)
        self.assertEqual(d.var_name.get(), "Team_A")
        d.var_folder.set("Team\\B\\Sub")
        d._on_folder_typed()
        self.assertEqual(d.var_name.get(), "Team_B_Sub")
        d._on_name_typed(SimpleNamespace(keysym="x"))
        d.var_name.set("Alice")
        d.var_folder.set("Other")
        d._on_folder_typed()
        self.assertEqual(d.var_name.get(), "Alice")
        d.destroy()

    def test_ok_returns_normalized_result_and_validates(self):
        d = self._dialog(default_folder="Team\\A", auto_name=False)
        d._on_name_typed(SimpleNamespace(keysym="x"))
        d.var_name.set("Alice")
        d.var_scope.set("domain")
        d.var_folder.set(" Team / C ")
        d.ok()
        self.assertEqual(d.result, ("Alice", "Team\\C", "domain"))

    def test_blocked_or_empty_folder_keeps_dialog_open(self):
        d = self._dialog()
        d.var_folder.set("_Unclassified\\X")
        d.ok()
        self.assertIsNone(d.result)
        self.assertTrue(d.winfo_exists())
        d.var_folder.set("")
        d.ok()
        self.assertIsNone(d.result)
        d.cancel()
        self.assertFalse(d.winfo_exists())


if __name__ == "__main__":
    unittest.main()
