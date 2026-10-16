"""Наскрізні сценарії на справжніх файлах без підміни сховищ."""

import csv
import hashlib
import tempfile
import unittest
from pathlib import Path
from threading import Event

from app.controllers.app_controller import AppController
from app.models import AppSettings, AppState, FileStatus
from app.services.baseline_storage import BaselineStorage
from app.services.directory_service import DirectoryService
from app.services.history_storage import HistoryStorage
from app.services.integrity_service import IntegrityService
from app.services.report_service import ReportService
from app.services.settings_storage import SettingsStorage
from test_history import HistoryFixture, HistoryView


class AcceptanceTests(HistoryFixture, unittest.TestCase):
    def test_complete_workflow_restart_and_independent_export_validation(self):
        source = self.root / "Курсова робота"
        source.mkdir()
        (source / "Вкладена").mkdir()
        (source / "cache").mkdir()
        for name, content in {"Без змін.txt": b"same", "Змінений.txt": b"before",
                              "Видалений.txt": b"delete", "Вкладена/empty.txt": b"",
                              "ignored.tmp": b"excluded", "cache/data.txt": b"excluded"}.items():
            (source / name).write_bytes(content)
        service, baselines = IntegrityService(), BaselineStorage()
        destination = source / "baseline.json"
        baseline = service.create_baseline(source, True, destination, Event(), lambda p: None,
                                           ("*.tmp", "cache/"))
        baselines.save(baseline, destination, Event())
        initial_json = destination.read_bytes()
        self.assertEqual(len(baseline.files), 4)
        self.assertEqual(service.check_integrity(baseline, destination, Event(), lambda p: None)
                         .counts[FileStatus.UNCHANGED], 4)
        (source / "Змінений.txt").write_bytes(b"after")
        (source / "Видалений.txt").unlink()
        (source / "Новий.txt").write_text("Новий документ", encoding="utf-8")
        (source / "new.tmp").write_bytes(b"excluded")
        (source / "cache/data.txt").write_bytes(b"ignored changes")
        result = service.check_integrity(baselines.load(destination, Event()), destination, Event(), lambda p: None)
        self.assertEqual([result.counts[status] for status in FileStatus], [2, 1, 1, 1, 0])
        self.assertEqual(destination.read_bytes(), initial_json)
        changed = next(item for item in result.files if item.status == FileStatus.CHANGED)
        self.assertEqual(changed.actual.sha256, hashlib.sha256(b"after").hexdigest())
        identifier = self.storage.save(result, Event())
        settings = SettingsStorage(self.root / "settings.json")
        preferences = AppSettings(source, True, ("*.tmp", "cache/"), FileStatus.CHANGED, (1100, 850))
        settings.save(preferences, Event())
        source.rename(self.root / "Переміщена робота")
        restored = HistoryStorage(self.storage.path).load(identifier, Event())
        self.assertEqual(restored, result)
        self.assertEqual(SettingsStorage(settings.path).load(), preferences)
        for extension in ("txt", "csv"):
            report = ReportService().export(restored, str(self.root / f"report.{extension}"), extension, Event())
            if extension == "txt":
                self.assertIn(changed.actual.sha256, report.read_text(encoding="utf-8"))
                self.assertIn("Усього записів: 5", report.read_text(encoding="utf-8"))
            else:
                with report.open(encoding="utf-8-sig", newline="") as stream:
                    rows = list(csv.DictReader(stream, delimiter=";"))
                self.assertEqual(len(rows), 5)
                self.assertEqual({row["Файл"]: row["Статус"] for row in rows},
                                 {item.path: item.status.value for item in result.files})

    def test_empty_and_thousand_file_scan_with_large_binary_and_progress(self):
        service, baselines = IntegrityService(), BaselineStorage()
        source = self.root / "Обсяг"
        source.mkdir()
        destination = self.root / "volume.json"
        empty = service.create_baseline(source, True, destination, Event(), lambda p: None)
        self.assertEqual(service.check_integrity(empty, destination, Event(), lambda p: None).files, ())
        payload = bytes(range(256)) * 65536  # 16 МіБ: читання кількома блоками.
        (source / "large.bin").write_bytes(payload)
        for index in range(1000):
            (source / f"file_{index:04}.txt").write_bytes(str(index).encode("ascii"))
        progress = []
        baseline = service.create_baseline(source, True, destination, Event(), progress.append)
        self.assertEqual(len(baseline.files), 1001)
        self.assertEqual(progress[-1].processed_files, 1001)
        self.assertEqual(progress[-1].processed_bytes, sum(item.size for item in baseline.files))
        self.assertEqual(next(item.sha256 for item in baseline.files if item.path == "large.bin"),
                         hashlib.sha256(payload).hexdigest())
        baselines.save(baseline, destination, Event())
        self.assertEqual(service.check_integrity(baselines.load(destination, Event()), destination,
                         Event(), lambda p: None).counts[FileStatus.UNCHANGED], 1001)

    def test_real_corrupt_history_does_not_hide_check_or_modify_source(self):
        self.storage.path.write_bytes(b"not a SQLite database")
        source = self.result.baseline.root_folder / "Документ.txt"
        content = source.read_bytes()
        state, view = AppState(baseline=self.result.baseline), HistoryView()
        controller = AppController(state, view, DirectoryService(), history_storage=self.storage)
        controller.check_integrity()
        self.finish(controller, view)
        self.assertEqual(state.check_result.counts[FileStatus.UNCHANGED], 1)
        self.assertEqual(source.read_bytes(), content)
        self.assertEqual(len(view.errors), 1)
