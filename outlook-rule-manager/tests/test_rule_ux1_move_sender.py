"""Rule UX Phase 1: moving a sender between rules really moves it (preview == result)."""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from core.models import AddressGroup, RuleConfig
from core.outlook_client import MockOutlookClient
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager


class TestAssignSenderCore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        shutil.copy2(os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml"), self.config_path)
        self.y = YamlConfigManager(self.config_path)
        self.engine = SyncEngine(self.y, MockOutlookClient())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _rule(self, rid):
        return next(r for r in self.y.rules if r.id == rid)

    def _holders(self, email):
        return [r.id for r in self.y.rules if email in self.y.get_all_emails_for_rule(r)]

    def test_move_sender_out_of_single_use_group(self):
        # lead.scada@ is in group 'engineering', used only by rule_engineering
        preview = self.y.preview_sender_move("lead.scada@company.com", "rule_suppliers")
        self.assertEqual(preview["from_rules"], ["SCADA PLC Maintenance"])
        self.assertEqual(preview["shared_groups"], [])

        result = self.y.assign_sender("lead.scada@company.com", "rule_suppliers")
        self.assertEqual(result["moved_from"], ["SCADA PLC Maintenance"])
        self.assertEqual(self._holders("lead.scada@company.com"), ["rule_suppliers"])
        matched, _ = self.engine.match_message("lead.scada@company.com", "x")
        self.assertEqual(matched.id, "rule_suppliers")

    def test_move_direct_email_between_rules(self):
        self._rule("rule_executive").emails.append("boss@x.com")
        self.y.assign_sender("boss@x.com", "rule_engineering")
        self.assertNotIn("boss@x.com", self._rule("rule_executive").emails)
        self.assertEqual(self._holders("boss@x.com"), ["rule_engineering"])

    def test_move_domain_removes_domain_from_old_rule_only(self):
        self.y.assign_sender("@omron.com", "rule_engineering", as_domain=True)
        self.assertNotIn("@omron.com", self.y.get_all_domains_for_rule(self._rule("rule_suppliers")))
        self.assertIn("@omron.com", self.y.get_all_domains_for_rule(self._rule("rule_engineering")))
        # emails in the old rule are untouched
        self.assertIn("sales@vendor.com", self.y.get_all_emails_for_rule(self._rule("rule_suppliers")))

    def test_exact_email_beats_domain_without_removing_domain(self):
        self.y.assign_sender("ha.pham@omron.com", "rule_engineering")
        self.assertIn("@omron.com", self.y.get_all_domains_for_rule(self._rule("rule_suppliers")))
        matched, _ = self.engine.match_message("ha.pham@omron.com", "x")
        self.assertEqual(matched.id, "rule_engineering")
        other, _ = self.engine.match_message("other@omron.com", "x")
        self.assertEqual(other.id, "rule_suppliers")

    def test_shared_group_is_untouched_unless_allowed(self):
        self._rule("rule_unclassified").groups.append("executive")  # 'executive' now shared by 2 rules
        preview = self.y.preview_sender_move("ceo@company.com", "rule_engineering")
        self.assertEqual(preview["shared_groups"], [("Executive Board", ["Executive Board", "[Unclassified]"])])

        result = self.y.assign_sender("ceo@company.com", "rule_engineering")
        self.assertEqual(result["blocked_by_groups"], [("Executive Board", ["Executive Board", "[Unclassified]"])])
        self.assertIn("ceo@company.com", self.y.groups["executive"].emails)

        result = self.y.assign_sender("ceo@company.com", "rule_engineering", remove_from_shared_groups=True)
        self.assertNotIn("ceo@company.com", self.y.groups["executive"].emails)
        self.assertEqual(self._holders("ceo@company.com"), ["rule_engineering"])

    def test_assign_removes_from_unclassified_pool_and_is_idempotent(self):
        self.y.assign_sender("former.contractor@vendor.com", "rule_engineering")
        self.assertNotIn("former.contractor@vendor.com", self.y.unclassified_pool)
        self.y.assign_sender("former.contractor@vendor.com", "rule_engineering")
        self.assertEqual(self.y.groups["engineering"].emails.count("former.contractor@vendor.com"), 1)

    def test_detach_for_new_rule(self):
        self.y.rules.append(RuleConfig(id="rule_new", name="New", emails=["eng1@company.com"], target_folder="X"))
        moved, blocked = self.y.detach_sender("eng1@company.com", except_rule_id="rule_new")
        self.assertEqual(moved, ["SCADA PLC Maintenance"])
        self.assertEqual(blocked, [])
        self.assertEqual(self._holders("eng1@company.com"), ["rule_new"])


class TestMoveSenderThroughInbox(unittest.TestCase):
    """GUI flow: drop/stage -> preview shows 'from' -> Apply -> match_message agrees with preview."""

    def setUp(self):
        import tkinter as tk  # noqa: F401
        from gui.main_window import MainWindow

        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        shutil.copy2(os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml"), self.config_path)
        self.win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        self.win.update()
        self.tv = self.win.tab_triage

    def tearDown(self):
        try:
            self.win.destroy()
        except Exception:
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _apply(self, shared_answer=False):
        def _answer(title, *_a, **_k):
            if title == "Shared Address Groups":
                return shared_answer
            return title == "Apply Batch Changes"

        with patch("gui.triage_view.messagebox.askyesno", side_effect=_answer) as ask, \
                patch("gui.triage_view.messagebox.showinfo"), patch("gui.triage_view.messagebox.showwarning"):
            self.tv._apply_all_staged()
        return ask

    def test_preview_then_apply_moves_sender(self):
        msg = next(m for m in self.tv.messages if m.entry_id == "MSG_001")  # lead.scada@ -> SCADA rule today
        self.tv.drop_messages_on_target("rule_rule_suppliers", [msg])
        self.assertEqual(self.tv.staged_actions[0].moved_from, ["SCADA PLC Maintenance"])
        self.assertIn("(from SCADA PLC Maintenance)", self.tv.tree_inbox.set("MSG_001", "WillGoTo"))
        promised = self.tv.staged_actions[0].target_folder

        self._apply()
        matched, _ = self.win.sync_engine.match_message(msg.sender_email, msg.subject)
        self.assertEqual(matched.target_folder, promised)
        self.assertEqual(self.tv.last_apply_mismatches, [])

    def test_shared_group_answer_no_reports_mismatch(self):
        y = self.win.yaml_mgr
        next(r for r in y.rules if r.id == "rule_unclassified").groups.append("executive")
        msg = next(m for m in self.tv.messages if m.entry_id == "MSG_003")  # coo@company.com
        self.tv.drop_messages_on_target("rule_rule_engineering", [msg])
        ask = self._apply(shared_answer=False)
        titles = [c.args[0] for c in ask.call_args_list]
        self.assertEqual(titles.count("Shared Address Groups"), 1)
        self.assertEqual(len(self.tv.last_apply_mismatches), 1)
        self.assertIn("coo@company.com", self.tv.last_apply_mismatches[0])

    def test_shared_group_answer_yes_moves(self):
        y = self.win.yaml_mgr
        next(r for r in y.rules if r.id == "rule_unclassified").groups.append("executive")
        msg = next(m for m in self.tv.messages if m.entry_id == "MSG_003")
        self.tv.drop_messages_on_target("rule_rule_engineering", [msg])
        self._apply(shared_answer=True)
        self.assertEqual(self.tv.last_apply_mismatches, [])


if __name__ == "__main__":
    unittest.main()
