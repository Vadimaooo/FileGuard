"""Перевірки правил, сумісності форматів і незмінності охоплення."""

import tempfile
import unittest
from pathlib import Path
from threading import Event

from app.models import FileStatus
from app.services.baseline_storage import BaselineStorage
from app.services.exclusions import ExclusionRules
from app.services.integrity_service import IntegrityService


class ExclusionTests(unittest.TestCase):
    def test_masks_paths_and_directory_rules(self):
        rules = ExclusionRules(("*.tmp", ".git", "cache/", "logs/*.log"))
        for path, directory in (("a.TMP", False), ("sub/a.tmp", False), (".git", True),
                                ("sub/.git/HEAD", False), ("cache", True), ("cache/a.txt", False),
                                ("logs/server.log", False)):
            self.assertTrue(rules.matches(path, directory), path)
        self.assertFalse(rules.matches("cache", False))
        self.assertFalse(rules.matches("cached/a.txt"))
        self.assertFalse(rules.matches("a.txt"))

    def test_invalid_rules_are_rejected(self):
        for pattern in ("../a", "/absolute", "C:/a", "!a", "a//b", "a\nb", ""):
            with self.subTest(pattern=pattern), self.assertRaises(ValueError):
                ExclusionRules((pattern,))
        self.assertEqual(ExclusionRules(("*.TMP", "*.tmp")).patterns, ("*.TMP",))

    def test_saved_rules_are_used_for_comparison_and_internal_directory_is_excluded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "state").mkdir()
            (root / "state" / "history.db").write_bytes(b"old")
            (root / "a.tmp").write_bytes(b"old")
            (root / "a.txt").write_bytes(b"same")
            destination = root / "baseline.json"
            service = IntegrityService((root / "state",))
            baseline = service.create_baseline(root, True, destination, Event(), lambda p: None, ("*.tmp",))
            storage = BaselineStorage()
            storage.save(baseline, destination, Event())
            loaded = storage.load(destination, Event())
            self.assertEqual(loaded, baseline)
            self.assertEqual([f.path for f in baseline.files], ["a.txt"])
            (root / "a.tmp").unlink()
            (root / "new.tmp").write_bytes(b"new")
            (root / "state" / "history.db").write_bytes(b"updated")
            result = service.check_integrity(loaded, destination, Event(), lambda p: None)
            self.assertEqual(result.counts[FileStatus.UNCHANGED], 1)
            self.assertEqual(len(result.files), 1)

    def test_legacy_version_one_is_read_without_new_rules(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            storage = BaselineStorage()
            baseline = IntegrityService().create_baseline(root, True, root / "b.json", Event(), lambda p: None)
            document = storage._document(baseline)
            document["schema_version"] = 1
            document.pop("exclusion_patterns")
            self.assertEqual(storage._validate(document).exclusion_patterns, ())


if __name__ == "__main__":
    unittest.main()
