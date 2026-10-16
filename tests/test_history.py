"""Перевірки постійної історії, цілісності записів та відмовостійкості."""

import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch
from contextlib import closing

from app.controllers.app_controller import AppController
from app.models import AppState, FileStatus
from app.services.directory_service import DirectoryService
from app.services.history_storage import HistoryStorage
from app.services.integrity_service import IntegrityService, OperationCancelled
from test_baseline_controller import TaskView


class HistoryView(TaskView):
    def show_saved_result(self, result, text):
        self.opened = (result, text)


class HistoryFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        source = self.root / "source"
        source.mkdir()
        (source / "Документ.txt").write_bytes(b"abc")
        service = IntegrityService()
        baseline = service.create_baseline(source, True, self.root / "b.json", Event(), lambda p: None)
        self.result = service.check_integrity(baseline, self.root / "b.json", Event(), lambda p: None)
        self.storage = HistoryStorage(self.root / "history.sqlite3")

    def finish(self, controller, view):
        deadline = time.monotonic() + 5
        while controller.state.busy and time.monotonic() < deadline:
            if view.callbacks:
                view.callbacks.pop(0)()
            time.sleep(0.005)
        self.assertFalse(controller.state.busy)


class HistoryTests(HistoryFixture, unittest.TestCase):

    def test_restart_restores_complete_result_with_hashes_and_counts(self):
        identifier = self.storage.save(self.result, Event())
        restarted = HistoryStorage(self.storage.path)
        entries = restarted.list_entries()
        self.assertEqual(entries[0].identifier, identifier)
        self.assertEqual(entries[0].counts[FileStatus.UNCHANGED], 1)
        self.assertEqual(restarted.load(identifier, Event()), self.result)

    def test_latest_entries_are_limited_without_deleting_older_records(self):
        identifiers = [self.storage.save(self.result, Event()) for _ in range(3)]
        self.assertEqual([e.identifier for e in self.storage.list_entries(2)], identifiers[:0:-1])
        self.assertEqual(self.storage.load(identifiers[0], Event()), self.result)

    def test_cancellation_after_insert_rolls_back_transaction(self):
        with patch("app.services.history_storage.check_cancelled", side_effect=[None, OperationCancelled()]):
            with self.assertRaises(OperationCancelled):
                self.storage.save(self.result, Event())
        self.assertEqual(self.storage.list_entries(), ())

    def test_corrupt_payload_or_unknown_schema_is_rejected(self):
        identifier = self.storage.save(self.result, Event())
        with closing(sqlite3.connect(self.storage.path)) as connection:
            connection.execute("UPDATE checks SET payload=? WHERE id=?", ("broken", identifier))
            connection.commit()
        with self.assertRaises(ValueError):
            self.storage.load(identifier, Event())
        with closing(sqlite3.connect(self.storage.path)) as connection:
            connection.execute("PRAGMA user_version=99")
        with self.assertRaises(ValueError):
            self.storage.list_entries()

    def test_controller_records_check_and_opens_past_result_without_changing_current_state(self):
        state = AppState(baseline=self.result.baseline)
        view = HistoryView()
        controller = AppController(state, view, DirectoryService(), history_storage=self.storage)
        controller.start()
        self.finish(controller, view)
        controller.check_integrity()
        self.finish(controller, view)
        current = state.check_result
        self.assertEqual(len(state.history_entries), 1)
        controller.open_history(state.history_entries[0].identifier)
        self.finish(controller, view)
        self.assertIs(state.check_result, current)
        self.assertEqual(view.opened[0], current)
        self.assertIn("SHA-256", view.opened[1])

    def test_history_write_failure_keeps_successful_check_visible(self):
        state = AppState(baseline=self.result.baseline)
        view = HistoryView()
        controller = AppController(state, view, DirectoryService(), history_storage=self.storage)
        with patch.object(self.storage, "save", side_effect=OSError("Диск недоступний")):
            controller.check_integrity()
            self.finish(controller, view)
        self.assertIsNotNone(state.check_result)
        self.assertEqual(state.check_result.counts[FileStatus.UNCHANGED], 1)
        self.assertEqual(len(view.errors), 1)


if __name__ == "__main__":
    unittest.main()
