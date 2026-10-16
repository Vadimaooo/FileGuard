"""Перевірки порівняння вмісту, неповного доступу та охоплення еталона."""

import os
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from threading import Event
from unittest.mock import patch

from app.models import FileStatus, ScanIssue
from app.services.baseline_storage import BaselineStorage
from app.services.integrity_service import IntegrityService, OperationCancelled


class IntegrityCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.root = self.directory / "Документи"
        self.root.mkdir()
        self.destination = self.directory / "baseline.json"
        self.service = IntegrityService()
        self.storage = BaselineStorage()

    def write(self, path: str, content: bytes = b"abc") -> Path:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def baseline(self, recursive=True, destination=None):
        return self.service.create_baseline(
            self.root, recursive, destination or self.destination, Event(), lambda progress: None
        )

    def check(self, baseline, source=None):
        return self.service.check_integrity(baseline, source or self.destination, Event(), lambda progress: None)

    @staticmethod
    def deny_open(target: Path):
        original_open = Path.open

        def open_file(path, *args, **kwargs):
            if path == target:
                raise PermissionError("Доступ заборонено")
            return original_open(path, *args, **kwargs)

        return patch.object(Path, "open", open_file)

    def test_mixed_changes_have_correct_statuses_counts_and_do_not_update_baseline(self) -> None:
        self.write("unchanged.txt")
        changed = self.write("changed.txt")
        deleted = self.write("deleted.txt")
        self.write("Вкладена/empty.txt", b"")
        baseline = self.baseline()
        self.storage.save(baseline, self.destination, Event())
        original_json = self.destination.read_bytes()
        changed.write_bytes(b"modified")
        deleted.unlink()
        self.write("new.txt", b"new")
        result = self.check(baseline)
        statuses = {item.path: item.status for item in result.files}
        self.assertEqual(statuses, {
            "unchanged.txt": FileStatus.UNCHANGED, "changed.txt": FileStatus.CHANGED,
            "deleted.txt": FileStatus.DELETED, "new.txt": FileStatus.ADDED,
            "Вкладена/empty.txt": FileStatus.UNCHANGED,
        })
        self.assertEqual(result.counts[FileStatus.UNCHANGED], 2)
        self.assertEqual(sum(result.counts.values()), len(result.files))
        self.assertEqual(result.counts[FileStatus.ERROR], 0)
        self.assertEqual(self.destination.read_bytes(), original_json)
        removed = next(item for item in result.files if item.status == FileStatus.DELETED)
        self.assertIsNone(removed.actual)
        self.assertIsNotNone(removed.expected)
        self.assertGreaterEqual(result.duration_seconds, 0)

    def test_same_size_and_timestamp_cannot_hide_changed_content(self) -> None:
        target = self.write("document.txt", b"abc")
        before = target.stat()
        baseline = self.baseline()
        target.write_bytes(b"xyz")
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        result = self.check(baseline)
        self.assertEqual(result.files[0].status, FileStatus.CHANGED)
        self.assertEqual(result.files[0].expected.size, result.files[0].actual.size)
        self.assertEqual(result.files[0].expected.modified_ns, result.files[0].actual.modified_ns)

    def test_changed_timestamp_with_identical_content_is_unchanged(self) -> None:
        target = self.write("document.txt")
        baseline = self.baseline()
        before = target.stat()
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns + 10_000_000_000))
        self.assertEqual(self.check(baseline).files[0].status, FileStatus.UNCHANGED)

    def test_nonrecursive_baseline_does_not_report_nested_changes(self) -> None:
        self.write("root.txt")
        nested = self.write("folder/nested.txt")
        baseline = self.baseline(recursive=False)
        nested.write_bytes(b"changed")
        self.write("folder/new.txt")
        result = self.check(baseline)
        self.assertEqual([(item.path, item.status) for item in result.files], [("root.txt", FileStatus.UNCHANGED)])

    def test_both_original_and_relocated_baseline_json_are_excluded(self) -> None:
        self.write("document.txt")
        original = self.root / "baseline.json"
        baseline = self.baseline(destination=original)
        self.storage.save(baseline, original, Event())
        copied = self.root / "copied.json"
        shutil.copyfile(original, copied)
        result = self.check(baseline, source=copied)
        self.assertEqual([(item.path, item.status) for item in result.files], [("document.txt", FileStatus.UNCHANGED)])

    def test_unreadable_expected_file_is_error_and_not_deleted(self) -> None:
        target = self.write("blocked.txt")
        self.write("readable.txt")
        baseline = self.baseline()
        with self.deny_open(target):
            result = self.check(baseline)
        rows = {item.path: item for item in result.files}
        self.assertEqual(rows["blocked.txt"].status, FileStatus.ERROR)
        self.assertIn("Доступ заборонено", rows["blocked.txt"].message)
        self.assertEqual(rows["readable.txt"].status, FileStatus.UNCHANGED)
        self.assertEqual(result.counts[FileStatus.DELETED], 0)

    def test_unreadable_new_file_is_error_not_added(self) -> None:
        baseline = self.baseline()
        target = self.write("blocked.txt")
        with self.deny_open(target):
            result = self.check(baseline)
        self.assertEqual(result.files[0].status, FileStatus.ERROR)
        self.assertEqual(result.counts[FileStatus.ADDED], 0)

    @unittest.skipUnless(sys.platform == "win32", "Перевірка ексклюзивного блокування Windows")
    def test_real_windows_file_lock_is_reported_as_error_not_deleted(self) -> None:
        import ctypes
        from ctypes import wintypes

        target = self.write("locked.txt")
        baseline = self.baseline()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        # Нульові прапорці спільного доступу забороняють іншим читачам відкрити цей файл.
        handle = kernel.CreateFileW(str(target), 0x80000000, 0, None, 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            result = self.check(baseline)
        finally:
            kernel.CloseHandle(handle)
        self.assertEqual(result.files[0].status, FileStatus.ERROR)
        self.assertEqual(result.counts[FileStatus.DELETED], 0)

    def test_unreadable_directory_does_not_turn_descendants_into_deleted_files(self) -> None:
        self.write("blocked/a.txt")
        self.write("blocked/deeper/b.txt")
        self.write("readable.txt")
        baseline = self.baseline()
        original = os.scandir

        def scandir(path):
            if Path(path) == self.root / "blocked":
                raise PermissionError("Папка недоступна")
            return original(path)

        with patch("app.services.integrity_service.os.scandir", side_effect=scandir):
            result = self.check(baseline)
        statuses = {item.path: item.status for item in result.files}
        self.assertEqual(statuses["blocked/a.txt"], FileStatus.ERROR)
        self.assertEqual(statuses["blocked/deeper/b.txt"], FileStatus.ERROR)
        self.assertEqual(statuses["blocked"], FileStatus.ERROR)
        self.assertEqual(statuses["readable.txt"], FileStatus.UNCHANGED)
        self.assertEqual(result.counts[FileStatus.DELETED], 0)

    def test_partial_directory_enumeration_keeps_successfully_read_file_results(self) -> None:
        self.write("folder/a.txt")
        self.write("folder/b.txt")
        baseline = self.baseline()
        original = os.scandir
        visible_path = None

        @contextmanager
        def scandir(path):
            nonlocal visible_path
            with original(path) as entries:
                if Path(path) != self.root / "folder":
                    yield entries
                    return
                first = next(entries)
                visible_path = Path(first.path).relative_to(self.root).as_posix()

                def partial():
                    yield first
                    raise PermissionError("Обхід перервано")

                yield partial()

        with patch("app.services.integrity_service.os.scandir", side_effect=scandir):
            result = self.check(baseline)
        statuses = {item.path: item.status for item in result.files}
        self.assertEqual(statuses[visible_path], FileStatus.UNCHANGED)
        self.assertEqual(result.counts[FileStatus.DELETED], 0)
        self.assertEqual(result.counts[FileStatus.ERROR], 2)

    def test_file_missing_from_partial_baseline_is_not_claimed_as_new(self) -> None:
        blocked = self.write("blocked.txt")
        self.write("known.txt")
        with self.deny_open(blocked):
            baseline = self.baseline()
        result = self.check(baseline)
        rows = {item.path: item for item in result.files}
        self.assertEqual(rows["blocked.txt"].status, FileStatus.ERROR)
        self.assertIn("Еталон не охоплює", rows["blocked.txt"].message)
        self.assertIsNotNone(rows["blocked.txt"].actual)
        self.assertEqual(rows["known.txt"].status, FileStatus.UNCHANGED)

    def test_partial_baseline_directory_keeps_known_hash_but_marks_unknown_children(self) -> None:
        self.write("folder/known.txt")
        baseline = replace(self.baseline(), issues=(ScanIssue("folder", "Неповний обхід"),))
        self.write("folder/unknown.txt")
        result = self.check(baseline)
        statuses = {item.path: item.status for item in result.files}
        self.assertEqual(statuses["folder/known.txt"], FileStatus.UNCHANGED)
        self.assertEqual(statuses["folder/unknown.txt"], FileStatus.ERROR)
        self.assertEqual(statuses["folder"], FileStatus.ERROR)

    def test_file_replaced_by_directory_is_deleted_and_nested_file_is_added(self) -> None:
        target = self.write("document.txt")
        baseline = self.baseline()
        target.unlink()
        self.write("document.txt/inside.txt")
        result = self.check(baseline)
        self.assertEqual(result.counts[FileStatus.DELETED], 1)
        self.assertEqual(result.counts[FileStatus.ADDED], 1)

    def test_empty_baseline_and_empty_folder_have_zero_results(self) -> None:
        result = self.check(self.baseline())
        self.assertEqual(result.files, ())
        self.assertFalse(result.counts)

    def test_missing_root_is_failed_operation_and_not_all_files_deleted(self) -> None:
        self.write("document.txt")
        baseline = self.baseline()
        self.root.rename(self.directory / "moved")
        with self.assertRaises(ValueError):
            self.check(baseline)

    def test_cancelled_comparison_does_not_return_partial_results_or_change_json(self) -> None:
        self.write("document.txt", b"x" * (IntegrityService.CHUNK_SIZE + 1))
        baseline = self.baseline()
        self.storage.save(baseline, self.destination, Event())
        original_json = self.destination.read_bytes()
        cancel = Event()
        with self.assertRaises(OperationCancelled):
            self.service.check_integrity(baseline, self.destination, cancel, lambda progress: cancel.set())
        self.assertEqual(self.destination.read_bytes(), original_json)


if __name__ == "__main__":
    unittest.main()
