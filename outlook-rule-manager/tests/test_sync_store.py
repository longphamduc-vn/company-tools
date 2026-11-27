"""Sync when the active archive PST is not open / missing (SYNC_STORE_FIX_PLAN). Never touches real Outlook."""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from core.outlook_client import MockOutlookClient, WindowsOutlookClient
from core.sync_engine import SyncEngine
from core.yaml_manager import YamlConfigManager
from tests.fakes import FakeNamespace, FakeStore

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "rules_sample.yaml")


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.config_path = os.path.join(self.tmp, "rules.yaml")
        shutil.copy2(FIXTURE, self.config_path)
        self.yaml_mgr = YamlConfigManager(self.config_path)
        self.pst_path = os.path.join(self.tmp, "longp_Archive_2025.pst")
        self.yaml_mgr.stores["active_archive"].file_path = self.pst_path
        self.mailbox = FakeStore("Primary Mailbox", "", is_data_file=False)

    def _client(self, archive_open: bool) -> WindowsOutlookClient:
        stores = [self.mailbox]
        if archive_open:
            stores.append(FakeStore("Archive 2025", self.pst_path))
        self.ns = FakeNamespace(stores=stores, default_store=self.mailbox)
        return WindowsOutlookClient(namespace=self.ns)

    def _touch_pst(self):
        with open(self.pst_path, "wb") as f:
            f.write(b"!BDN")


class TestUnclassifiedWarning(_Base):
    def test_empty_unclassified_pool_is_not_reported(self):
        self.yaml_mgr.unclassified_pool = []
        ok, msg = SyncEngine(self.yaml_mgr, self._client(archive_open=True)).push_to_outlook()
        self.assertTrue(ok, msg)
        self.assertNotIn("[Unclassified]", msg)

    def test_normal_empty_rule_is_still_reported(self):
        self.yaml_mgr.unclassified_pool = []
        rule = next(r for r in self.yaml_mgr.rules if not SyncEngine._is_unclassified_rule(r))
        rule.emails, rule.domains, rule.subject_keywords, rule.groups = [], [], [], []
        ok, msg = SyncEngine(self.yaml_mgr, self._client(archive_open=True)).push_to_outlook()
        self.assertTrue(ok, msg)
        self.assertIn(f"skipped rules with no conditions: {rule.name}", msg)

    def test_failure_message_has_no_warnings(self):
        rule = next(r for r in self.yaml_mgr.rules if not SyncEngine._is_unclassified_rule(r))
        rule.emails, rule.domains, rule.subject_keywords, rule.groups = [], [], [], []
        ok, msg = SyncEngine(self.yaml_mgr, self._client(archive_open=False)).push_to_outlook()
        self.assertFalse(ok)
        self.assertNotIn("Warning -", msg)


class TestDiagnoseStore(_Base):
    def test_four_states_with_fake_com(self):
        self.assertEqual(self._client(True).diagnose_store("")["status"], "default")
        self.assertEqual(self._client(True).diagnose_store(self.pst_path)["status"], "ok")
        client = self._client(False)
        self.assertEqual(client.diagnose_store(self.pst_path)["status"], "missing_file")
        self._touch_pst()
        info = client.diagnose_store(self.pst_path)
        self.assertEqual(info["status"], "not_open")
        self.assertEqual(info["path"], self.pst_path)
        self.assertEqual([m["name"] for m in info["mounted"]], ["Primary Mailbox"])

    def test_four_states_with_mock(self):
        mock = MockOutlookClient()
        self.assertEqual(mock.diagnose_store("")["status"], "default")
        self.assertEqual(mock.diagnose_store("/mock/data/longp_Archive_2025.pst")["status"], "ok")
        self.assertEqual(mock.diagnose_store(self.pst_path)["status"], "missing_file")
        self._touch_pst()
        self.assertEqual(mock.diagnose_store(self.pst_path)["status"], "not_open")


