"""Create a brand-new PST (first year) from the Yearly Rollover dialog. Never touches real Outlook."""
import os
import shutil
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from core.outlook_client import MockOutlookClient, WindowsOutlookClient
from core.rollover_suggest import suggest_new_pst, validate_new_pst_path
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager
from gui.rollover_view import RolloverView
from tests.fakes import FakeNamespace, FakeStore

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")


class TestNewPstHelpers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_validate_refuses_unsafe_or_existing_paths(self):
        self.assertEqual(validate_new_pst_path(os.path.join(self.tmp, "Archive_2027.pst")), "")
        self.assertIn("Choose", validate_new_pst_path(""))
        self.assertIn(".pst", validate_new_pst_path(os.path.join(self.tmp, "a.txt")))
        self.assertIn("OneDrive", validate_new_pst_path(r"C:\Users\me\OneDrive - Corp\a.pst"))
        self.assertIn("network", validate_new_pst_path(r"\\server\share\a.pst"))
        self.assertIn("does not exist", validate_new_pst_path(os.path.join(self.tmp, "nope", "a.pst")))
        existing = os.path.join(self.tmp, "old.pst")
        open(existing, "wb").close()
        self.assertIn("already exists", validate_new_pst_path(existing))

    def test_suggestion_sits_next_to_open_data_files_and_avoids_existing(self):
        stores = [{"name": "Mailbox", "file_path": ""},
                  {"name": "store-2026", "file_path": os.path.join(self.tmp, "store-2026.pst")}]
        name, path = suggest_new_pst(stores, 2027)
        self.assertEqual((name, path), ("Archive 2027", os.path.join(self.tmp, "Archive_2027.pst")))
        open(path, "wb").close()
        name2, path2 = suggest_new_pst(stores, 2027)
        self.assertEqual((name2, path2), ("Archive 2027 (2)", os.path.join(self.tmp, "Archive_2027_2.pst")))
        # No data file open: falls back to the given folder
        empty_dir = tempfile.mkdtemp(dir=self.tmp)
        self.assertEqual(suggest_new_pst([], 2027, default_dir=empty_dir)[1], os.path.join(empty_dir, "Archive_2027.pst"))


class TestCreatePstWithOutlook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.mailbox = FakeStore("me@company.com", "", is_data_file=False)
        self.ns = FakeNamespace(stores=[self.mailbox], default_store=self.mailbox)
        self.outlook = WindowsOutlookClient(namespace=self.ns)

    def test_creates_unicode_pst_opens_it_and_names_it(self):
        path = os.path.join(self.tmp, "Archive_2027.pst")
        ok, result = self.outlook.create_pst(path, "Archive 2027")
        self.assertTrue(ok, result)
        self.assertTrue(os.path.exists(path))
        self.assertEqual(self.ns.added_store_types, [3])
        self.assertTrue(self.outlook.store_exists(path))
        self.assertEqual(self.outlook._find_store(path).GetRootFolder().Name, "Archive 2027")

    def test_never_overwrites_an_existing_file(self):
        path = os.path.join(self.tmp, "old.pst")
        with open(path, "wb") as f:
            f.write(b"keep me")
        ok, msg = self.outlook.create_pst(path, "X")
        self.assertFalse(ok)
        self.assertIn("already exists", msg)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"keep me")
        self.assertFalse(hasattr(self.ns, "added_store_types"))

    def test_mock_client_adds_store_for_the_session(self):
        mock = MockOutlookClient()
        ok, path = mock.create_pst(r"D:\Mail\Archive_2027.pst", "Archive 2027")
        self.assertTrue(ok)
        self.assertTrue(mock.store_exists(path))
        self.assertFalse(mock.create_pst(path, "again")[0])


class TestRolloverDialogCreateButton(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        cfg = os.path.join(self.tmp, "rules.yaml")
        shutil.copy2(FIXTURE, cfg)
        self.yaml_mgr = YamlConfigManager(cfg)
        self.mailbox = FakeStore("me@company.com", "", is_data_file=False)
        self.ns = FakeNamespace(stores=[self.mailbox], default_store=self.mailbox)
        self.outlook = WindowsOutlookClient(namespace=self.ns)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.view = RolloverView(self.root, self.yaml_mgr, self.outlook, SyncEngine(self.yaml_mgr, self.outlook))

    def test_create_then_rollover_to_the_new_pst(self):
        path = os.path.join(self.tmp, "Archive_2027.pst")
        # Configured archive path does not exist yet (first year): rollover is disabled
        self.assertEqual(str(self.view.btn_rollover.cget("state")), "disabled")
        with patch.object(self.view, "_ask_new_pst_path", return_value=path), \
                patch("gui.rollover_view.messagebox") as mb:
            mb.askyesno.return_value = True
            self.assertTrue(self.view._create_new_pst())
        mb.showinfo.assert_called_once()
        self.assertTrue(os.path.exists(path))
        # New PST is listed, selected and ready
        self.assertEqual(self.view.var_new_path.get(), path)
        self.assertEqual(self.view.ent_new_name.get(), "Archive 2027")
        self.assertEqual(len(self.view.tree_stores.get_children()), 2)
        self.assertEqual(str(self.view.btn_rollover.cget("state")), "normal")
        # Rules are untouched until Execute
        self.assertNotEqual(self.yaml_mgr.stores["active_archive"].file_path, path)
        ok, msg = self.view.sync_engine.perform_rollover("Archive 2027", path)
        self.assertTrue(ok, msg)
        self.assertEqual(self.yaml_mgr.stores["active_archive"].file_path, path)

    def test_cancel_or_refusal_creates_nothing(self):
        with patch.object(self.view, "_ask_new_pst_path", return_value=""):
            self.assertFalse(self.view._create_new_pst())
        existing = os.path.join(self.tmp, "old.pst")
        open(existing, "wb").close()
        with patch.object(self.view, "_ask_new_pst_path", return_value=existing), \
                patch("gui.rollover_view.messagebox") as mb:
            self.assertFalse(self.view._create_new_pst())
        mb.showwarning.assert_called_once()
        mb.askyesno.assert_not_called()
        with patch.object(self.view, "_ask_new_pst_path", return_value=os.path.join(self.tmp, "n.pst")), \
                patch("gui.rollover_view.messagebox") as mb:
            mb.askyesno.return_value = False
            self.assertFalse(self.view._create_new_pst())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "n.pst")))
        self.assertFalse(hasattr(self.ns, "added_store_types"))


if __name__ == "__main__":
    unittest.main()
