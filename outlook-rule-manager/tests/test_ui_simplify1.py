"""Tests for UI Simplify Phase S1: single triage flow, Will go to column, and slim pending bar."""
from datetime import datetime
import os
import shutil
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from core.models import EmailMessage
from core.outlook_client import MockOutlookClient
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager
from gui.main_window import MainWindow
from tests.fakes import FakeNamespace, FakeStore


def _find_buttons(root: tk.Misc):
    """Return all descendant ttk.Button widgets."""
    found = []
    queue = list(root.winfo_children())
    while queue:
        w = queue.pop(0)
        if isinstance(w, ttk.Button):
            found.append(w)
        queue.extend(w.winfo_children())
    return found


class TestUiSimplifyPhaseS1(unittest.TestCase):
    """Integration tests for UI_SIMPLIFY_PLAN Phase S1."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        sample_config = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")
        shutil.copy2(sample_config, self.config_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_two_pane_layout_no_drag_drop_or_left_rule_tree(self):
        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.geometry("1120x720")
            win.update()
            triage = win.tab_triage

            # Removed widgets/methods
            self.assertFalse(hasattr(triage, "tree_rules"))
            self.assertFalse(hasattr(triage, "drop_new_zone"))
            self.assertFalse(hasattr(triage, "mb_assign_rule"))
            self.assertFalse(hasattr(triage, "_on_drag_start"))

            # Drag bindings must NOT exist on tree_inbox
            self.assertFalse(triage.tree_inbox.bind("<ButtonPress-1>"))
            self.assertFalse(triage.tree_inbox.bind("<B1-Motion>"))
            self.assertFalse(triage.tree_inbox.bind("<ButtonRelease-1>"))

            # 2 panes: Inbox list left, Reading/Actions right
            self.assertEqual(len(triage.paned.panes()), 2)

            # Right-click menu mirrors inspector actions
            menu_labels = [
                triage.menu_inbox.entrycget(i, "label")
                for i in range(triage.menu_inbox.index("end") + 1)
                if triage.menu_inbox.type(i) == "command"
            ]
            self.assertEqual(menu_labels, ["Add to Rule...", "New Rule...", "Move Now"])

            # Expand/Collapse Tree buttons removed from top bar
            top_btn_texts = [
                w.cget("text")
                for w in triage.winfo_children()[0].winfo_children()
                if isinstance(w, ttk.Button)
            ]
            self.assertEqual(top_btn_texts, ["Refresh Inbox"])
        finally:
            win.destroy()

    def test_will_go_to_column_matches_sync_engine_and_staged_prefix(self):
        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.update()
            triage = win.tab_triage

            cols = list(triage.tree_inbox["columns"])
            self.assertIn("WillGoTo", cols)
            will_idx = cols.index("WillGoTo")
            self.assertEqual(triage.tree_inbox.heading("WillGoTo", "text"), "Will go to")

            # Compare every row's "Will go to" against SyncEngine.match_message
            for msg in triage.messages:
                matched_rule, _ = triage.sync_engine.match_message(msg.sender_email, msg.subject)
                expected = matched_rule.target_folder if matched_rule else "Inbox (no rule)"
                row_vals = triage.tree_inbox.item(msg.entry_id, "values")
                self.assertEqual(row_vals[will_idx], expected)

            # Stage an email -> "Will go to" shows "* <target_folder>"
            stranger = next(
                m for m in triage.messages if triage.sync_engine.match_message(m.sender_email, m.subject)[0] is None
            )
            exec_rule = next(r for r in win.yaml_mgr.rules if r.id == "rule_executive")
            triage._stage_add_to_existing_rule(stranger, exec_rule.id, match_mode="email")
            win.update()
            staged_vals = triage.tree_inbox.item(stranger.entry_id, "values")
            self.assertEqual(staged_vals[will_idx], f"* {exec_rule.target_folder}")
        finally:
            win.destroy()

    def test_add_to_rule_flow_pending_bar_review_and_apply_to_yaml(self):
        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.geometry("1120x720")
            win.update()
            triage = win.tab_triage

            # Initially N = 0 -> pending bar hidden
            self.assertFalse(bool(triage.pending_bar.winfo_ismapped()))

            # Inject a deterministic stranger email so Add to Rule is clean
            stranger = EmailMessage(
                entry_id="MSG_ACME",
                subject="New RFQ",
                sender_name="Acme Rep",
                sender_email="rep@acme.example",
                received_time=datetime.now(),
            )
            triage.messages.append(stranger)
            triage._populate_inbox_table()
            triage.tree_inbox.selection_set("MSG_ACME")
            triage._on_message_select_fast(None)
            self.assertIs(triage.selected_message, stranger)

            # 1. Verify rule picker dialog search filter & default/domain scope directly
            dlg, controls, get_result = triage._build_rule_picker_dialog(stranger, allow_scope=True)
            try:
                win.update()
                self.assertEqual(controls["scope_var"].get(), "email")
                # Filter by folder substring "Directors"
                controls["filter_var"].set("Directors")
                win.update_idletasks()
                self.assertEqual(len(controls["filtered_rules"]), 1)
                self.assertEqual(controls["filtered_rules"][0].id, "rule_executive")
                controls["scope_var"].set("domain")
                controls["ok_button"].invoke()
            finally:
                if dlg.winfo_exists():
                    dlg.destroy()
            self.assertIsNotNone(get_result())
            self.assertEqual(get_result()[0].id, "rule_executive")
            self.assertEqual(get_result()[1], "domain")

            # 2. Full _menu_add_to_rule -> 1 action staged -> pending bar shows "1 pending change"
            exec_rule = next(r for r in win.yaml_mgr.rules if r.id == "rule_executive")
            with patch.object(triage, "_prompt_rule_selection", return_value=(exec_rule, "domain")):
                triage._menu_add_to_rule()
            win.update()

            self.assertEqual(len(triage.staged_actions), 1)
            self.assertEqual(triage.staged_actions[0].match_mode, "domain")
            self.assertTrue(bool(triage.pending_bar.winfo_ismapped()))
            self.assertEqual(triage.lbl_pending_status.cget("text"), "1 pending change")

            # 3. Review dialog lists staged action & allows removing row
            rev_dlg, rev_tree = triage._build_review_staged_dialog()
            try:
                win.update()
                items = rev_tree.get_children()
                self.assertEqual(len(items), 1)
                vals = rev_tree.item(items[0], "values")
                self.assertIn("rep@acme.example", vals[0])
                self.assertEqual(vals[2], "Executive Board")
                self.assertIn("Whole domain (@acme.example)", vals[3])
                self.assertEqual(vals[4], exec_rule.target_folder)

                # Remove row inside Review dialog -> hides pending bar and closes dialog when empty
                rev_tree.selection_set(items[0])
                rm_btn = next(b for b in _find_buttons(rev_dlg) if b.cget("text") == "Remove Selected")
                rm_btn.invoke()
                win.update()
                self.assertEqual(len(triage.staged_actions), 0)
                self.assertFalse(bool(triage.pending_bar.winfo_ismapped()))
            finally:
                if rev_dlg.winfo_exists():
                    rev_dlg.destroy()

            # 4. Stage 1 email via Add to Rule... (This sender) + Apply -> saved to rules.yaml
            triage.tree_inbox.selection_set("MSG_ACME")
            triage._on_message_select_fast(None)
            with patch.object(triage, "_prompt_rule_selection", return_value=(exec_rule, "email")):
                triage._menu_add_to_rule()
            win.update()
            self.assertEqual(len(triage.staged_actions), 1)

            with patch("gui.triage_view.messagebox.askyesno", return_value=True), patch(
                "gui.triage_view.messagebox.showinfo"
            ), patch.object(triage.conflict_detector, "detect_conflicts", return_value=[]):
                triage._apply_all_staged()
            win.update()

            self.assertFalse(bool(triage.pending_bar.winfo_ismapped()))
            reloaded = YamlConfigManager(self.config_path)
            saved_exec = next(r for r in reloaded.rules if r.id == "rule_executive")
            self.assertIn("rep@acme.example", reloaded.get_all_emails_for_rule(saved_exec))

            # Clear button empties multiple pending changes and hides bar
            triage._stage_add_to_existing_rule(triage.messages[0], "rule_engineering")
            triage._stage_add_to_existing_rule(triage.messages[1], "rule_suppliers")
            win.update()
            self.assertEqual(triage.lbl_pending_status.cget("text"), "2 pending changes")
            triage.btn_pending_clear.invoke()
            win.update()
            self.assertEqual(len(triage.staged_actions), 0)
            self.assertFalse(bool(triage.pending_bar.winfo_ismapped()))
        finally:
            win.destroy()

    def test_move_now_uses_rule_picker_dialog_without_tree_rules(self):
        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.update()
            triage = win.tab_triage
            msg = triage.messages[0]
            triage.selected_message = msg
            suppliers_rule = next(r for r in win.yaml_mgr.rules if r.id == "rule_suppliers")

            with patch.object(triage, "_prompt_rule_selection", return_value=(suppliers_rule, "email")) as mock_pick, \
                 patch.object(triage.outlook, "move_message", return_value=True) as mock_move, \
                 patch("gui.triage_view.messagebox.showinfo"):
                triage._move_selected_now()

            mock_pick.assert_called_once()
            mock_move.assert_called_once_with(
                msg.entry_id,
                suppliers_rule.target_folder,
                win.yaml_mgr.stores["active_archive"].file_path,
            )
        finally:
            win.destroy()


if __name__ == "__main__":
    unittest.main()
