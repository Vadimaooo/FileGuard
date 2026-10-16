"""Перевірка історії у справжніх вікнах із повторним запуском."""

import gc
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.controllers.app_controller import AppController
from app.models import AppState
from app.services.directory_service import DirectoryService
from app.services.history_storage import HistoryStorage
from app.views.main_window import MainWindow
from smoke_ui import finish_task


def main():
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary).resolve()
        root = directory / "Документи"
        root.mkdir()
        source = root / "test.txt"
        source.write_bytes(b"abc")
        history = HistoryStorage(directory / "history.sqlite3")
        window = MainWindow()
        controller = AppController(AppState(), window, DirectoryService(), history_storage=history)
        window.set_controller(controller)
        try:
            controller.start()
            finish_task(window, controller.state)
            controller.select_folder(str(root))
            with patch.object(window, "ask_save_baseline", return_value=str(directory / "baseline.json")):
                window.create_baseline_button.invoke()
            finish_task(window, controller.state)
            window.check_button.invoke()
            finish_task(window, controller.state)
            current = controller.state.check_result
            assert len(window.history_table.get_children()) == 1
            source.write_bytes(b"changed after check")
            window.notebook.select(window.history_tab)
            window.history_table.selection_set(window.history_table.get_children()[0])
            window.update()
            window.history_open_button.invoke()
            finish_task(window, controller.state)
            assert window._saved_result_window.winfo_exists()
            assert current.files[0].actual.sha256 in window._saved_result_window.content.get("1.0", "end")
            assert controller.state.check_result is current
        finally:
            window.destroy()
            del controller, window
            gc.collect()

        root.rename(directory / "Переміщені документи")
        window = MainWindow()
        controller = AppController(AppState(), window, DirectoryService(), history_storage=history)
        window.set_controller(controller)
        try:
            controller.start()
            finish_task(window, controller.state)
            assert len(window.history_table.get_children()) == 1
            assert controller.state.baseline is None
            window.history_table.selection_set(window.history_table.get_children()[0])
            window.update()
            window.history_open_button.invoke()
            finish_task(window, controller.state)
            assert "test.txt" in window._saved_result_window.content.get("1.0", "end")
            report = directory / "saved_report.txt"
            with patch.object(window, "ask_save_report", return_value=str(report)):
                window._saved_result_window.export_menu.invoke(0)
            finish_task(window, controller.state)
            assert "test.txt" in report.read_text(encoding="utf-8")
        finally:
            window.destroy()
            del controller, window
            gc.collect()
    print("Persistence UI smoke: OK (history, immutable snapshot, restart, missing source folder)")


if __name__ == "__main__":
    main()
