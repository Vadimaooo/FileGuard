"""Перевірки справжнього хешування, формату еталона та цілісності запису."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from app.services.baseline_storage import BaselineStorage
from app.services.integrity_service import IntegrityService, OperationCancelled


class BaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.root = self.directory / "Документи з пробілами"
        self.root.mkdir()
        (self.root / "Документ.txt").write_bytes(b"abc")
        (self.root / "empty.txt").write_bytes(b"")
        (self.root / "Вкладена").mkdir()
        (self.root / "Вкладена" / "data.bin").write_bytes(bytes(range(256)) * 16)
        self.destination = self.directory / "еталон.json"
        self.scanner = IntegrityService()
        self.storage = BaselineStorage()

    def scan(self, recursive: bool = True, destination: Path | None = None, callback=None):
        return self.scanner.create_baseline(
            self.root, recursive, destination or self.destination, Event(), callback or (lambda progress: None)
        )

    def test_hashes_match_known_values_and_source_files_remain_unchanged(self) -> None:
        baseline = self.scan()
        files = {item.path: item for item in baseline.files}
        self.assertEqual(files["Документ.txt"].sha256,
                         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        self.assertEqual(files["empty.txt"].sha256, hashlib.sha256(b"").hexdigest())
        self.assertEqual(files["Вкладена/data.bin"].sha256, hashlib.sha256(bytes(range(256)) * 16).hexdigest())
        self.assertEqual(files["Документ.txt"].size, 3)
        self.assertEqual((self.root / "Документ.txt").read_bytes(), b"abc")
        self.assertFalse(baseline.issues)

    def test_nonrecursive_scan_contains_only_top_level_files(self) -> None:
        baseline = self.scan(recursive=False)
        self.assertEqual({item.path for item in baseline.files}, {"Документ.txt", "empty.txt"})
        self.assertFalse(baseline.include_subfolders)

    def test_empty_folder_can_be_saved_and_loaded(self) -> None:
        empty = self.directory / "Порожня"
        empty.mkdir()
        baseline = self.scanner.create_baseline(empty, True, self.destination, Event(), lambda value: None)
        self.storage.save(baseline, self.destination, Event())
        self.assertEqual(self.storage.load(self.destination, Event()), baseline)
        self.assertEqual(baseline.files, ())

    def test_json_round_trip_preserves_metadata_and_works_after_folder_is_moved(self) -> None:
        baseline = self.scan()
        self.storage.save(baseline, self.destination, Event())
        self.root.rename(self.directory / "Переміщена папка")
        loaded = self.storage.load(self.destination, Event())
        self.assertEqual(loaded, baseline)
        self.assertIn("Документ.txt", self.destination.read_text(encoding="utf-8"))

    def test_destination_inside_root_is_excluded_even_if_it_already_exists(self) -> None:
        destination = self.root / "baseline.json"
        destination.write_text("previous baseline", encoding="utf-8")
        baseline = self.scan(destination=destination)
        self.assertEqual(baseline.excluded_paths, ("baseline.json",))
        self.assertNotIn("baseline.json", {item.path for item in baseline.files})
        self.storage.save(baseline, destination, Event())
        self.assertEqual(self.storage.load(destination, Event()), baseline)

    def test_unreadable_file_is_reported_and_other_files_are_preserved(self) -> None:
        blocked = self.root / "Документ.txt"
        original_open = Path.open

        def open_file(path, *args, **kwargs):
            if path == blocked:
                raise PermissionError("Доступ заборонено")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", open_file):
            baseline = self.scan()
        self.assertEqual(len(baseline.files), 2)
        self.assertEqual(baseline.issues[0].path, "Документ.txt")
        self.assertIn("Доступ заборонено", baseline.issues[0].message)
        self.storage.save(baseline, self.destination, Event())
        self.assertEqual(self.storage.load(self.destination, Event()), baseline)

    def test_file_changed_while_reading_is_not_accepted_as_stable_snapshot(self) -> None:
        source = self.root / "Документ.txt"
        source.write_bytes(b"x" * (self.scanner.CHUNK_SIZE + 1))
        changed = False

        def change_during_scan(progress):
            nonlocal changed
            if progress.current_path == "Документ.txt" and not changed:
                with source.open("ab") as stream:
                    stream.write(b"changed")
                changed = True

        baseline = self.scan(callback=change_during_scan)
        self.assertTrue(changed)
        self.assertNotIn("Документ.txt", {item.path for item in baseline.files})
        self.assertTrue(any("змінився" in issue.message for issue in baseline.issues))

    def test_cancellation_interrupts_reading(self) -> None:
        cancel = Event()
        with self.assertRaises(OperationCancelled):
            self.scanner.create_baseline(self.root, True, self.destination, cancel, lambda value: cancel.set())

    def test_cancelled_save_preserves_existing_file(self) -> None:
        baseline = self.scan()
        self.destination.write_bytes(b"previous baseline")
        cancel = Event()
        original_dump = json.dump

        def cancel_after_write(*args, **kwargs):
            original_dump(*args, **kwargs)
            cancel.set()

        with patch("app.services.baseline_storage.json.dump", side_effect=cancel_after_write):
            with self.assertRaises(OperationCancelled):
                self.storage.save(baseline, self.destination, cancel)
        self.assertEqual(self.destination.read_bytes(), b"previous baseline")
        self.assertFalse(list(self.directory.glob(".fileguard-*.tmp")))

    def test_failed_atomic_replace_preserves_existing_file_and_removes_temporary_file(self) -> None:
        self.destination.write_bytes(b"previous baseline")
        with patch("app.services.baseline_storage.os.replace", side_effect=PermissionError("Зайнято")):
            with self.assertRaises(PermissionError):
                self.storage.save(self.scan(), self.destination, Event())
        self.assertEqual(self.destination.read_bytes(), b"previous baseline")
        self.assertFalse(list(self.directory.glob(".fileguard-*.tmp")))

    def test_malformed_json_duplicate_keys_and_wrong_encoding_are_rejected(self) -> None:
        for content in (b"not json", b'{"application":"FileGuard","application":"Other"}', b"\xff\xfe"):
            with self.subTest(content=content):
                self.destination.write_bytes(content)
                with self.assertRaises(ValueError):
                    self.storage.load(self.destination, Event())

    def test_invalid_schema_fields_and_dangerous_paths_are_rejected(self) -> None:
        original = self.storage._document(self.scan())
        changes = [
            ("application", "Other"), ("schema_version", True), ("schema_version", 99),
            ("algorithm", "MD5"), ("root_folder", "relative"), ("include_subfolders", 1),
            ("created_at", "2026-10-15T12:00:00"), ("files", None), ("issues", {}),
            ("excluded_paths", ["../outside"]),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                document = dict(original)
                document[field] = value
                self.destination.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.storage.load(self.destination, Event())
        for path in ("../outside.txt", "/absolute.txt", "C:/outside.txt", "a\\b", ".", "a//b", "a/./b", "file. "):
            with self.subTest(path=path):
                document = json.loads(json.dumps(original))
                document["files"][0]["path"] = path
                self.destination.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.storage.load(self.destination, Event())

    def test_invalid_hash_sizes_and_duplicate_file_paths_are_rejected(self) -> None:
        original = self.storage._document(self.scan())
        for key, value in (("sha256", "x" * 64), ("sha256", "a"), ("size", -1), ("size", 10**400),
                           ("size", True), ("modified_ns", False)):
            with self.subTest(key=key, value=value):
                document = json.loads(json.dumps(original))
                document["files"][0][key] = value
                with self.assertRaises(ValueError):
                    self.storage._validate(document)
        document = json.loads(json.dumps(original))
        document["files"].append(dict(document["files"][0]))
        with self.assertRaises(ValueError):
            self.storage._validate(document)

    def test_oversized_json_is_rejected_before_decoding(self) -> None:
        self.destination.write_bytes(b" " * 33)
        with patch.object(self.storage, "MAX_JSON_BYTES", 32):
            with self.assertRaises(ValueError):
                self.storage.load(self.destination, Event())

    def test_destination_must_be_json_file_in_existing_directory(self) -> None:
        for target in (self.directory / "file.txt", self.directory / "missing" / "base.json"):
            with self.subTest(target=target):
                with self.assertRaises((ValueError, OSError)):
                    self.storage.prepare_destination(str(target))


if __name__ == "__main__":
    unittest.main()
