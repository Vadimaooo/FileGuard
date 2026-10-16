"""Регресії Qt: повторні фонові перевірки, помилки й закриття під навантаженням."""

import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QPushButton

from app.controllers.app_controller import AppController
from app.models import AppState, FileStatus
from app.services.directory_service import DirectoryService
from app.services.integrity_service import IntegrityService, OperationCancelled
from app.services.settings_storage import SettingsStorage
from app.views.main_window import MainWindow
from qt_helpers import application, dispose, finish_task, pump


class QtUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = application()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        source = self.root / "Документи"
        source.mkdir()
        (source / "test.txt").write_bytes(b"before")
        baseline = IntegrityService().create_baseline(source, True, self.root / "b.json", Event(), lambda p: None)
        self.window = MainWindow()
        self.addCleanup(dispose, self.window)
        self.state = AppState(selected_folder=source, baseline=baseline, glass_enabled=False)
        self.settings = SettingsStorage(self.root / "settings.json")
        self.controller = AppController(self.state, self.window, DirectoryService(), settings_storage=self.settings)
        self.window.set_controller(self.controller)
        self.window.show()
        self.window.render_state(self.state)
        self.errors = []
        self.error_patch = patch.object(self.window, "show_error", side_effect=lambda *args: self.errors.append(args))
        self.error_patch.start()
        self.addCleanup(self.error_patch.stop)
        self.controller.start()
        finish_task(self.window, self.state)
        self.state.selected_folder = source
        self.state.baseline = baseline
        self.state.glass_enabled = False
        self.window.render_state(self.state)
        pump()

    def test_repeated_background_checks_and_status_painting(self):
        for index in range(15):
            (self.state.selected_folder / "test.txt").write_bytes(b"before" if index % 2 else b"after")
            self.window.check_button.click()
            finish_task(self.window, self.state)
            status = FileStatus.UNCHANGED if index % 2 else FileStatus.CHANGED
            self.assertEqual(self.state.check_result.files[0].status, status)
            self.assertEqual(self.window.results_model.index(0, 1).data(), status.value)
        self.assertEqual(self.errors, [])

    def test_bad_json_keeps_previous_baseline_and_shows_error(self):
        broken = self.root / "broken.json"
        broken.write_bytes(b"broken")
        before = self.state.baseline
        with patch.object(self.window, "ask_open_baseline", return_value=str(broken)):
            self.window.load_baseline_button.click()
        finish_task(self.window, self.state)
        self.assertIs(self.state.baseline, before)
        self.assertTrue(self.window.check_button.isEnabled())
        self.assertEqual(len(self.errors), 1)

    def test_settings_rounded_corner_does_not_reveal_dark_system_palette(self):
        self.window.navigation[2].click()
        pump()
        page = self.window.pages.widget(2).widget()
        position = page.mapTo(self.window, QPoint(1, 1))
        rendered = self.window.grab()
        ratio = rendered.devicePixelRatio()
        corner = rendered.toImage().pixelColor(round(position.x() * ratio), round(position.y() * ratio))
        self.assertGreater(corner.lightness(), 180)

    def test_window_close_cancels_worker_and_saves_preferences_before_exit(self):
        def delayed(*args):
            self.controller._cancel.wait(3)
            raise OperationCancelled()
        with patch.object(self.controller.integrity_service, "check_integrity", side_effect=delayed):
            self.window.check_button.click()
            close_button = next(button for button in self.window.findChildren(QPushButton)
                                if button.accessibleName() == "Закрити")
            close_button.click()
            self.assertTrue(self.state.cancel_requested)
            finish_task(self.window, self.state)
        self.assertFalse(self.window.isVisible())
        self.assertIsNone(self.state.check_result)
        self.assertEqual(self.settings.load().last_folder, self.state.selected_folder)
        self.assertFalse(self.settings.load().glass_enabled)
        self.assertEqual(self.errors, [])
