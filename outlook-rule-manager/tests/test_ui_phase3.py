"""Tests for UI Phase 3 (3.1 - 3.6) plus quota colors, exact domain test match, and footer colors."""
import os
import shutil
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from core.models import RuleConfig, pluralize_count
from core.outlook_client import MockOutlookClient, WindowsOutlookClient
from core.sync_engine import SyncEngine, match_email_domain
from gui import styles
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
            win.geometry("1280x760")
            win.update()

            # Check Rule Conflicts moved to MainWindow header next to Sync
            self.assertEqual(win.btn_conflicts.cget("text"), "Check Rule Conflicts")
            self.assertIs(win.btn_conflicts.master, win.btn_sync.master)
            triage_btn_texts = [b.cget("text") for b in _find_widgets(win.tab_triage, ttk.Button)]
            self.assertNotIn("Check Rule Conflicts", triage_btn_texts)

            # Footer red status in Mock mode (store not in mock stores)
            self.assertEqual(win.lbl_footer_status.cget("text"), "NOT found in Outlook")
            self.assertEqual(str(win.lbl_footer_status.cget("foreground")), styles.DANGER)

            # Single screen: Rules navigator | Mail list | Details; Search label & single action set
            triage = win.tab_triage
            self.assertEqual(len(win.workspace.panes()), 3)
            self.assertFalse(hasattr(triage, "tree_rules"))
            self.assertFalse(hasattr(triage, "drop_new_zone"))
            self.assertFalse(hasattr(triage, "mb_assign_rule"))

            action_texts = [b.cget("text") for b in _find_widgets(triage.frame_right, ttk.Button)]
            self.assertEqual(action_texts, ["Add to Rule...", "New Rule...", "Move Now"])

            search_lbl = next(
                lbl for lbl in _find_widgets(triage.frame_left, tk.Label) if lbl.cget("text") == "Search:"
            )
            self.assertTrue(bool(search_lbl.winfo_ismapped()))
            self.assertGreater(search_lbl.winfo_width(), 20)
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
            win.geometry("1280x760")
            win.show_rule_details()
            win.update()

            rules_texts = _collect_tree_texts(win.tab_rules.tree)

            for txt in rules_texts:
                self.assertNotIn("[L1]", txt)
                self.assertNotIn("[L2]", txt)
                self.assertNotIn("[ON]", txt)
                self.assertNotIn("[OFF]", txt)
                self.assertNotIn("HIERARCHICAL", txt)
                self.assertNotIn("NAVIGATOR", txt)

            self.assertIn("Folders & Rules", rules_texts)

            exec_id = r"rule_management\executive_board\directors"
            # Disabled rule styling + suffix in Rules tree
            self.assertIn("(disabled)", win.tab_rules.tree.item(f"rule_{exec_id}", "text"))
            self.assertIn("rule_disabled", win.tab_rules.tree.item(f"rule_{exec_id}", "tags"))

            # [Unclassified] rule counts 1 singular sender
            self.assertEqual(pluralize_count(1, "sender"), "1 sender")
            self.assertEqual(pluralize_count(2, "sender"), "2 senders")
            self.assertEqual(pluralize_count(0, "domain"), "0 domains")
            self.assertEqual(win.tab_rules.tree.item("rule_rule_unclassified", "values")[0], "1 sender")

            # Panel title is "Navigator" (no duplicate "Folders & Rules" panel header); merged New menubutton
            left_lbls = [l.cget("text") for l in _find_widgets(win.tab_rules.frame_left, tk.Label)]
            self.assertIn("Navigator", left_lbls)
            self.assertNotIn("Folders & Rules", left_lbls)
            rules_toolbar_btns = [b.cget("text") for b in _find_widgets(win.tab_rules, ttk.Button)]
            self.assertEqual(win.tab_rules.mb_new.cget("text"), "New")
            new_menu_labels = [
                win.tab_rules.menu_new.entrycget(i, "label")
                for i in range(win.tab_rules.menu_new.index("end") + 1)
            ]
            self.assertEqual(new_menu_labels, ["Rule", "Folder", "Subfolder"])
            self.assertNotIn("+ Root Folder (L1)", rules_toolbar_btns)
            self.assertNotIn("+ Subfolder (L+1)", rules_toolbar_btns)

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

            # Checkbox "Enabled" + "(applies to Outlook on next Sync)", clean breadcrumb, singular emails/domains
            win.tab_rules.tree.selection_set(f"rule_{exec_id}")
            win.tab_rules._on_tree_select()
            win.update()
            crumb = win.tab_rules.lbl_breadcrumb.cget("text")
            self.assertNotIn("[L1]", crumb)
            self.assertNotIn("[L2]", crumb)
            self.assertTrue(crumb.endswith("(Level 3)"))
            self.assertEqual(win.tab_rules.chk_rule_enabled.cget("text"), "Enabled")
            hdr_labels = [l.cget("text") for l in _find_widgets(win.tab_rules.frame_rule, tk.Label)]
            self.assertIn("(applies to Outlook on next Sync)", hdr_labels)

            one_rule = win.yaml_mgr.ensure_rule_for_folder(r"One\Folder")
            one_rule.emails = ["one@x.com"]
            win.yaml_mgr.save()
            win.tab_rules.refresh_all()
            win.tab_rules.tree.selection_set(f"rule_{one_rule.id}")
            win.tab_rules._on_tree_select()
            self.assertIn("1 sender, 0 domains, 0 keywords → 1 native rule", win.tab_rules.lbl_quota.cget("text"))
            self.assertNotIn("1 native rules", win.tab_rules.lbl_quota.cget("text"))
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
            win.show_rule_details()
            win.update()
            view: RuleManagerView = win.tab_rules

            # Multi-type rule has 3 native rules (email + domain + keyword) WITHOUT "(Part " -> GREEN
            view.tree.selection_set(r"rule_rule_vendors\mix")
            view._on_tree_select()
            win.update()
            self.assertIn("1 sender, 1 domain, 1 keyword → 3 native rules", view.lbl_quota.cget("text"))
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
            view.tree.selection_set(r"rule_rule_vendors\big")
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
            win.geometry("1280x760")
            win.show_rule_details()
            win.update()
            view: RuleManagerView = win.tab_rules

            exec_id = r"rule_management\executive_board\directors"
            eng_id = r"rule_engineering_team\scada_part\plc_unit"
            sup_id = r"rule_purchasing_team\vendor_part\omron_unit"

            # Start on executive rule
            view.tree.selection_set(f"rule_{exec_id}")
            view._on_tree_select()
            win.update()
            self.assertFalse(view.has_unsaved_changes())
            self.assertEqual(view.btn_save_rule.cget("text"), "Save Rule to YAML")

            view.txt_keywords.insert(tk.END, "Urgent\n")
            view._on_rule_text_changed()
            self.assertTrue(view.has_unsaved_changes())
            self.assertEqual(view.btn_save_rule.cget("text"), "Save Changes ●")
            self.assertEqual(view.btn_save_rule.cget("style"), "DirtySave.TButton")

            # Normal Save refreshes tree WITHOUT asking "Save changes?"
            with patch("gui.rule_manager_view.messagebox.askyesnocancel") as mock_ask, patch.object(
                view, "_show_toast"
            ):
                view._save_rule_changes()
                mock_ask.assert_not_called()
            self.assertFalse(view.has_unsaved_changes())
            self.assertEqual(view.btn_save_rule.cget("text"), "Save Rule to YAML")

            # Case 1: Edit domain on exec rule, select eng rule, Cancel (None) -> stay on old rule
            view.txt_domains.insert(tk.END, "@canceldom.com\n")
            view._on_rule_text_changed()
            self.assertTrue(view.has_unsaved_changes())

            with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=None) as mock_ask:
                view.tree.selection_set(f"rule_{eng_id}")
                view._on_tree_select()
                mock_ask.assert_called_once()
            self.assertEqual(view.selected_rule.id, exec_id)
            self.assertTrue(view.has_unsaved_changes())
            self.assertEqual(view.tree.selection()[0], f"rule_{exec_id}")
            self.assertNotIn(
                "@canceldom.com",
                next(r for r in YamlConfigManager(self.config_path).rules if r.id == exec_id).domains,
            )

            # Case 2: Switch again and answer No (False) -> discarded, switches to eng rule
            with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=False) as mock_ask:
                view.tree.selection_set(f"rule_{eng_id}")
                view._on_tree_select()
                mock_ask.assert_called_once()
            self.assertEqual(view.selected_rule.id, eng_id)
            self.assertFalse(view.has_unsaved_changes())
            self.assertNotIn(
                "@canceldom.com",
                next(r for r in YamlConfigManager(self.config_path).rules if r.id == exec_id).domains,
            )

            # Case 3: Edit domain on eng rule, switch to sup rule, answer Yes (True) -> saved!
            view.txt_domains.insert(tk.END, "\n@saveddom.com\n")
            view._on_rule_text_changed()
            with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=True) as mock_ask, patch.object(
                view, "_show_toast"
            ):
                view.tree.selection_set(f"rule_{sup_id}")
                view._on_tree_select()
                mock_ask.assert_called_once()
            self.assertEqual(view.selected_rule.id, sup_id)
            self.assertIn(
                "@saveddom.com",
                next(r for r in YamlConfigManager(self.config_path).rules if r.id == eng_id).domains,
            )

            # Dirty tracking on sup rule + pane switch Cancel + close Cancel/Yes
            view.txt_domains.insert(tk.END, "\n@supboard.com")
            view._on_rule_text_changed()
            self.assertTrue(view.is_rule_dirty())

            win.show_rule_details()
            with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=None) as mock_ask:
                win.show_mail_details()
                win.update()
                mock_ask.assert_called()
            self.assertEqual(win.details_mode, "rule")
            self.assertTrue(view.is_rule_dirty())

            # Attempt window close -> Cancel keeps window alive; Yes saves & closes
            with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=None):
                win._on_close_window()
            self.assertTrue(bool(win.winfo_exists()))

            with patch("gui.rule_manager_view.messagebox.askyesnocancel", return_value=True), patch.object(
                view, "_show_toast"
            ):
                win._on_close_window()
            reloaded = YamlConfigManager(self.config_path)
            self.assertIn("@supboard.com", next(r for r in reloaded.rules if r.id == sup_id).domains)
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
