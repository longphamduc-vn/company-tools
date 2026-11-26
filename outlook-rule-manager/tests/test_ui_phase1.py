"""Tests for UI Phase 1 (1.1 - 1.4): group ID uniqueness, linked groups, simulation banner, and sync status."""
import os
import shutil
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from core.conflict_detector import ConflictDetector
from core.outlook_client import MockOutlookClient, WindowsOutlookClient
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager
from gui.conflict_dialog import ConflictDialog
from gui.main_window import MainWindow
from gui.rule_manager_view import RuleManagerView
from gui.triage_view import StagedAction
from tests.fakes import FakeNamespace, FakeStore


def _find_widgets_of_type(root: tk.Misc, cls):
    """Return all descendant widgets matching cls (breadth-first)."""
    found = []
    queue = list(root.winfo_children())
    while queue:
        w = queue.pop(0)
        if isinstance(w, cls):
            found.append(w)
        queue.extend(w.winfo_children())
    return found


def _rule_by_id(yaml_mgr: YamlConfigManager, rule_id: str):
    """Return the RuleConfig with the given ID."""
    return next(r for r in yaml_mgr.rules if r.id == rule_id)


class TestUiPhase1(unittest.TestCase):
    """Unit and Tkinter integration tests for UI_FIX_PLAN Phase UI-1."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        sample_config = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")
        shutil.copy2(sample_config, self.config_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_fake_real_client(self, yaml_mgr: YamlConfigManager) -> WindowsOutlookClient:
        store_path = yaml_mgr.stores["active_archive"].file_path
        archive_store = FakeStore("Archive 2025", store_path)
        default_store = FakeStore("Primary Mailbox", "", is_data_file=False)
        namespace = FakeNamespace(
            stores=[default_store, archive_store],
            default_store=default_store,
        )
        return WindowsOutlookClient(namespace=namespace)

    # ------------------------------------------------------------------
    # 1.1 Group ID uniqueness
    # ------------------------------------------------------------------
    def test_generate_group_id_uniqueness_and_after_delete(self):
        yaml_mgr = YamlConfigManager(self.config_path)
        self.assertEqual(yaml_mgr.generate_group_id("Vendor Group!"), "grp_vendor_group")
        self.assertEqual(yaml_mgr.generate_group_id("grp_Already"), "grp_already")
        self.assertEqual(yaml_mgr.generate_group_id("!!!"), "grp_new")

        root = tk.Tk()
        root.withdraw()
        try:
            sync_engine = SyncEngine(yaml_mgr, MockOutlookClient())
            view = RuleManagerView(root, yaml_mgr, sync_engine)
            view.pack()

            with patch("gui.rule_manager_view.simpledialog.askstring", return_value="Vendors"), patch.object(
                view, "_show_toast"
            ):
                view._add_group()
                view._add_group()
                view._add_group()

            self.assertIn("grp_vendors", yaml_mgr.groups)
            self.assertIn("grp_vendors_1", yaml_mgr.groups)
            self.assertIn("grp_vendors_2", yaml_mgr.groups)

            # Delete #2 ("grp_vendors_1"), then add another group with same name
            deleted = yaml_mgr.delete_group("grp_vendors_1")
            self.assertTrue(deleted)

            with patch("gui.rule_manager_view.simpledialog.askstring", return_value="Vendors"), patch.object(
                view, "_show_toast"
            ):
                view._add_group()

            # Must remain 3 distinct groups and not collide with grp_vendors_2
            self.assertIn("grp_vendors", yaml_mgr.groups)
            self.assertIn("grp_vendors_1", yaml_mgr.groups)
            self.assertIn("grp_vendors_2", yaml_mgr.groups)
            self.assertEqual(len([k for k in yaml_mgr.groups if k.startswith("grp_vendors")]), 3)
        finally:
            root.destroy()

    # ------------------------------------------------------------------
    # 1.2 Linked Groups editor in RuleManagerView
    # ------------------------------------------------------------------
    def test_rule_inspector_linked_groups_link_unlink_and_save_persistence(self):
        yaml_mgr = YamlConfigManager(self.config_path)
        sync_engine = SyncEngine(yaml_mgr, MockOutlookClient())

        root = tk.Tk()
        root.withdraw()
        try:
            view = RuleManagerView(root, yaml_mgr, sync_engine)
            view.pack()
            root.update_idletasks()

            view.tree.selection_set("rule_rule_executive")
            view._on_tree_select()

            self.assertEqual(view.lst_rule_groups.size(), 1)
            self.assertIn("Executive Board", view.lst_rule_groups.get(0))

            # Unlink removes from UI staging list but does NOT persist before Save
            view.lst_rule_groups.selection_set(0)
            view._unlink_group_from_rule()
            self.assertEqual(view.lst_rule_groups.size(), 0)
            self.assertEqual(_rule_by_id(yaml_mgr, "rule_executive").groups, ["executive"])
            self.assertEqual(
                _rule_by_id(YamlConfigManager(self.config_path), "rule_executive").groups,
                ["executive"],
            )

            # Link "Engineering SCADA Team" via modal dialog
            view._link_group_to_rule()
            root.update_idletasks()
            dialogs = [w for w in view.winfo_children() if isinstance(w, tk.Toplevel)]
            self.assertEqual(len(dialogs), 1)
            dlg = dialogs[0]

            lst_boxes = _find_widgets_of_type(dlg, tk.Listbox)
            self.assertEqual(len(lst_boxes), 1)
            modal_lst = lst_boxes[0]
            eng_idx = next(
                i for i in range(modal_lst.size()) if "Engineering SCADA Team" in modal_lst.get(i)
            )
            modal_lst.selection_set(eng_idx)

            link_btn = next(
                b for b in _find_widgets_of_type(dlg, ttk.Button) if b.cget("text") == "Link Selected"
            )
            link_btn.invoke()
            root.update_idletasks()

            self.assertEqual(view.lst_rule_groups.size(), 1)
            self.assertIn("Engineering SCADA Team", view.lst_rule_groups.get(0))
            # Still unsaved on disk until Save Rule to YAML
            self.assertEqual(
                _rule_by_id(YamlConfigManager(self.config_path), "rule_executive").groups,
                ["executive"],
            )

            with patch.object(view, "_show_toast"):
                view._save_rule_changes()

            reloaded = YamlConfigManager(self.config_path)
            self.assertEqual(_rule_by_id(reloaded, "rule_executive").groups, ["engineering"])
        finally:
            root.destroy()

    # ------------------------------------------------------------------
    # 1.3 Simulation banner, Retry Connection, and [SIMULATION] dialogs
    # ------------------------------------------------------------------
    def test_simulation_banner_visibility_and_retry_connection(self):
        mock_client = MockOutlookClient()
        win = MainWindow(self.config_path, outlook_client=mock_client)
        try:
            win.update()
            self.assertTrue(bool(win.sim_banner.winfo_ismapped()))
            self.assertIn("Simulated", win.btn_sync.cget("text"))
            self.assertIn("Simulated", win.lbl_mode.cget("text"))
            banner_labels = _find_widgets_of_type(win.sim_banner, tk.Label)
            self.assertTrue(any("SIMULATION MODE" in lbl.cget("text") for lbl in banner_labels))

            # Retry fails when COM still unavailable -> shows error, keeps banner mapped
            with patch("gui.main_window.get_outlook_client", return_value=MockOutlookClient()), patch(
                "gui.main_window.messagebox"
            ) as mock_mb:
                win._retry_outlook_connection()
                win.update()
                mock_mb.showerror.assert_called_once()
                self.assertTrue(bool(win.sim_banner.winfo_ismapped()))

            # Retry succeeds -> swaps outlook across MainWindow, SyncEngine, and tabs; hides banner
            real_client = self._make_fake_real_client(win.yaml_mgr)
            with patch("gui.main_window.get_outlook_client", return_value=real_client), patch(
                "gui.main_window.messagebox"
            ) as mock_mb:
                win._retry_outlook_connection()
                win.update()

            mock_mb.showinfo.assert_called_once()
            self.assertFalse(bool(win.sim_banner.winfo_ismapped()))
            self.assertEqual(win.btn_sync.cget("text"), "Sync to Outlook")
            self.assertIs(win.outlook, real_client)
            self.assertIs(win.sync_engine.outlook, real_client)
            self.assertIs(win.tab_triage.outlook, real_client)
            self.assertIs(win.tab_triage.conflict_detector.outlook, real_client)
            self.assertIs(win.tab_rollover.outlook, real_client)
            self.assertIs(win.tab_dryrun.outlook, real_client)
        finally:
            win.destroy()

        # Starting directly with real WindowsOutlookClient hides banner from the beginning
        yaml_mgr_real = YamlConfigManager(self.config_path)
        real_client_init = self._make_fake_real_client(yaml_mgr_real)
        win_real = MainWindow(self.config_path, outlook_client=real_client_init)
        try:
            win_real.update()
            self.assertFalse(bool(win_real.sim_banner.winfo_ismapped()))
            self.assertEqual(win_real.btn_sync.cget("text"), "Sync to Outlook")
        finally:
            win_real.destroy()

    def test_simulation_prefix_in_dialogs(self):
        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.update()

            # 1. MainWindow._sync_to_outlook
            with patch("gui.main_window.messagebox") as mock_mb:
                mock_mb.askyesno.return_value = True
                win._sync_to_outlook()
            self.assertTrue(mock_mb.showinfo.called)
            sync_msg = mock_mb.showinfo.call_args[0][1]
            self.assertTrue(sync_msg.startswith("[SIMULATION] No changes were made to Outlook."))

            # 2. TriageView._move_selected_now
            triage = win.tab_triage
            self.assertGreater(len(triage.messages), 0)
            triage.selected_message = triage.messages[0]
            exec_rule = _rule_by_id(win.yaml_mgr, "rule_executive")
            with patch.object(triage, "_prompt_rule_selection", return_value=(exec_rule, "email")), patch(
                "gui.triage_view.messagebox"
            ) as mock_triage_mb:
                mock_triage_mb.askyesno.return_value = True
                triage._move_selected_now()
            self.assertTrue(mock_triage_mb.showinfo.called)
            move_msg = mock_triage_mb.showinfo.call_args[0][1]
            self.assertTrue(move_msg.startswith("[SIMULATION] No changes were made to Outlook."))

            # 3. TriageView._apply_all_staged
            triage.staged_actions.append(
                StagedAction(
                    action_type="create_rule",
                    rule_name="Sim Staged Rule",
                    rule_id="",
                    target_folder="Vendor_Team\\Sim",
                    sender_email="sim@vendor.com",
                    sender_domain="@vendor.com",
                    match_mode="email",
                    message_id=triage.messages[0].entry_id,
                    subject=triage.messages[0].subject,
                )
            )
            with patch("gui.triage_view.messagebox") as mock_stage_mb:
                mock_stage_mb.askyesno.side_effect = (
                    lambda title, *a, **kw: False if "Conflict" in title else True
                )
                triage._apply_all_staged()
            self.assertTrue(mock_stage_mb.showinfo.called)
            stage_msg = mock_stage_mb.showinfo.call_args[0][1]
            self.assertTrue(stage_msg.startswith("[SIMULATION] No changes were made to Outlook."))

            # 4. RolloverView._execute_rollover (must point to an existing mock store path)
            rollover = win.tab_rollover
            rollover.ent_new_name.delete(0, tk.END)
            rollover.ent_new_name.insert(0, "longp Archive 2025")
            rollover.ent_new_path.delete(0, tk.END)
            rollover.ent_new_path.insert(0, "/mock/data/longp_Archive_2025.pst")
            with patch("gui.rollover_view.messagebox") as mock_roll_mb:
                mock_roll_mb.askyesno.return_value = True
                rollover._execute_rollover()
            self.assertTrue(mock_roll_mb.showinfo.called)
            roll_msg = mock_roll_mb.showinfo.call_args[0][1]
            self.assertTrue(roll_msg.startswith("[SIMULATION] No changes were made to Outlook."))

            # 5. ConflictDialog._execute_resolutions
            detector = ConflictDetector(win.yaml_mgr, win.outlook)
            with patch.object(ConflictDialog, "run_detection", return_value=None):
                dlg = ConflictDialog(win, detector, win.sync_engine)
            try:
                from core.conflict_detector import RuleConflict

                dlg.conflicts = [
                    RuleConflict(
                        conflict_type="NAME_COLLISION",
                        rule_name="Executive Board",
                        yaml_rule=_rule_by_id(win.yaml_mgr, "rule_executive"),
                        outlook_rule_info={"name": "Executive Board", "emails": [], "target_folder": ""},
                        description="Overlap",
                        suggested_action="OVERWRITE",
                    )
                ]
                with patch("gui.conflict_dialog.messagebox") as mock_conflict_mb:
                    mock_conflict_mb.askyesno.return_value = False
                    dlg._execute_resolutions()
                self.assertTrue(mock_conflict_mb.showinfo.called)
                conflict_msg = mock_conflict_mb.showinfo.call_args[0][1]
                self.assertTrue(conflict_msg.startswith("[SIMULATION] No changes were made to Outlook."))
            finally:
                if dlg.winfo_exists():
                    dlg.destroy()
        finally:
            win.destroy()

    # ------------------------------------------------------------------
    # 1.4 Unsynced changes counter, listeners, and MainWindow header badge
    # ------------------------------------------------------------------
    def test_unsynced_changes_counter_core_and_reload_behavior(self):
        yaml_mgr = YamlConfigManager(self.config_path)
        events = []
        yaml_mgr.add_change_listener(lambda: events.append((yaml_mgr.unsynced_changes, yaml_mgr.has_synced)))

        self.assertEqual(yaml_mgr.unsynced_changes, 0)
        self.assertFalse(yaml_mgr.has_synced)

        yaml_mgr.save()
        yaml_mgr.save()
        yaml_mgr.save()
        self.assertEqual(yaml_mgr.unsynced_changes, 3)
        self.assertEqual(len(events), 3)

        # load() preserves unsynced counter
        yaml_mgr.load()
        self.assertEqual(yaml_mgr.unsynced_changes, 3)
        self.assertFalse(yaml_mgr.has_synced)

        # Failed save() must NOT increment counter
        with patch("core.yaml_manager.os.replace", side_effect=PermissionError("locked")):
            with self.assertRaises(RuntimeError):
                yaml_mgr.save()
        self.assertEqual(yaml_mgr.unsynced_changes, 3)

        # Simulated sync does NOT reset counter
        mock_engine = SyncEngine(yaml_mgr, MockOutlookClient())
        ok_sim, _ = mock_engine.push_to_outlook()
        self.assertTrue(ok_sim)
        self.assertEqual(yaml_mgr.unsynced_changes, 3)
        self.assertFalse(yaml_mgr.has_synced)

        # Failing real sync (unknown store) does NOT reset counter
        bad_ns = FakeNamespace(stores=[FakeStore("Primary Mailbox", "", is_data_file=False)])
        fail_engine = SyncEngine(yaml_mgr, WindowsOutlookClient(namespace=bad_ns))
        ok_fail, _ = fail_engine.push_to_outlook()
        self.assertFalse(ok_fail)
        self.assertEqual(yaml_mgr.unsynced_changes, 3)
        self.assertFalse(yaml_mgr.has_synced)

        # Successful real sync resets counter and sets has_synced
        real_client = self._make_fake_real_client(yaml_mgr)
        real_engine = SyncEngine(yaml_mgr, real_client)
        ok_real, _ = real_engine.push_to_outlook()
        self.assertTrue(ok_real)
        self.assertEqual(yaml_mgr.unsynced_changes, 0)
        self.assertTrue(yaml_mgr.has_synced)

    def test_mainwindow_header_sync_status_and_button_highlight(self):
        yaml_pre = YamlConfigManager(self.config_path)
        real_client = self._make_fake_real_client(yaml_pre)

        win = MainWindow(self.config_path, outlook_client=real_client)
        try:
            win.update()
            self.assertIsInstance(win.lbl_sync_status, ttk.Label)
            self.assertEqual(win.lbl_sync_status.cget("text"), "Not synced this session")
            self.assertEqual(win.btn_sync.cget("style"), "Accent.TButton")

            # After 1 save -> badge updates & Sync button turns blue (SyncPending.TButton)
            win.yaml_mgr.save()
            win.update_idletasks()
            self.assertEqual(win.lbl_sync_status.cget("text"), "● 1 unsynced change(s)")
            self.assertEqual(win.btn_sync.cget("style"), "SyncPending.TButton")

            # Reload YAML preserves unsynced count
            with patch("gui.main_window.messagebox.showinfo"):
                win._reload_yaml()
            win.update_idletasks()
            self.assertEqual(win.lbl_sync_status.cget("text"), "● 1 unsynced change(s)")
            self.assertEqual(win.btn_sync.cget("style"), "SyncPending.TButton")

            # Real sync resets status -> "✓ Outlook in sync" & Accent.TButton
            with patch("gui.main_window.messagebox.askyesno", return_value=True), patch(
                "gui.main_window.messagebox.showinfo"
            ):
                win._sync_to_outlook()
            win.update_idletasks()
            self.assertEqual(win.lbl_sync_status.cget("text"), "✓ Outlook in sync")
            self.assertEqual(win.btn_sync.cget("style"), "Accent.TButton")

            # Subsequent save switches back from in-sync to unsynced
            win.yaml_mgr.save()
            win.update_idletasks()
            self.assertEqual(win.lbl_sync_status.cget("text"), "● 1 unsynced change(s)")
            self.assertEqual(win.btn_sync.cget("style"), "SyncPending.TButton")
        finally:
            win.destroy()

    def test_inspector_save_button_visible_and_scrollable_at_1120x720(self):
        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.geometry("1120x720")
            win.notebook.select(win.tab_rules)
            win.update()

            # Select rule -> Save Rule button must be mapped & inside window bounds
            win.tab_rules.tree.selection_set("rule_rule_executive")
            win.tab_rules._on_tree_select()
            win.update()

            btn_save_rule = win.tab_rules.btn_save_rule
            self.assertTrue(bool(btn_save_rule.winfo_ismapped()))
            self.assertLessEqual(
                btn_save_rule.winfo_rooty() + btn_save_rule.winfo_height(),
                win.winfo_rooty() + win.winfo_height(),
            )

            # Verify mousewheel helper scrolls rule canvas when shrunk to cause vertical overflow
            win.geometry("920x460")
            win.update()
            self.assertTrue(bool(btn_save_rule.winfo_ismapped()))
            self.assertLessEqual(
                btn_save_rule.winfo_rooty() + btn_save_rule.winfo_height(),
                win.winfo_rooty() + win.winfo_height(),
            )
            fake_wheel = type("WheelEvent", (), {"widget": win.tab_rules.lst_rule_groups, "delta": -120})()
            first_before, last_before = win.tab_rules.rule_scroll_canvas.yview()
            self.assertLess(last_before, 1.0)
            win.tab_rules._on_scrollable_mousewheel(fake_wheel)
            self.assertGreater(win.tab_rules.rule_scroll_canvas.yview()[0], first_before)

            # Select group -> Save Group button also mapped & visible inside window bounds
            win.geometry("1120x720")
            win.tab_rules.tree.selection_set("grp_executive")
            win.tab_rules._on_tree_select()
            win.update()

            btn_save_group = win.tab_rules.btn_save_group
            self.assertTrue(bool(btn_save_group.winfo_ismapped()))
            self.assertLessEqual(
                btn_save_group.winfo_rooty() + btn_save_group.winfo_height(),
                win.winfo_rooty() + win.winfo_height(),
            )
        finally:
            win.destroy()

    def test_rollover_resets_unsynced_changes_for_real_client(self):
        yaml_mgr = YamlConfigManager(self.config_path)
        old_path = yaml_mgr.stores["active_archive"].file_path
        new_path = r"D:\Outlook_Data\longp_Archive_2026.pst"
        archive_2025 = FakeStore("Archive 2025", old_path)
        archive_2026 = FakeStore("Archive 2026", new_path)
        default_store = FakeStore("Primary Mailbox", "", is_data_file=False)
        namespace = FakeNamespace(
            stores=[default_store, archive_2025, archive_2026],
            default_store=default_store,
        )
        engine = SyncEngine(yaml_mgr, WindowsOutlookClient(namespace=namespace))

        yaml_mgr.save()
        self.assertEqual(yaml_mgr.unsynced_changes, 1)

        ok, _ = engine.perform_rollover("Archive 2026", new_path)
        self.assertTrue(ok)
        self.assertEqual(yaml_mgr.unsynced_changes, 0)
        self.assertTrue(yaml_mgr.has_synced)

        # Simulated rollover must keep unsynced_changes > 0
        mock_engine = SyncEngine(yaml_mgr, MockOutlookClient())
        yaml_mgr.save()
        before_mock = yaml_mgr.unsynced_changes
        ok_mock, _ = mock_engine.perform_rollover("longp Archive 2025", "/mock/data/longp_Archive_2025.pst")
        self.assertTrue(ok_mock)
        self.assertGreater(yaml_mgr.unsynced_changes, before_mock)


if __name__ == "__main__":
    unittest.main()
