"""Rule UX Phase 1: moving a sender between rules really moves it (preview == result)."""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from core.models import RuleConfig
from core.outlook_client import MockOutlookClient
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager

EXEC_ID = r"rule_management\executive_board\directors"
ENG_ID = r"rule_engineering_team\scada_part\plc_unit"
SUP_ID = r"rule_purchasing_team\vendor_part\omron_unit"


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

    def test_move_sender_between_rules_preview_and_result(self):
        preview = self.y.preview_sender_move("lead.scada@company.com", SUP_ID)
        self.assertEqual(preview["from_rules"], ["Engineering_Team_SCADA_Part_PLC_Unit"])

        result = self.y.assign_sender("lead.scada@company.com", SUP_ID)
        self.assertEqual(result["moved_from"], ["Engineering_Team_SCADA_Part_PLC_Unit"])
        self.assertEqual(self._holders("lead.scada@company.com"), [SUP_ID])
        matched, _ = self.engine.match_message("lead.scada@company.com", "x")
        self.assertEqual(matched.id, SUP_ID)

    def test_move_direct_email_between_rules(self):
        self._rule(EXEC_ID).emails.append("boss@x.com")
        self.y.assign_sender("boss@x.com", ENG_ID)
        self.assertNotIn("boss@x.com", self._rule(EXEC_ID).emails)
        self.assertEqual(self._holders("boss@x.com"), [ENG_ID])

    def test_move_domain_removes_domain_from_old_rule_only(self):
        self.y.assign_sender("@omron.com", ENG_ID, as_domain=True)
        self.assertNotIn("@omron.com", self.y.get_all_domains_for_rule(self._rule(SUP_ID)))
        self.assertIn("@omron.com", self.y.get_all_domains_for_rule(self._rule(ENG_ID)))
        self.assertIn("sales@vendor.com", self.y.get_all_emails_for_rule(self._rule(SUP_ID)))

    def test_exact_email_beats_domain_without_removing_domain(self):
        self.y.assign_sender("ha.pham@omron.com", ENG_ID)
        self.assertIn("@omron.com", self.y.get_all_domains_for_rule(self._rule(SUP_ID)))
        matched, _ = self.engine.match_message("ha.pham@omron.com", "x")
        self.assertEqual(matched.id, ENG_ID)
        other, _ = self.engine.match_message("other@omron.com", "x")
        self.assertEqual(other.id, SUP_ID)

    def test_assign_removes_from_unclassified_pool_and_is_idempotent(self):
        self.y.assign_sender("former.contractor@vendor.com", ENG_ID)
        self.assertNotIn("former.contractor@vendor.com", self.y.unclassified_pool)
        self.y.assign_sender("former.contractor@vendor.com", ENG_ID)
        self.assertEqual(self._rule(ENG_ID).emails.count("former.contractor@vendor.com"), 1)

    def test_detach_for_new_rule(self):
        self.y.rules.append(RuleConfig(id="rule_x", name="X", emails=["eng1@company.com"], target_folder="X"))
        moved = self.y.detach_sender("eng1@company.com", except_rule_id="rule_x")
        self.assertEqual(moved, ["Engineering_Team_SCADA_Part_PLC_Unit"])
        self.assertEqual(self._holders("eng1@company.com"), ["rule_x"])


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

    def _apply(self):
        with patch("gui.triage_view.messagebox.askyesno", return_value=True) as ask, \
                patch("gui.triage_view.messagebox.showinfo"), patch("gui.triage_view.messagebox.showwarning"):
            self.tv._apply_all_staged()
        return ask

    def test_preview_then_apply_moves_sender(self):
        msg = next(m for m in self.tv.messages if m.entry_id == "MSG_001")  # lead.scada@ -> SCADA rule today
        self.tv.drop_messages_on_target(f"rule_{SUP_ID}", [msg])
        self.assertEqual(self.tv.staged_actions[0].moved_from, ["Engineering_Team_SCADA_Part_PLC_Unit"])
        self.assertIn("(from Engineering_Team_SCADA_Part_PLC_Unit)", self.tv.tree_inbox.set("MSG_001", "WillGoTo"))
        promised = self.tv.staged_actions[0].target_folder

        self._apply()
        matched, _ = self.win.sync_engine.match_message(msg.sender_email, msg.subject)
        self.assertEqual(matched.target_folder, promised)
        self.assertEqual(self.tv.last_apply_mismatches, [])


if __name__ == "__main__":
    unittest.main()
