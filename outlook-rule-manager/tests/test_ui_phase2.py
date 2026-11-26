"""Tests for UI Phase 2 (2.1 - 2.4): Subject Keywords, Footer, Rollover View, and Compiled Quota Preview."""
import os
import shutil
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from core.models import MANAGED_PREFIX, RuleConfig, StoreConfig
from core.outlook_client import MockOutlookClient, WindowsOutlookClient
from core.rollover_suggest import suggest_rollover_target
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager
from gui.main_window import MainWindow
from gui.rule_manager_view import RuleManagerView
from tests.fakes import FakeNamespace, FakeStore


def _is_descendant(widget: tk.Misc, ancestor: tk.Misc) -> bool:
    """Return True if widget is inside ancestor's widget hierarchy."""
    curr = widget
    while curr is not None:
        if curr is ancestor:
            return True
        curr = getattr(curr, "master", None)
    return False


class TestUiPhase2(unittest.TestCase):
    """Unit and Tkinter integration tests for UI_FIX_PLAN Phase UI-2."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        sample_config = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")
        shutil.copy2(sample_config, self.config_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_fake_real_client(self, extra_stores=None) -> WindowsOutlookClient:
        yaml_mgr = YamlConfigManager(self.config_path)
        archive_path = yaml_mgr.stores["active_archive"].file_path
        archive_store = FakeStore("Archive 2025", archive_path)
        default_store = FakeStore("Primary Mailbox", "", is_data_file=False)
        stores = [default_store, archive_store] + list(extra_stores or [])
        ns = FakeNamespace(stores=stores, default_store=default_store)
        return WindowsOutlookClient(namespace=ns)

    # ------------------------------------------------------------------
    # 2.1 Subject Keywords UI, Normalization, Bulk Mode, and Test Match
    # ------------------------------------------------------------------
    def test_normalize_keywords_and_gui_subject_keywords_visual_bulk_and_test_match(self):
        self.assertEqual(
            YamlConfigManager.normalize_keywords(["SCADA", " scada ", "", "Alarm"]),
            ["SCADA", "Alarm"],
        )

        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.geometry("1120x720")
            win.notebook.select(win.tab_rules)
            win.update()

            view: RuleManagerView = win.tab_rules
            view.tree.selection_set("rule_rule_executive")
            view._on_tree_select()
            win.update()

            # Subject Keywords widgets sit inside scrollable canvas container (rule_scroll_canvas)
            self.assertTrue(_is_descendant(view.txt_keywords, view.rule_scroll_canvas))
            card_cond = view.txt_keywords.master
            while card_cond is not None and not isinstance(card_cond, tk.LabelFrame):
                card_cond = card_cond.master
            self.assertIsNotNone(card_cond)
            self.assertEqual(card_cond.cget("text"), "Filter Conditions")

            # Add keywords in single-mode inspector: duplicates & blanks dropped, first spelling kept
            view.txt_keywords.delete("1.0", tk.END)
            view.txt_keywords.insert(tk.END, "SCADA\n scada \n  \nAlarm\n")
            view._on_rule_text_changed()

            with patch.object(view, "_show_toast"):
                view._save_rule_changes()

            reloaded = YamlConfigManager(self.config_path)
            saved_rule = next(r for r in reloaded.rules if r.id == "rule_executive")
            self.assertEqual(saved_rule.subject_keywords, ["SCADA", "Alarm"])

            # Test Match supports optional Subject entry
            view.ent_test_match.delete(0, tk.END)
            view.ent_test_subject.delete(0, tk.END)
            view.ent_test_subject.insert(0, "URGENT: alarm triggered")
            view._test_rule_match()
            self.assertIn("MATCH!", view.lbl_test_result.cget("text"))
            self.assertIn("Alarm", view.lbl_test_result.cget("text"))

            view.ent_test_subject.delete(0, tk.END)
            view.ent_test_subject.insert(0, "Weekly lunch menu")
            view._test_rule_match()
            self.assertEqual(view.lbl_test_result.cget("text"), "NO MATCH")

            # Replace keywords & verify roundtrip deduplication
            self.assertIn("SCADA", view.txt_keywords.get("1.0", tk.END))
            view.txt_keywords.delete("1.0", tk.END)
            view.txt_keywords.insert(tk.END, "  PLC  \n\nplc\nBreaker\n")
            view._on_rule_text_changed()
            with patch.object(view, "_show_toast"):
                view._save_rule_changes()

            reloaded2 = YamlConfigManager(self.config_path)
            saved_rule2 = next(r for r in reloaded2.rules if r.id == "rule_executive")
            self.assertEqual(saved_rule2.subject_keywords, ["PLC", "Breaker"])

            # Save button still visible at 1120x720 with keywords inside rule_cond_body
            win.update()
            self.assertTrue(bool(view.btn_save_rule.winfo_ismapped()))
            self.assertLessEqual(
                view.btn_save_rule.winfo_rooty() + view.btn_save_rule.winfo_height(),
                win.winfo_rooty() + win.winfo_height(),
            )
        finally:
            win.destroy()

    # ------------------------------------------------------------------
    # 2.2 Footer visibility (even with simulation banner) and updates
    # ------------------------------------------------------------------
    def test_footer_visible_with_simulation_banner_and_refreshes(self):
        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.geometry("1120x720")
            win.update()

            self.assertTrue(bool(win.sim_banner.winfo_ismapped()))
            self.assertTrue(bool(win.footer.winfo_ismapped()))
            self.assertLessEqual(
                win.footer.winfo_rooty() + win.footer.winfo_height(),
                win.winfo_rooty() + win.winfo_height(),
            )
            self.assertIn("Active archive: Archive 2025", win.lbl_footer.cget("text"))
            self.assertEqual(win.lbl_footer_status.cget("text"), "NOT found in Outlook")

            # Connecting real Outlook store updates footer status -> found in Outlook
            extra_2026 = FakeStore("Archive 2026", r"D:\Outlook_Data\longp_Archive_2026.pst")
            real_client = self._make_fake_real_client(extra_stores=[extra_2026])
            with patch("gui.main_window.get_outlook_client", return_value=real_client), patch(
                "gui.main_window.messagebox"
            ):
                win._retry_outlook_connection()
                win.update()

            self.assertEqual(win.lbl_footer_status.cget("text"), "found in Outlook")

            # Successful rollover via dialog refreshes footer to new store and closes dialog
            roll_dlg, roll_view = win._build_rollover_dialog()
            try:
                roll_view.ent_new_name.delete(0, tk.END)
                roll_view.ent_new_name.insert(0, "Archive 2026")
                roll_view.ent_new_path.delete(0, tk.END)
                roll_view.ent_new_path.insert(0, r"D:\Outlook_Data\longp_Archive_2026.pst")
                with patch("gui.rollover_view.messagebox") as mock_mb:
                    mock_mb.askyesno.return_value = True
                    roll_view._execute_rollover()
            finally:
                if roll_dlg.winfo_exists():
                    roll_dlg.destroy()
            win.update_idletasks()
            self.assertIn("Active archive: Archive 2026", win.lbl_footer.cget("text"))
            self.assertEqual(win.lbl_footer_status.cget("text"), "found in Outlook")

            # Reload YAML updates footer from disk
            ext_mgr = YamlConfigManager(self.config_path)
            ext_mgr.stores["active_archive"] = StoreConfig(
                id="active_archive", name="Reloaded Store", file_path=r"D:\Missing\Reloaded.pst"
            )
            ext_mgr.save()
            with patch("gui.main_window.messagebox.showinfo"):
                win._reload_yaml()
            self.assertIn("Active archive: Reloaded Store", win.lbl_footer.cget("text"))
            self.assertEqual(win.lbl_footer_status.cget("text"), "NOT found in Outlook")
        finally:
            win.destroy()

    # ------------------------------------------------------------------
    # 2.3 Rollover suggestions, user-input preservation, Health Status & button state
    # ------------------------------------------------------------------
    def test_rollover_suggest_helper_and_view_state(self):
        self.assertEqual(
            suggest_rollover_target("Archive 2025", r"D:\Data\x_2025.pst"),
            ("Archive 2026", r"D:\Data\x_2026.pst"),
        )
        self.assertEqual(suggest_rollover_target("Main Archive", r"D:\Data\x.pst"), ("", ""))
        self.assertEqual(
            suggest_rollover_target("Archive 2025", r"D:\2020_folder\plain.pst"),
            ("Archive 2026", ""),
        )
        self.assertEqual(
            suggest_rollover_target("longp Archive 2025", "/mock/data/longp_Archive_2025.pst"),
            ("longp Archive 2026", "/mock/data/longp_Archive_2026.pst"),
        )

        # Prepare YAML store without year to verify no hardcoded ..._Archive_2025 fallback
        yaml_mgr = YamlConfigManager(self.config_path)
        yaml_mgr.stores["active_archive"].name = "Company Archive"
        yaml_mgr.stores["active_archive"].file_path = os.path.join(self.temp_dir, "missing_archive.pst")
        yaml_mgr.save()

        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        roll_dlg = None
        try:
            roll_dlg, roll = win._build_rollover_dialog()
            # Missing on disk -> [MISSING] and no hardcoded C:\Outlook_Data or _Archive_2025
            self.assertIn("[MISSING]", roll.lbl_cur_size.cget("text"))
            self.assertNotIn("File managed by Outlook", roll.lbl_cur_size.cget("text"))
            self.assertEqual(roll.ent_new_name.get(), "")
            self.assertEqual(roll.ent_new_path.get(), "")
            self.assertIn("disabled", roll.btn_rollover.state())

            # Create file on disk but NOT open in Outlook -> [NOT MOUNTED]
            with open(yaml_mgr.stores["active_archive"].file_path, "wb") as f:
                f.write(b"pst")
            roll.refresh_view()
            self.assertIn("[NOT MOUNTED]", roll.lbl_cur_size.cget("text"))

            # Unknown path keeps Execute disabled; mounted mock store enables Execute
            roll.ent_new_path.delete(0, tk.END)
            roll.ent_new_path.insert(0, r"D:\Unknown\nonexistent.pst")
            self.assertIn("disabled", roll.btn_rollover.state())

            roll.ent_new_name.delete(0, tk.END)
            roll.ent_new_name.insert(0, "User Custom Name")
            roll.ent_new_path.delete(0, tk.END)
            roll.ent_new_path.insert(0, "/mock/data/longp_Archive_2025.pst")
            self.assertNotIn("disabled", roll.btn_rollover.state())

            # Tab-switch refresh must NOT overwrite user-edited inputs
            roll.refresh_view()
            self.assertEqual(roll.ent_new_name.get(), "User Custom Name")
            self.assertEqual(roll.ent_new_path.get(), "/mock/data/longp_Archive_2025.pst")

            # Selecting same path as current active archive disables Execute
            mock_active_path = "/mock/data/longp_Archive_2024.pst"
            win.yaml_mgr.stores["active_archive"].file_path = mock_active_path
            roll.ent_new_path.delete(0, tk.END)
            roll.ent_new_path.insert(0, mock_active_path)
            self.assertIn("disabled", roll.btn_rollover.state())
        finally:
            if roll_dlg is not None and roll_dlg.winfo_exists():
                roll_dlg.destroy()
            win.destroy()

    # ------------------------------------------------------------------
    # 2.4 Compiled preview (shared with push_to_outlook) and live Quota label
    # ------------------------------------------------------------------
    def test_preview_compiled_rules_and_live_quota_updates(self):
        yaml_mgr = YamlConfigManager(self.config_path)
        big_rule = RuleConfig(
            id="rule_big",
            name="Big Vendor",
            enabled=True,
            emails=[f"user{i:02d}@vendor.com" for i in range(41)],
            domains=["@vendor.com"],
            subject_keywords=["Quote"],
            target_store="active_archive",
            target_folder="Vendors\\Big",
        )
        yaml_mgr.rules = [big_rule]
        yaml_mgr.save()

        mock_client = MockOutlookClient()
        engine = SyncEngine(yaml_mgr, mock_client)

        preview_names = engine.preview_compiled_rules(big_rule)
        self.assertEqual(
            preview_names,
            [
                f"{MANAGED_PREFIX}Big Vendor (Part 1)",
                f"{MANAGED_PREFIX}Big Vendor (Part 2)",
                f"{MANAGED_PREFIX}Big Vendor (Domains)",
                f"{MANAGED_PREFIX}Big Vendor (Keywords)",
            ],
        )

        # Verify push_to_outlook uses exact same compile names
        ok, _ = engine.push_to_outlook()
        self.assertTrue(ok)
        created_managed = [r["name"] for r in mock_client.get_native_rules() if r["name"].startswith(MANAGED_PREFIX)]
        self.assertEqual(created_managed, preview_names)

        # GUI quota updates immediately on Link/Unlink and after Save + empty/no-folder warnings
        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.notebook.select(win.tab_rules)
            win.update()
            view: RuleManagerView = win.tab_rules

            # Check initial quota display for big_rule (41 emails, 1 domain, 1 keyword -> 4 native rules)
            view.tree.selection_set("rule_rule_big")
            view._on_tree_select()
            win.update()
            quota_txt = view.lbl_quota.cget("text")
            self.assertIn("41 senders, 1 domain, 1 keyword → 4 native rules", quota_txt)
            self.assertIn("Big Vendor (Keywords)", view.lbl_quota_subrules.cget("text"))

            # Link group "executive" via modal dialog -> immediately updates to 43 senders BEFORE Save
            view._link_group_to_rule()
            win.update_idletasks()
            dlg = next(w for w in view.winfo_children() if isinstance(w, tk.Toplevel))
            modal_lst = next(w for w in dlg.winfo_children() if isinstance(w, tk.Listbox))
            exec_idx = next(i for i in range(modal_lst.size()) if "Executive Board" in modal_lst.get(i))
            modal_lst.selection_set(exec_idx)
            btn_bar = next(w for w in dlg.winfo_children() if isinstance(w, ttk.Frame))
            link_btn = next(b for b in btn_bar.winfo_children() if isinstance(b, ttk.Button) and b.cget("text") == "Link Selected")
            link_btn.invoke()
            win.update_idletasks()
            self.assertIn("43 senders, 1 domain, 1 keyword → 4 native rules", view.lbl_quota.cget("text"))

            # Unlink via UI method -> drops back to 41 senders immediately
            view.lst_rule_groups.selection_set(0)
            view._unlink_group_from_rule()
            self.assertIn("41 senders, 1 domain, 1 keyword → 4 native rules", view.lbl_quota.cget("text"))

            # Remove keyword and Save -> drops to 0 keywords and 3 native rules
            view.txt_keywords.delete("1.0", tk.END)
            view._on_rule_text_changed()
            with patch.object(view, "_show_toast"):
                view._save_rule_changes()
            self.assertIn("41 senders, 1 domain, 0 keywords → 3 native rules", view.lbl_quota.cget("text"))

            # Rule without conditions -> warning
            empty_rule = RuleConfig(
                id="rule_empty",
                name="Empty Rule",
                enabled=True,
                target_folder="Vendors\\Empty",
            )
            win.yaml_mgr.rules.append(empty_rule)
            win.yaml_mgr.save()
            view.refresh_all()
            view.tree.selection_set("rule_rule_empty")
            view._on_tree_select()
            self.assertIn("No conditions", view.lbl_quota.cget("text"))

            # Rule with condition but empty target_folder -> warning
            nofold_rule = RuleConfig(
                id="rule_nofold",
                name="No Folder Rule",
                enabled=True,
                emails=["a@b.com"],
                target_folder="",
            )
            win.yaml_mgr.rules.append(nofold_rule)
            win.yaml_mgr.save()
            view.refresh_all()
            view.tree.selection_set("rule_rule_nofold")
            view._on_tree_select()
            self.assertIn("No target folder", view.lbl_quota.cget("text"))
        finally:
            win.destroy()


if __name__ == "__main__":
    unittest.main()
