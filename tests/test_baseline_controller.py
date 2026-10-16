"""Перевірки фонового виконання та збереження стану без tkinter."""

import tempfile
import time
import unittest
from pathlib import Path
from threading import get_ident

from app.controllers.app_controller import AppController
from app.models import AppState, FileStatus
from app.services.baseline_storage import BaselineStorage
from app.services.directory_service import DirectoryService
from app.services.integrity_service import IntegrityService, OperationCancelled


class TaskView:
    def __init__(self) -> None:
        self.save_path = ""
        self.open_path = ""
        self.errors = []
        self.callbacks = []
        self.thread_ids = []
        self.closed = False

    def render_state(self, state):
        self.thread_ids.append(get_ident())

    def ask_save_baseline(self, directory, filename):
        return self.save_path

    def ask_open_baseline(self, directory):
        return self.open_path

    def show_error(self, title, message):
        self.errors.append((title, message))

    def schedule(self, delay_ms, callback):
        self.thread_ids.append(get_ident())
        self.callbacks.append(callback)

    def close(self):
        self.closed = True


class BaselineControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.root = self.directory / "source"
        self.root.mkdir()
        (self.root / "test.txt").write_text("abc", encoding="utf-8")
        self.destination = self.directory / "baseline.json"
        self.view = TaskView()
        self.state = AppState(selected_folder=self.root)
        self.controller = AppController(self.state, self.view, DirectoryService())

    def finish(self) -> None:
        deadline = time.monotonic() + 5
        while self.state.busy and time.monotonic() < deadline:
            if self.view.callbacks:
                self.view.callbacks.pop(0)()
            time.sleep(0.005)
        self.assertFalse(self.state.busy, "Фонова операція не завершилася вчасно")

    def test_create_and_reload_uses_worker_without_touching_view_from_background(self) -> None:
        main_thread = get_ident()
        self.view.save_path = str(self.destination)
        self.controller.create_baseline()
        self.assertTrue(self.state.busy)
        self.assertFalse(self.controller.select_folder(str(self.directory)))
        self.controller.set_include_subfolders(False)
        self.assertTrue(self.state.include_subfolders)
        self.finish()
        original = self.state.baseline
        self.assertIsNotNone(original)
        self.assertTrue(self.destination.exists())
        self.view.open_path = str(self.destination)
        self.controller.load_baseline()
        self.finish()
        self.assertEqual(self.state.baseline, original)
        self.assertEqual(set(self.view.thread_ids), {main_thread})
        self.assertFalse(self.view.errors)

    def test_load_error_preserves_previous_baseline(self) -> None:
        self.view.save_path = str(self.destination)
        self.controller.create_baseline()
        self.finish()
        previous = self.state.baseline
        damaged = self.directory / "damaged.json"
        damaged.write_text("broken", encoding="utf-8")
        self.view.open_path = str(damaged)
        self.controller.load_baseline()
        self.finish()
        self.assertIs(self.state.baseline, previous)
        self.assertEqual(self.state.baseline_path, self.destination)
        self.assertEqual(len(self.view.errors), 1)

    def test_cancelled_dialog_does_not_start_a_worker(self) -> None:
        self.controller.create_baseline()
        self.controller.load_baseline()
        self.assertFalse(self.state.busy)
        self.assertFalse(self.view.callbacks)
        self.assertFalse(self.destination.exists())

    def test_close_during_scan_cancels_before_closing_view(self) -> None:
        class WaitForCancellation(IntegrityService):
            def create_baseline(self, root, recursive, destination, cancel, on_progress):
                if not cancel.wait(3):
                    raise RuntimeError("Очікування скасування перевищено")
                raise OperationCancelled()

        self.controller = AppController(self.state, self.view, DirectoryService(), WaitForCancellation())
        self.view.save_path = str(self.destination)
        self.controller.create_baseline()
        self.controller.request_close()
        self.assertFalse(self.view.closed)
        self.finish()
        self.assertTrue(self.view.closed)
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.view.errors)

    def test_selecting_different_folder_clears_unrelated_baseline(self) -> None:
        self.view.save_path = str(self.destination)
        self.controller.create_baseline()
        self.finish()
        self.assertIsNotNone(self.state.baseline)
        self.controller.check_integrity()
        self.finish()
        self.assertIsNotNone(self.state.check_result)
        self.assertTrue(self.controller.select_folder(str(self.directory)))
        self.assertIsNone(self.state.baseline)
        self.assertIsNone(self.state.baseline_path)
        self.assertIsNone(self.state.check_result)

    def test_check_updates_results_without_modifying_baseline_and_uses_main_thread_for_view(self) -> None:
        self.view.save_path = str(self.destination)
        self.controller.create_baseline()
        self.finish()
        previous = self.state.baseline
        saved_json = self.destination.read_bytes()
        (self.root / "test.txt").write_text("changed", encoding="utf-8")
        self.controller.check_integrity()
        self.finish()
        self.assertEqual(self.state.check_result.counts[FileStatus.CHANGED], 1)
        self.assertIs(self.state.baseline, previous)
        self.assertEqual(self.destination.read_bytes(), saved_json)
        self.assertEqual(set(self.view.thread_ids), {get_ident()})

    def test_check_scope_is_taken_from_baseline_not_new_baseline_setting(self) -> None:
        (self.root / "folder").mkdir()
        nested = self.root / "folder" / "nested.txt"
        nested.write_bytes(b"abc")
        self.view.save_path = str(self.destination)
        self.controller.create_baseline()
        self.finish()
        nested.write_bytes(b"changed")
        self.controller.set_include_subfolders(False)
        self.controller.check_integrity()
        self.finish()
        self.assertEqual(self.state.check_result.counts[FileStatus.CHANGED], 1)
        self.assertTrue(self.state.check_result.baseline.include_subfolders)

    def test_failed_check_keeps_previous_complete_result(self) -> None:
        self.view.save_path = str(self.destination)
        self.controller.create_baseline()
        self.finish()
        self.controller.check_integrity()
        self.finish()
        previous = self.state.check_result
        self.root.rename(self.directory / "moved")
        self.controller.check_integrity()
        self.finish()
        self.assertIs(self.state.check_result, previous)
        self.assertEqual(len(self.view.errors), 1)

    def test_cancelled_check_keeps_previous_complete_result(self) -> None:
        self.view.save_path = str(self.destination)
        self.controller.create_baseline()
        self.finish()
        self.controller.check_integrity()
        self.finish()
        previous = self.state.check_result

        class WaitForCancellation(IntegrityService):
            def check_integrity(self, baseline, source, cancel, on_progress):
                if not cancel.wait(3):
                    raise RuntimeError("Очікування скасування перевищено")
                raise OperationCancelled()

        self.controller.integrity_service = WaitForCancellation()
        self.controller.check_integrity()
        self.controller.check_integrity()  # Повторне натискання не створює друге завдання.
        self.controller.cancel_operation()
        self.finish()
        self.assertIs(self.state.check_result, previous)
        self.assertFalse(self.view.errors)
        self.assertIn("скасовано", self.state.status_message)

    def test_only_successful_baseline_load_clears_completed_check(self) -> None:
        self.view.save_path = str(self.destination)
        self.controller.create_baseline()
        self.finish()
        self.controller.check_integrity()
        self.finish()
        previous = self.state.check_result
        broken = self.directory / "broken.json"
        broken.write_bytes(b"broken")
        self.view.open_path = str(broken)
        self.controller.load_baseline()
        self.finish()
        self.assertIs(self.state.check_result, previous)
        self.view.open_path = str(self.destination)
        self.controller.load_baseline()
        self.finish()
        self.assertIsNone(self.state.check_result)


if __name__ == "__main__":
    unittest.main()
