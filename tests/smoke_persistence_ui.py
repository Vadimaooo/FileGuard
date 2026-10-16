"""Qt-вікна з повторним запуском, історією, параметрами та відсутньою папкою."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.controllers.app_controller import AppController
from app.models import AppState, FileStatus
from app.services.directory_service import DirectoryService
from app.services.history_storage import HistoryStorage
from app.services.settings_storage import SettingsStorage
from app.views.main_window import MainWindow
from qt_helpers import application, dispose, finish_task, pump


def main():
    app = application()
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary).resolve()
        source = directory / "Документи"
        source.mkdir()
        (source / "test.txt").write_bytes(b"abc")
        history = HistoryStorage(directory / "history.sqlite3")
        settings = SettingsStorage(directory / "settings.json")

        def create():
            window = MainWindow()
            controller = AppController(AppState(), window, DirectoryService(), history_storage=history,
                                       settings_storage=settings)
            window.set_controller(controller)
            window.show()
            controller.start()
            finish_task(window, controller.state)
            return window, controller

        window, controller = create()
        try:
            controller.select_folder(str(source))
            with patch.object(window, "ask_save_baseline", return_value=str(directory / "baseline.json")):
                window.create_baseline_button.click()
            finish_task(window, controller.state)
            window.check_button.click()
            finish_task(window, controller.state)
            current = controller.state.check_result
            assert window.history_model.rowCount() == 1
            (source / "test.txt").write_bytes(b"changed after check")
            window.navigation[1].click()
            window.history_table.selectRow(0)
            window.history_open_button.click()
            finish_task(window, controller.state)
            pump(80)
            assert current.files[0].actual.sha256 in window._saved_result_window.content.toPlainText()
            assert controller.state.check_result is current
            controller.set_include_subfolders(False)
            controller.set_exclusion_patterns(["*.tmp", "cache/"])
            controller.set_status_filter(FileStatus.CHANGED.value)
            controller.set_glass_enabled(False)
            window.resize(1100, 850)
            window.navigation[2].click()
            window.save_settings_button.click()
            finish_task(window, controller.state)
            assert settings.load().window_size == (1100, 850)
        finally:
            dispose(window)
        source.rename(directory / "Переміщені документи")
        window, controller = create()
        try:
            state = controller.state
            assert state.selected_folder == source
            assert state.baseline is None and state.check_result is None
            assert not state.include_subfolders and not state.glass_enabled
            assert state.exclusion_patterns == ("*.tmp", "cache/")
            assert state.status_filter == FileStatus.CHANGED
            assert window.get_window_size() == (1100, 850)
            assert window.history_model.rowCount() == 1
            window.navigation[1].click()
            window.history_table.selectRow(0)
            window.history_open_button.click()
            finish_task(window, state)
            pump(80)
            assert "test.txt" in window._saved_result_window.content.toPlainText()
            report = directory / "saved.txt"
            with patch.object(window, "ask_save_report", return_value=str(report)):
                window._saved_result_window.export_menu.actions()[0].trigger()
            finish_task(window, state)
            assert current.files[0].actual.sha256 in report.read_text(encoding="utf-8")
            controller.request_close()
            finish_task(window, state)
            assert not window.isVisible()
        finally:
            dispose(window)
    print("Qt persistence smoke: OK (immutable history, restart, settings, glass preference, TXT, missing source, normal close)")


if __name__ == "__main__":
    main()
