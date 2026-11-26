"""Tests for UI Phase 3 (3.1 - 3.6) plus quota colors, exact domain test match, and footer colors."""
import os
import shutil
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from core.models import RuleConfig
from core.outlook_client import MockOutlookClient, WindowsOutlookClient
from core.sync_engine import SyncEngine, match_email_domain
from core.yaml_manager import YamlConfigManager
from gui.main_window import MainWindow
from gui.rule_manager_view import RuleManagerView
from tests.fakes import FakeNamespace, FakeStore


def _find_widgets(root: tk.Misc, cls):
    """Collect all descendant widgets of type cls."""
    found = []
    queue = list(root.winfo_children())
    while queue:
        w = queue.pop(0)
        if isinstance(w, cls):
            found.append(w)
        queue.extend(w.winfo_children())
    return found


def _collect_tree_texts(tree: ttk.Treeview, item: str = "") -> list:
    """Recursively collect display text of all nodes in a ttk.Treeview."""
    texts = []
    for child in tree.get_children(item):
        texts.append(tree.item(child, "text"))
        texts.extend(_collect_tree_texts(tree, child))
    return texts


class TestUiPhase3(unittest.TestCase):
    """Unit and Tkinter integration tests for UI_FIX_PLAN Phase UI-3."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "rules.yaml")
        sample_config = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")
        shutil.copy2(sample_config, self.config_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_fake_real_client(self) -> WindowsOutlookClient:
        yaml_mgr = YamlConfigManager(self.config_path)
        archive_path = yaml_mgr.stores["active_archive"].file_path
        archive_store = FakeStore("Archive 2025", archive_path)
        default_store = FakeStore("Primary Mailbox", "", is_data_file=False)
        ns = FakeNamespace(stores=[default_store, archive_store], default_store=default_store)
        return WindowsOutlookClient(namespace=ns)

    # ------------------------------------------------------------------
    # 3.1 + 3.4 Triage layout, drop zone, assign button, conflicts on header
    # C. Red footer status when NOT found in Outlook
    # ------------------------------------------------------------------
    def test_triage_layout_header_conflicts_and_footer_colors(self):
        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.geometry("1120x720")
            win.update()

            # Check Rule Conflicts moved to MainWindow header next to Sync
            self.assertEqual(win.btn_conflicts.cget("text"), "Check Rule Conflicts")
            self.assertIs(win.btn_conflicts.master, win.btn_sync.master)
            triage_btn_texts = [b.cget("text") for b in _find_widgets(win.tab_triage, ttk.Button)]
            self.assertNotIn("Check Rule Conflicts", triage_btn_texts)

            # Footer red status in Mock mode (store not in mock stores)
            self.assertEqual(win.lbl_footer_status.cget("text"), "NOT found in Outlook")
            self.assertEqual(str(win.lbl_footer_status.cget("foreground")), "#dc2626")

            # Triage paned weights (3, 5, 3) & column widths & widgets
            triage = win.tab_triage
            paned = next(w for w in _find_widgets(triage, ttk.PanedWindow))
            self.assertEqual(paned.pane(triage.frame_left, "weight"), 3)
            self.assertEqual(paned.pane(triage.frame_center, "weight"), 5)
            self.assertEqual(paned.pane(triage.frame_right, "weight"), 3)
            self.assertGreaterEqual(int(triage.tree_rules.column("#0", "width")), 220)

            # Drop zone wording without "Instant staging (0ms)"
            drop_labels = _find_widgets(triage.drop_new_zone, tk.Label)
            self.assertEqual(len(drop_labels), 1)
            self.assertEqual(drop_labels[0].cget("text"), "Drop an email here to create a new rule")

            # Assign button has no duplicate arrow in text; Search label precedes ent_search
            self.assertEqual(triage.mb_assign_rule.cget("text"), "Assign to Rule...")
            search_lbl = next(
                lbl for lbl in _find_widgets(triage.frame_center, tk.Label) if lbl.cget("text") == "Search:"
            )
            self.assertLess(search_lbl.winfo_rootx(), triage.ent_search.winfo_rootx())
        finally:
            win.destroy()

        # Footer green status when Outlook store exists
        win_real = MainWindow(self.config_path, outlook_client=self._make_fake_real_client())
        try:
            win_real.update()
            self.assertEqual(win_real.lbl_footer_status.cget("text"), "found in Outlook")
            self.assertEqual(str(win_real.lbl_footer_status.cget("foreground")), "#16a34a")
        finally:
            win_real.destroy()

    # ------------------------------------------------------------------
    # 3.2, 3.3, 3.4, 3.5 Tree labels, pool count, bottom tip bar, Enabled checkbox
    # ------------------------------------------------------------------
    def test_tree_labels_unclassified_count_tip_bar_and_enabled_checkbox(self):
        yaml_mgr = YamlConfigManager(self.config_path)
        yaml_mgr.rules[0].enabled = False  # disable Executive Board
        yaml_mgr.save()

        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.geometry("1120x720")
            win.notebook.select(win.tab_rules)
            win.update()

            triage_texts = _collect_tree_texts(win.tab_triage.tree_rules)
            rules_texts = _collect_tree_texts(win.tab_rules.tree)

            for txt in triage_texts + rules_texts:
                self.assertNotIn("[L1]", txt)
                self.assertNotIn("[L2]", txt)
                self.assertNotIn("[ON]", txt)
                self.assertNotIn("[OFF]", txt)
                self.assertNotIn("HIERARCHICAL", txt)
                self.assertNotIn("NAVIGATOR", txt)

            self.assertIn("Folders & Rules", triage_texts)
            self.assertIn("Folders & Rules", rules_texts)
            self.assertIn("Shared Address Groups", rules_texts)

            # Disabled rule styling + suffix in both trees
            self.assertIn("(disabled)", win.tab_rules.tree.item("rule_rule_executive", "text"))
            self.assertIn("rule_disabled", win.tab_rules.tree.item("rule_rule_executive", "tags"))
            self.assertIn("(disabled)", win.tab_triage.tree_rules.item("rule_rule_executive", "text"))
            self.assertIn("rule_disabled", win.tab_triage.tree_rules.item("rule_rule_executive", "tags"))

            # [Unclassified] rule counts unclassified_pool addresses (rules_sample has 1 address)
            self.assertEqual(win.tab_rules.tree.item("rule_rule_unclassified", "values")[0], "1 senders")
            unclass_children = [
                win.tab_triage.tree_rules.item(c, "text").strip()
                for c in win.tab_triage.tree_rules.get_children("rule_rule_unclassified")
            ]
            self.assertIn("former.contractor@vendor.com", unclass_children)

            # Left panel duplicate buttons removed from frame_left; kept in inspector footer
            left_btns = [b.cget("text") for b in _find_widgets(win.tab_rules.frame_left, ttk.Button)]
            self.assertNotIn("Delete Selected", left_btns)
            self.assertNotIn("Duplicate Rule", left_btns)

            # Tip bar visible and not clipped horizontally at 1120x720
            tip_lbl = win.tab_rules.lbl_toast
            self.assertTrue(bool(tip_lbl.winfo_ismapped()))
            self.assertGreaterEqual(tip_lbl.winfo_rootx(), win.winfo_rootx())
            self.assertLessEqual(
                tip_lbl.winfo_rootx() + tip_lbl.winfo_width(),
                win.winfo_rootx() + win.winfo_width(),
            )

            # Checkbox "Enabled" + "(applies to Outlook on next Sync)" caption
            win.tab_rules.tree.selection_set("rule_rule_executive")
            win.tab_rules._on_tree_select()
            win.update()
            self.assertEqual(win.tab_rules.chk_rule_enabled.cget("text"), "Enabled")
            hdr_labels = [l.cget("text") for l in _find_widgets(win.tab_rules.frame_rule, tk.Label)]
            self.assertIn("(applies to Outlook on next Sync)", hdr_labels)
        finally:
            win.destroy()

    # ------------------------------------------------------------------
    # A. Quota color (green unless threshold "(Part " split)
    # B. Domain match exact after '@' ("x@notvendor.com" must NOT match "@vendor.com")
    # ------------------------------------------------------------------
    def test_quota_color_semantics_and_exact_domain_matching(self):
        # Pure helper tests (Item B)
        self.assertIsNone(match_email_domain("x@notvendor.com", ["@vendor.com"]))
        self.assertEqual(match_email_domain("a@vendor.com", ["@vendor.com"]), "@vendor.com")
        self.assertIsNone(match_email_domain("vendor.com", ["@vendor.com"]))

        yaml_mgr = YamlConfigManager(self.config_path)
        multi_type_rule = RuleConfig(
            id="rule_multi",
            name="Vendor Mix",
            enabled=True,
            emails=["direct@vendor.com"],
            domains=["@vendor.com"],
            subject_keywords=["Quote"],
            target_folder="Vendors\\Mix",
        )
        split_rule = RuleConfig(
            id="rule_split",
            name="Large List",
            enabled=True,
            emails=[f"u{i:02d}@big.com" for i in range(41)],
            target_folder="Vendors\\Big",
        )
        yaml_mgr.rules.extend([multi_type_rule, split_rule])
        yaml_mgr.save()

        engine = SyncEngine(yaml_mgr, MockOutlookClient())
        ok1, msg1 = engine.test_rule_match(multi_type_rule, sender_email="x@notvendor.com")
        self.assertFalse(ok1)
        self.assertEqual(msg1, "NO MATCH")

        ok2, msg2 = engine.test_rule_match(multi_type_rule, sender_email="a@vendor.com")
        self.assertTrue(ok2)
        self.assertEqual(msg2, "MATCH! (Domain Rule)")

        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.notebook.select(win.tab_rules)
            win.update()
            view: RuleManagerView = win.tab_rules

            # Multi-type rule has 3 native rules (email + domain + keyword) WITHOUT "(Part " -> GREEN
            view.tree.selection_set("rule_rule_multi")
            view._on_tree_select()
            win.update()
            self.assertIn("3 native rule(s)", view.lbl_quota.cget("text"))
            self.assertEqual(view.lbl_quota.cget("fg"), "#16a34a")

            # GUI Test Match rejects x@notvendor.com and accepts a@vendor.com
            view.ent_test_match.delete(0, tk.END)
            view.ent_test_match.insert(0, "x@notvendor.com")
            view._test_rule_match()
            self.assertEqual(view.lbl_test_result.cget("text"), "NO MATCH")

            view.ent_test_match.delete(0, tk.END)
            view.ent_test_match.insert(0, "a@vendor.com")
            view._test_rule_match()
            self.assertEqual(view.lbl_test_result.cget("text"), "MATCH! (Domain Rule)")

            # Threshold-split rule has "(Part " -> ORANGE
            view.tree.selection_set("rule_rule_split")
            view._on_tree_select()
            win.update()
            self.assertEqual(view.lbl_quota.cget("fg"), "#ea580c")
        finally:
            win.destroy()

    # ------------------------------------------------------------------
    # 3.6 Dirty tracking across Rule, Group, Link/Unlink, Keywords, Tree/Tab/Close
    # ------------------------------------------------------------------
    def test_dirty_tracking_yes_no_cancel_and_no_prompt_on_save_refresh(self):
        win = MainWindow(self.config_path, outlook_client=MockOutlookClient())
        try:
            win.geometry("1120x720")
            win.notebook.select(win.tab_rules)
            win.update()
            view: RuleManagerView = win.tab_rules

            # Start on rule_executive
            view.tree.selection_set("rule_rule_executive")
            view._on_tree_select()
            win.update()
            self.assertFalse(view.has_unsaved_changes())
            self.assertEqual(view.btn_save_rule.cget("text"), "Save Rule to YAML")

            # Link/Unlink & Add/Remove Keyword mark form dirty -> "Save Changes ●"
            view._editing_rule_group_ids.append("suppliers")
            view._refresh_linked_groups_listbox()
            view._refresh_dirty_state()
            self.assertTrue(view.has_unsaved_changes())
            self.assertEqual(view.btn_save_rule.cget("text"), "Save Changes ●")
            self.assertEqual(view.btn_save_rule.cget("style"), "DirtySave.TButton")

            view.lst_rule_groups.selection_set(view.lst_rule_groups.size() - 1)
            view._unlink_group_from_rule()
            self.assertFalse(view.has_unsaved_changes())

            view.ent_add_keyword.insert(0, "Urgent")
            view._add_keyword_chip()
            self.assertTrue(view.has_unsaved_changes())
            self.assertEqual(view.btn_save_rule.cget("text"), "Save Changes ●")

            # Normal Save refreshes tree WITHOUT asking "Save changes?"
            with patch("gui.rule_manager_view.messagebox.askyesnocancel") as mock_ask, patch.object(
                view, "_show_toast"
            ):
                view._save_rule_changes()
                mock_ask.assert_not_called()
            self.assertFalse(view.has_unsaved_changes())
            self.assertEqual(view.btn_save_rule.cget("text"), "Save Rule to YAML")

            # Case 1: Edit domain on rule_executive, select rule_engineering, Cancel (None) -> stay on old rule
            view.ent_add_domain.insert(0, "@canceldom.com")
            view._add_domain_chip()
            self.assertTrue(view.has_unsaved_changes())

            with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=None) as mock_ask:
                view.tree.selection_set("rule_rule_engineering")
                view._on_tree_select()
                mock_ask.assert_called_once()
            self.assertEqual(view.selected_rule.id, "rule_executive")
            self.assertTrue(view.has_unsaved_changes())
            self.assertEqual(view.tree.selection()[0], "rule_rule_executive")
            self.assertNotIn(
                "@canceldom.com",
                next(r for r in YamlConfigManager(self.config_path).rules if r.id == "rule_executive").domains,
            )

            # Case 2: Switch again and answer No (False) -> discarded, switches to rule_engineering
            with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=False) as mock_ask:
                view.tree.selection_set("rule_rule_engineering")
                view._on_tree_select()
                mock_ask.assert_called_once()
            self.assertEqual(view.selected_rule.id, "rule_engineering")
            self.assertFalse(view.has_unsaved_changes())
            self.assertNotIn(
                "@canceldom.com",
                next(r for r in YamlConfigManager(self.config_path).rules if r.id == "rule_executive").domains,
            )

            # Case 3: Edit domain on rule_engineering, switch to rule_suppliers, answer Yes (True) -> saved!
            view.ent_add_domain.insert(0, "@saveddom.com")
            view._add_domain_chip()
            with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=True) as mock_ask, patch.object(
                view, "_show_toast"
            ):
                view.tree.selection_set("rule_rule_suppliers")
                view._on_tree_select()
                mock_ask.assert_called_once()
            self.assertEqual(view.selected_rule.id, "rule_suppliers")
            self.assertIn(
                "@saveddom.com",
                next(r for r in YamlConfigManager(self.config_path).rules if r.id == "rule_engineering").domains,
            )

            # Group dirty tracking + tab change Cancel keeps tab 1 + close Cancel prevents destroy
            view.tree.selection_set("grp_executive")
            view._on_tree_select()
            win.update()
            view.txt_group_domains.insert(tk.END, "\n@board.com")
            view._refresh_dirty_state()
            self.assertTrue(view.is_group_dirty())
            self.assertEqual(view.btn_save_group.cget("text"), "Save Changes ●")

            # Attempt tab switch -> Cancel restores tab 1
            with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=None) as mock_ask:
                win.notebook.select(0)
                win.update()
                mock_ask.assert_called()
            self.assertEqual(win.notebook.index("current"), 1)
            self.assertTrue(view.is_group_dirty())

            # Attempt window close -> Cancel keeps window alive; Yes saves & closes
            with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=None):
                win._on_close_window()
            self.assertTrue(bool(win.winfo_exists()))

            with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=True), patch.object(
                view, "_show_toast"
            ):
                win._on_close_window()
            reloaded = YamlConfigManager(self.config_path)
            self.assertIn("@board.com", reloaded.groups["executive"].domains)
            with self.assertRaises(tk.TclError):
                win.winfo_exists()
        finally:
            try:
                if win.winfo_exists():
                    win.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    unittest.main()
