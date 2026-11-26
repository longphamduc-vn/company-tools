"""Tests verifying FakeRules and FakeFolderCollection match real Outlook COM behavior."""
import unittest

from tests.fakes import FakeFolder, FakeRules


class TestFakeComBehavior(unittest.TestCase):
    """Ensure test fakes reproduce COM edge cases."""

    def test_fake_rules_iter_mutates_in_place_on_remove(self):
        rules = FakeRules()
        rules.Create("Rule1")
        rules.Create("Rule2")
        rules.Create("Rule3")

        # Removing while iterating directly skips Rule2, just like COM collection iteration
        for rule in rules:
            rules.Remove(rule.Name)

        remaining_names = [r.Name for r in rules]
        self.assertEqual(remaining_names, ["Rule2"])

        # Collecting names first removes everything safely
        names_to_remove = [r.Name for r in rules]
        for name in names_to_remove:
            rules.Remove(name)
        self.assertEqual(rules.Count, 0)

    def test_fake_folder_add_raises_on_case_insensitive_duplicate(self):
        root = FakeFolder("Archive")
        root.Folders.Add("Engineering")

        with self.assertRaises(ValueError):
            root.Folders.Add("engineering")
