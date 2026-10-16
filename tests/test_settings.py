"""Перевірки налаштувань, повторного запуску та безпечного закриття."""

import json
import unittest
from threading import Event
from unittest.mock import patch

from app.controllers.app_controller import AppController
from app.models import AppSettings, AppState, FileStatus
from app.services.directory_service import DirectoryService
from app.services.integrity_service import OperationCancelled
from app.services.settings_storage import SettingsStorage
from test_history import HistoryFixture, HistoryView


class SettingsView(HistoryView):
    def get_window_size(self):
        return (1100, 850)

    def apply_window_size(self, size):
        self.applied_size = size


class SettingsTests(HistoryFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.settings_storage = SettingsStorage(self.root / "settings.json")
        self.preferences = AppSettings(self.root / "Відсутня папка", False,
                                       ("*.tmp", "cache/"), FileStatus.CHANGED, (1100, 850))

    def controller(self):
        view = SettingsView()
        controller = AppController(AppState(), view, DirectoryService(), history_storage=self.storage,
                                   settings_storage=self.settings_storage)
        return controller, view

    def test_missing_defaults_and_unicode_roundtrip(self):
        self.assertEqual(self.settings_storage.load(), AppSettings())
        self.settings_storage.save(self.preferences, Event())
        self.assertEqual(self.settings_storage.load(), self.preferences)

    def test_invalid_fields_duplicates_and_oversized_json_are_rejected(self):
        original = self.settings_storage._document(self.preferences)
        invalid = {"version": 99, "last_folder": "relative", "include_subfolders": 1,
                   "exclusion_patterns": ["../escape"], "status_filter": "unknown",
                   "window_size": [980, True]}
        for key, value in invalid.items():
            with self.subTest(key=key):
                document = dict(original, **{key: value})
                self.settings_storage.path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.settings_storage.load()
        for raw in (b'{"version":1,"version":1}', b"broken", b" " * (SettingsStorage.MAX_BYTES + 1)):
            self.settings_storage.path.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.settings_storage.load()

    def test_cancel_and_replace_failure_preserve_previous_file(self):
        self.settings_storage.save(self.preferences, Event())
        original = self.settings_storage.path.read_bytes()
        cancel = Event()
        cancel.set()
        with self.assertRaises(OperationCancelled):
            self.settings_storage.save(AppSettings(), cancel)
        with patch("app.services.atomic_file.os.replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                self.settings_storage.save(AppSettings(), Event())
        self.assertEqual(self.settings_storage.path.read_bytes(), original)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_startup_restores_preferences_and_history_without_scanning(self):
        self.settings_storage.save(self.preferences, Event())
        self.storage.save(self.result, Event())
        controller, view = self.controller()
        with patch.object(controller.directory_service, "validate_folder", side_effect=AssertionError("scan")):
            controller.start()
            self.finish(controller, view)
        self.assertEqual(controller.state.selected_folder, self.preferences.last_folder)
        self.assertFalse(controller.state.include_subfolders)
        self.assertEqual(controller.state.exclusion_patterns, self.preferences.exclusion_patterns)
        self.assertEqual(controller.state.status_filter, FileStatus.CHANGED)
        self.assertEqual(view.applied_size, (1100, 850))
        self.assertIsNone(controller.state.baseline)
        self.assertEqual(len(controller.state.history_entries), 1)
        self.assertEqual(view.errors, [])

    def test_close_automatically_saves_applied_preferences(self):
        controller, view = self.controller()
        controller.start()
        self.finish(controller, view)
        controller.select_folder(str(self.result.baseline.root_folder))
        controller.set_include_subfolders(False)
        controller.set_exclusion_patterns(["*.tmp"])
        controller.set_status_filter(FileStatus.DELETED.value)
        controller.request_close()
        self.finish(controller, view)
        self.assertTrue(view.closed)
        self.assertEqual(self.settings_storage.load(), AppSettings(self.result.baseline.root_folder,
                         False, ("*.tmp",), FileStatus.DELETED, (1100, 850)))

    def test_corrupt_settings_are_reported_and_preserved_on_close(self):
        self.settings_storage.path.write_bytes(b"broken")
        controller, view = self.controller()
        controller.start()
        self.finish(controller, view)
        self.assertEqual(len(view.errors), 1)
        controller.request_close()
        self.assertTrue(view.closed)
        self.assertEqual(self.settings_storage.path.read_bytes(), b"broken")

    def test_applied_change_can_replace_corrupt_settings(self):
        self.settings_storage.path.write_bytes(b"broken")
        controller, view = self.controller()
        controller.start()
        self.finish(controller, view)
        controller.set_include_subfolders(False)
        controller.request_close()
        self.finish(controller, view)
        self.assertFalse(self.settings_storage.load().include_subfolders)
        self.assertTrue(view.closed)

    def test_close_during_cancelled_startup_preserves_unread_settings(self):
        self.settings_storage.save(self.preferences, Event())
        controller, view = self.controller()
        with patch("app.controllers.app_controller.check_cancelled", side_effect=OperationCancelled):
            controller.start()
            controller.request_close()
            self.finish(controller, view)
        self.assertTrue(view.closed)
        self.assertEqual(self.settings_storage.load(), self.preferences)

    def test_close_after_cancelled_operation_saves_settings(self):
        controller, view = self.controller()
        controller.start()
        self.finish(controller, view)
        controller._start_task(lambda: controller._cancel.wait(2), "test", "test")
        controller.request_close()
        self.finish(controller, view)
        self.assertTrue(view.closed)
        self.assertEqual(self.settings_storage.load().window_size, (1100, 850))

    def test_save_failure_reports_error_and_closes_without_retry(self):
        controller, view = self.controller()
        controller.start()
        self.finish(controller, view)
        with patch.object(self.settings_storage, "save", side_effect=OSError("disk unavailable")) as save:
            controller.request_close()
            self.finish(controller, view)
        self.assertTrue(view.closed)
        self.assertEqual(save.call_count, 1)
        self.assertEqual(len(view.errors), 1)

    def test_obsolete_preferences_preserve_current_settings_on_restart(self):
        document = self.settings_storage._document(self.preferences)
        document["glass_enabled"] = True
        self.settings_storage.path.write_text(json.dumps(document), encoding="utf-8")
        self.assertEqual(self.settings_storage.load(), self.preferences)
        controller, view = self.controller()
        controller.start()
        self.finish(controller, view)
        controller.save_settings()
        self.finish(controller, view)
        self.assertEqual(self.settings_storage.load(), self.preferences)
        self.assertNotIn("glass_enabled", json.loads(self.settings_storage.path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
