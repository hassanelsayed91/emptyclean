"""Tests for the EmptyClean core. Run with: python -m pytest -q"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from emptyclean import core
from emptyclean.core import CleanOptions


class BaseCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "root"
        self.root.mkdir()
        # temp files
        (self.root / "a.tmp").write_bytes(b"x" * 10)
        (self.root / "b.crdownload").write_bytes(b"y" * 5)
        (self.root / "keep.txt").write_bytes(b"keep")
        # empty dirs
        (self.root / "emptydir").mkdir()
        (self.root / "nested" / "deep").mkdir(parents=True)
        # non-empty dir
        (self.root / "nonempty").mkdir()
        (self.root / "nonempty" / "file.txt").write_bytes(b"z")

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, data=b"x"):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p


class PlanTests(BaseCase):
    def test_finds_temp_files(self):
        items = core.plan_clean(self.root, CleanOptions())
        temps = [it for it in items if it.kind == "temp_file"]
        names = sorted(it.src.name for it in temps)
        self.assertEqual(names, ["a.tmp", "b.crdownload"])

    def test_finds_empty_dirs(self):
        items = core.plan_clean(self.root, CleanOptions())
        dirs = [it for it in items if it.kind == "empty_dir"]
        names = sorted(it.src.name for it in dirs)
        # emptydir and nested/deep (nested becomes empty after deep removed? cascading)
        self.assertIn("emptydir", names)
        self.assertIn("deep", names)

    def test_nonempty_dir_not_removed(self):
        items = core.plan_clean(self.root, CleanOptions())
        dirs = [it for it in items if it.kind == "empty_dir"]
        names = [it.src.name for it in dirs]
        self.assertNotIn("nonempty", names)

    def test_no_temp_mode(self):
        opts = CleanOptions(delete_temp_files=False)
        items = core.plan_clean(self.root, opts)
        self.assertTrue(all(it.kind == "empty_dir" for it in items))

    def test_no_empty_mode(self):
        opts = CleanOptions(delete_empty_dirs=False)
        items = core.plan_clean(self.root, opts)
        self.assertTrue(all(it.kind == "temp_file" for it in items))

    def test_pattern_filter(self):
        opts = CleanOptions(temp_patterns=["*.tmp"])
        items = core.plan_clean(self.root, opts)
        temps = [it for it in items if it.kind == "temp_file"]
        self.assertEqual([it.src.name for it in temps], ["a.tmp"])

    def test_min_age(self):
        opts = CleanOptions(min_age_seconds=10**9)
        items = core.plan_clean(self.root, opts)
        temps = [it for it in items if it.kind == "temp_file"]
        self.assertEqual(temps, [])

    def test_not_a_dir(self):
        with self.assertRaises(NotADirectoryError):
            core.plan_clean(self.root / "nope", CleanOptions())

    def test_custom_exclude(self):
        opts = CleanOptions(exclude_dirs=["nested"])
        items = core.plan_clean(self.root, opts)
        dirs = [it for it in items if it.kind == "empty_dir"]
        names = [it.src.name for it in dirs]
        self.assertNotIn("deep", names)


class ExecuteUndoTests(BaseCase):
    def test_execute_and_undo_roundtrip(self):
        opts = CleanOptions()
        items = core.plan_clean(self.root, opts)
        summary, journal = core.execute(items)
        self.assertGreater(summary.get("deleted", 0), 0)
        self.assertTrue(journal is not None and journal.exists())
        # temp file gone
        self.assertFalse((self.root / "a.tmp").exists())
        # empty dir gone
        self.assertFalse((self.root / "emptydir").exists())
        # kept file still there
        self.assertTrue((self.root / "keep.txt").exists())
        # undo
        usum, _ = core.undo(journal)
        self.assertGreater(usum.get("restored", 0), 0)
        self.assertTrue((self.root / "a.tmp").exists())
        self.assertTrue((self.root / "emptydir").exists())

    def test_dry_run(self):
        items = core.plan_clean(self.root, CleanOptions())
        before = sorted(str(p) for p in self.root.rglob("*"))
        summary, journal = core.execute(items, dry_run=True)
        after = sorted(str(p) for p in self.root.rglob("*"))
        self.assertEqual(before, after)
        self.assertIsNone(journal)

    def test_no_items_no_journal(self):
        opts = CleanOptions(delete_empty_dirs=False, delete_temp_files=False)
        items = core.plan_clean(self.root, opts)
        summary, journal = core.execute(items)
        self.assertIsNone(journal)


class HelperTests(unittest.TestCase):
    def test_human_size(self):
        self.assertEqual(core.human_size(0), "0 B")
        self.assertEqual(core.human_size(1024), "1.0 KB")

    def test_version(self):
        self.assertEqual(core.VERSION, "1.0.0")
        self.assertIn("emptyclean", core.PROJECT_URL)


if __name__ == "__main__":
    unittest.main()
