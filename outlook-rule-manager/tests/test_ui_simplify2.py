"""Tests for UI Simplify Phase S2 + S1 polish: columns fit, 2 tabs, rollover modal, single-mode inspector."""
import os
import shutil
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from core.models import RuleConfig
from core.outlook_client import MockOutlookClient, WindowsOutlookClient
from core.yaml_manager import YamlConfigManager
from gui.main_window import MainWindow
from tests.fakes import FakeNamespace, FakeStore


def _find_widgets(root: tk.Misc, widget_cls):
    found = []
    queue = list(root.winfo_children())
    while queue:
        w = queue.pop(0)
        if isinstance(w, widget_cls):
            found.append(w)
        queue.extend(w.winfo_children())
    return found


class TestUiSimplifyPhaseS2(unittest.TestCase):
    """Integration tests for UI_SIMPLIFY_PLAN Phase S2 and S1 polish items."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        sample_config = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")
        shutil.copy2(sample_config, self.config_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_fake_real_client(self, extra_stores=None):
        yaml_mgr = YamlConfigManager(self.config_path)
        active = yaml_mgr.stores["active_archive"]
        default_store = FakeStore("Primary Mailbox", "", is_data_file=False)
        stores = [
            default_store,
            FakeStore(active.name, active.file_path),
        ]
        if extra_stores:
            stores.extend(extra_stores)
        ns = FakeNamespace(stores=stores, default_store=default_store)
        return WindowsOutlookClient(namespace=ns)

    def test_triage_columns_fit_panel_and_pending_bar_no_emdash(self):
        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.geometry("1120x720")
            win.update()
            triage = win.tab_triage

            cols = list(triage.tree_inbox["columns"])
            self.assertEqual(cols, ["Sender", "Subject", "WillGoTo"])
            self.assertNotIn("Status", cols)

            total_width = 0
            for col in cols:
                col_cfg = triage.tree_inbox.column(col)
                self.assertTrue(bool(col_cfg["stretch"]), f"Column {col} should stretch")
                total_width += int(col_cfg["width"])
            tree_width = triage.tree_inbox.winfo_width()
            self.assertLessEqual(
                total_width,
                tree_width + 2,
                f"Columns ({total_width}px) exceed tree width ({tree_width}px) at 1120x720",
            )

            # Pending bar shows clean count without trailing " —"
            exec_rule = next(r for r in win.yaml_mgr.rules if r.id == "rule_executive")
            triage._stage_add_to_existing_rule(triage.messages[0], exec_rule.id, match_mode="email")
            win.update()
            self.assertEqual(triage.lbl_pending_status.cget("text"), "1 pending change")
            self.assertFalse(triage.lbl_pending_status.cget("text").endswith("—"))
        finally:
            win.destroy()

    def test_two_tabs_dryrun_removed_and_rollover_dialog_workflow(self):
        repo_gui_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gui"))
        self.assertFalse(os.path.exists(os.path.join(repo_gui_dir, "dryrun_view.py")))

        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        roll_dlg = None
        try:
            win.geometry("1120x720")
            win.update()

            # Only 2 tabs remain: Inbox Triage and Rules & Groups
            tab_ids = win.notebook.tabs()
            self.assertEqual(len(tab_ids), 2)
            tab_texts = [win.notebook.tab(tid, "text") for tid in tab_ids]
            self.assertEqual(tab_texts, [" Inbox Triage ", " Rules & Groups "])
            self.assertFalse(hasattr(win, "tab_dryrun"))
            self.assertFalse(hasattr(win, "tab_rollover"))

            # Yearly Rollover... button is in header next to Check Rule Conflicts
            self.assertTrue(bool(win.btn_rollover.winfo_ismapped()))
            self.assertEqual(win.btn_rollover.cget("text"), "Yearly Rollover...")
            self.assertIs(win.btn_rollover.master, win.btn_conflicts.master)

            # Reconnect Outlook -> subsequent Yearly Rollover dialog receives the new client
            extra_2026 = FakeStore("Archive 2026", r"D:\Outlook_Data\longp_Archive_2026.pst")
            real_client = self._make_fake_real_client(extra_stores=[extra_2026])
            with patch("gui.main_window.get_outlook_client", return_value=real_client), patch(
                "gui.main_window.messagebox"
            ):
                win._retry_outlook_connection()
                win.update()

            roll_dlg, roll_view = win._build_rollover_dialog()
            self.assertIs(roll_view.outlook, real_client)
            roll_view.ent_new_name.delete(0, tk.END)
            roll_view.ent_new_name.insert(0, "Archive 2026")
            roll_view.ent_new_path.delete(0, tk.END)
            roll_view.ent_new_path.insert(0, r"D:\Outlook_Data\longp_Archive_2026.pst")
            with patch("gui.rollover_view.messagebox") as mock_mb:
                mock_mb.askyesno.return_value = True
                roll_view._execute_rollover()

            self.assertFalse(roll_dlg.winfo_exists())
            win.update()
            self.assertIn("Active archive: Archive 2026", win.lbl_footer.cget("text"))
            self.assertEqual(win.lbl_footer_status.cget("text"), "found in Outlook")
        finally:
            if roll_dlg is not None and roll_dlg.winfo_exists():
                roll_dlg.destroy()
            win.destroy()

    def test_rules_tab_single_row_toolbar_and_single_mode_inspector_geometry(self):
        yaml_mgr = YamlConfigManager(self.config_path)
        yaml_mgr.rules.append(
            RuleConfig(
                id="rule_big",
                name="Big Vendor",
                enabled=True,
                emails=[f"user{i:02d}@vendor.com" for i in range(41)],
                domains=["@vendor.com"],
                subject_keywords=["Invoice"],
                target_folder="Vendors\\Big",
            )
        )
        yaml_mgr.save()

        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.geometry("1120x720")
            win.notebook.select(win.tab_rules)
            win.update()

            view = win.tab_rules

            # Toolbar is a single row with New menubutton, Expand, Collapse, and Filter:
            self.assertEqual(view.mb_new.cget("text"), "New")
            menu_labels = [
                view.menu_new.entrycget(i, "label")
                for i in range(view.menu_new.index("end") + 1)
            ]
            self.assertEqual(menu_labels, ["Rule", "Folder", "Subfolder", "Group"])

            toolbar_frame = view.mb_new.master
            self.assertIs(view.ent_search.master, toolbar_frame)
            toolbar_btns = [b.cget("text") for b in _find_widgets(toolbar_frame, ttk.Button)]
            self.assertEqual(toolbar_btns, ["Expand", "Collapse"])

            # Mode-switch widgets & Visual chip listboxes are gone
            for old_attr in (
                "condition_mode",
                "btn_mode_visual",
                "btn_mode_bulk",
                "lst_emails",
                "lst_domains",
                "lst_keywords",
                "ent_add_email",
                "ent_add_domain",
                "ent_add_keyword",
                "txt_bulk_emails",
                "txt_bulk_domains",
                "txt_bulk_keywords",
                "_set_condition_mode",
            ):
                self.assertFalse(hasattr(view, old_attr), f"{old_attr} should be removed")

            # Select rule_big (41 emails, 1 domain, 1 keyword)
            view.tree.selection_set("rule_rule_big")
            view._on_tree_select()
            win.update()

            self.assertEqual(view.lbl_rule_emails_hdr.cget("text"), "Emails (41)")
            self.assertEqual(view.lbl_rule_domains_hdr.cget("text"), "Domains (1)")
            self.assertEqual(view.lbl_rule_keywords_hdr.cget("text"), "Subject Keywords (1)")

            # At 1120x720 without scrolling outer canvas, >= 4 lines of Emails and Save button are visible
            self.assertEqual(view.rule_scroll_canvas.yview()[0], 0.0)
            canvas_top = view.rule_scroll_canvas.winfo_rooty()
            canvas_bottom = canvas_top + view.rule_scroll_canvas.winfo_height()
            visible_email_lines = 0
            for line_no in range(1, 7):
                bbox = view.txt_emails.dlineinfo(f"{line_no}.0")
                if bbox is not None:
                    line_top = view.txt_emails.winfo_rooty() + bbox[1]
                    line_bottom = line_top + bbox[3]
                    if line_top >= canvas_top and line_bottom <= canvas_bottom:
                        visible_email_lines += 1
            self.assertGreaterEqual(visible_email_lines, 4)

            self.assertTrue(bool(view.btn_save_rule.winfo_ismapped()))
            self.assertLessEqual(
                view.btn_save_rule.winfo_rooty() + view.btn_save_rule.winfo_height(),
                win.winfo_rooty() + win.winfo_height(),
            )

            # Live count labels update on edit & mark form dirty
            view.txt_emails.insert(tk.END, "\nextra_one@big.com\n")
            view.txt_domains.insert(tk.END, "\n@extra-big.com\n")
            view.txt_keywords.insert(tk.END, "\nURGENT\n")
            view._on_rule_text_changed()

            self.assertEqual(view.lbl_rule_emails_hdr.cget("text"), "Emails (42)")
            self.assertEqual(view.lbl_rule_domains_hdr.cget("text"), "Domains (2)")
            self.assertEqual(view.lbl_rule_keywords_hdr.cget("text"), "Subject Keywords (2)")
            self.assertTrue(view.has_unsaved_changes())
            self.assertEqual(view.btn_save_rule.cget("text"), "Save Changes ●")

            # CSV import appends deduplicated emails and updates live count
            csv_path = os.path.join(self.temp_dir, "more.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("email\nextra_one@big.com\nimported_new@big.com\n")
            with patch("gui.rule_manager_view.filedialog.askopenfilename", return_value=csv_path), patch(
                "gui.rule_manager_view.messagebox"
            ), patch.object(view, "_show_toast"):
                view._import_addresses_to_rule()
            self.assertEqual(view.lbl_rule_emails_hdr.cget("text"), "Emails (43)")
            self.assertIn("imported_new@big.com", view.txt_emails.get("1.0", tk.END))
        finally:
            win.destroy()
