"""Tests for Simplify Phase S3: unified ttk style and compact window chrome."""
import os
import re
import shutil
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest

from core.outlook_client import MockOutlookClient
from gui import styles
from gui.main_window import MainWindow

GUI_DIR = os.path.join(os.path.dirname(__file__), "..", "gui")


def _find_widgets(root, cls):
    found = []
    stack = [root]
    while stack:
        w = stack.pop()
        if isinstance(w, cls):
            found.append(w)
        stack.extend(w.winfo_children())
    return found


class TestUiSimplifyPhaseS3(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        sample = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")
        shutil.copy2(sample, self.config_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_window(self):
        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        win.geometry("1120x720+0+0")
        win.update()
        return win

    def test_no_plain_tk_buttons_in_gui_sources(self):
        offenders = []
        for name in sorted(os.listdir(GUI_DIR)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(GUI_DIR, name), encoding="utf-8") as f:
                for lineno, line in enumerate(f, start=1):
                    if re.search(r"\btk\.Button\(", line):
                        offenders.append(f"{name}:{lineno}")
        self.assertEqual(offenders, [])

    def test_compact_chrome_fits_budget_in_simulation_mode(self):
        win = self._make_window()
        try:
            self.assertTrue(win.sim_banner.winfo_ismapped())
            content = win.tab_triage
            top = content.winfo_rooty() - win.winfo_rooty()
            bottom = (win.winfo_rooty() + win.winfo_height()) - (content.winfo_rooty() + content.winfo_height())
            # Header + banner + tab bar + footer (incl. separators/padding)
            self.assertLessEqual(top + bottom, 130, f"chrome uses {top + bottom}px (top={top}, bottom={bottom})")
            # Banner is a single compact line
            self.assertLessEqual(win.sim_banner.winfo_height(), 36)
            self.assertEqual(win.btn_retry_conn.cget("text"), "Retry")
        finally:
            win.destroy()

    def test_header_single_line_fits_and_footer_shows_engine_and_account(self):
        win = self._make_window()
        try:
            self.assertEqual(win.lbl_mode.cget("text"), "Simulated")
            # Full engine name + account live in the footer
            footer_text = win.lbl_footer.cget("text")
            self.assertIn(win.outlook.get_mode_name(), footer_text)
            self.assertIn(win.outlook.get_current_user_account(), footer_text)
            # Header fits: Sync button fully inside the window at 1120 px
            right_edge = win.btn_sync.winfo_rootx() + win.btn_sync.winfo_width()
            self.assertLessEqual(right_edge, win.winfo_rootx() + win.winfo_width())
            # Title and engine label share the same row container
            title = next(
                w for w in _find_widgets(win, ttk.Label) if w.cget("text") == "Outlook Rule Companion"
            )
            self.assertIs(title.master, win.lbl_mode.master)
            self.assertEqual(win.lbl_mode.pack_info()["side"], "left")
        finally:
            win.destroy()

    def test_tabs_named_inbox_and_rules(self):
        win = self._make_window()
        try:
            texts = [win.notebook.tab(t, "text") for t in win.notebook.tabs()]
            self.assertEqual(texts, ["Inbox", "Rules"])
        finally:
            win.destroy()

    def test_inbox_filters_are_ttk_toolbuttons_in_one_row_with_refresh(self):
        win = self._make_window()
        try:
            tv = win.tab_triage
            for btn in (tv.btn_f_all, tv.btn_f_untracked, tv.btn_f_staged):
                self.assertIsInstance(btn, ttk.Radiobutton)
                self.assertEqual(btn.cget("style"), "Filter.Toolbutton")
            self.assertIs(tv.btn_refresh.master, tv.btn_f_all.master)
            self.assertFalse(hasattr(tv, "lbl_account"))

            tv._set_filter("STAGED")
            self.assertEqual(tv.var_filter.get(), "STAGED")
            self.assertEqual(tv.active_filter, "STAGED")
            tv.btn_f_all.invoke()
            self.assertEqual(tv.active_filter, "ALL")
        finally:
            win.destroy()

    def test_delete_buttons_use_danger_style(self):
        win = self._make_window()
        try:
            danger_texts = {
                b.cget("text")
                for b in _find_widgets(win.tab_rules, ttk.Button)
                if b.cget("style") == "Danger.TButton"
            }
            self.assertTrue({"Delete Rule", "Delete Folder", "Delete Group", "Clear Entire Pool"} <= danger_texts)
            # Style is defined centrally
            self.assertEqual(str(ttk.Style(win).lookup("Danger.TButton", "foreground")), styles.DANGER)
        finally:
            win.destroy()

    def test_rollover_dialog_has_close_button_and_short_description(self):
        win = self._make_window()
        try:
            dlg, view = win._build_rollover_dialog()
            dlg.update()
            self.assertEqual(dlg.btn_close.cget("text"), "Close")
            self.assertTrue(dlg.btn_close.winfo_ismapped())
            labels = [w.cget("text") for w in _find_widgets(view, ttk.Label)]
            self.assertIn(
                "Re-point Companion rules to a new yearly PST that is already open in Outlook.", labels
            )
            dlg.btn_close.invoke()
            self.assertFalse(dlg.winfo_exists())
        finally:
            win.destroy()

    def test_rules_tip_wording(self):
        win = self._make_window()
        try:
            self.assertEqual(
                win.tab_rules._default_tip_text,
                "Tip: drag rules or folders to reorganize. Right-click for more actions.",
            )
        finally:
            win.destroy()


if __name__ == "__main__":
    unittest.main()