class TestPushPreflight(_Base):
    def test_not_open_pst_stops_before_saving_rules(self):
        self._touch_pst()
        client = self._client(archive_open=False)
        with patch.object(client, "save_native_rules") as save:
            ok, msg = SyncEngine(self.yaml_mgr, client).push_to_outlook()
        self.assertFalse(ok)
        self.assertIn("not open in Outlook", msg)
        self.assertIn(self.pst_path, msg)
        save.assert_not_called()

    def test_missing_pst_lists_open_data_files(self):
        other = FakeStore("Archive 2024", os.path.join(self.tmp, "a2024.pst"))
        self.ns = FakeNamespace(stores=[self.mailbox, other], default_store=self.mailbox)
        ok, msg = SyncEngine(self.yaml_mgr, WindowsOutlookClient(namespace=self.ns)).push_to_outlook()
        self.assertFalse(ok)
        self.assertIn("not found on disk", msg)
        self.assertIn("Yearly Rollover", msg)
        self.assertIn("Archive 2024", msg)
        self.assertNotIn("Primary Mailbox", msg)

    def test_empty_path_still_syncs_to_default_store(self):
        self.yaml_mgr.stores["active_archive"].file_path = ""
        ok, msg = SyncEngine(self.yaml_mgr, self._client(archive_open=False)).push_to_outlook()
        self.assertTrue(ok, msg)
        self.assertGreater(self.mailbox.GetRules().Count, 0)

    def test_simulation_skips_store_check(self):
        ok, msg = SyncEngine(self.yaml_mgr, MockOutlookClient()).push_to_outlook()
        self.assertTrue(ok, msg)


class TestOpenPst(_Base):
    def test_opens_existing_file(self):
        self._touch_pst()
        client = self._client(archive_open=False)
        ok, result = client.open_pst(self.pst_path)
        self.assertTrue(ok, result)
        self.assertTrue(client.store_exists(self.pst_path))

    def test_refuses_missing_file_without_calling_outlook(self):
        client = self._client(archive_open=False)
        ok, result = client.open_pst(self.pst_path)
        self.assertFalse(ok)
        self.assertIn("does not exist", result)
        self.assertEqual(getattr(self.ns, "add_store_calls", []), [])
        self.assertFalse(os.path.exists(self.pst_path))

    def test_already_open_is_not_reopened(self):
        client = self._client(archive_open=True)
        ok, _ = client.open_pst(self.pst_path)
        self.assertTrue(ok)
        self.assertEqual(getattr(self.ns, "add_store_calls", []), [])


class TestMainWindowPreflight(_Base):
    def _window(self, client):
        from gui.main_window import MainWindow

        self.yaml_mgr.save()
        win = MainWindow(self.config_path, outlook_client=client)
        self.addCleanup(win.destroy)
        win.update()
        return win

    def test_yes_opens_pst_then_syncs(self):
        self._touch_pst()
        client = self._client(archive_open=False)
        win = self._window(client)
        with patch("gui.main_window.messagebox") as mb:
            mb.askyesno.return_value = True
            win._sync_to_outlook()
        self.assertEqual(self.ns.add_store_calls, [self.pst_path])
        self.assertTrue(mb.showinfo.called, mb.showerror.call_args)
        self.assertIn("Successfully synced", mb.showinfo.call_args[0][1])

    def test_no_does_not_sync(self):
        self._touch_pst()
        client = self._client(archive_open=False)
        win = self._window(client)
        with patch("gui.main_window.messagebox") as mb, patch.object(
            win.sync_engine, "push_to_outlook"
        ) as push:
            mb.askyesno.return_value = False
            win._sync_to_outlook()
        push.assert_not_called()
        self.assertEqual(getattr(self.ns, "add_store_calls", []), [])

    def test_missing_file_offers_rollover_and_does_not_sync(self):
        client = self._client(archive_open=False)
        win = self._window(client)
        with patch("gui.main_window.messagebox") as mb, patch.object(
            win, "_open_rollover_dialog"
        ) as rollover, patch.object(win.sync_engine, "push_to_outlook") as push:
            mb.askyesno.return_value = True
            win._sync_to_outlook()
        rollover.assert_called_once()
        push.assert_not_called()


if __name__ == "__main__":
    unittest.main()
