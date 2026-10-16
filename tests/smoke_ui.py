"""Наскрізна перевірка справжніх віджетів Qt та сигналів користувацьких дій."""

import csv
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from app.controllers.app_controller import AppController
from app.models import AppState, FileStatus, FileSnapshot, ScanIssue
from app.services.directory_service import DirectoryService
from app.views.main_window import MainWindow
from qt_helpers import application, dispose, finish_task, pump


def main():
    app = application()
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary).resolve()
        source = directory / "Тестова папка"
        source.mkdir()
        (source / "Документ.txt").write_bytes(b"before")
        (source / "empty.txt").write_bytes(b"")
        (source / "ignored.tmp").write_bytes(b"ignored")
        destination = directory / "baseline.json"
        window = MainWindow()
        state = AppState()
        controller = AppController(state, window, DirectoryService())
        window.set_controller(controller)
        window.show()
        try:
            controller.start()
            pump()
            assert not window.check_button.isEnabled()
            assert all(value.text() == "—" for value in window.counter_labels.values())
            with patch.object(window, "ask_directory", return_value=str(source)):
                window.choose_button.click()
            assert state.selected_folder == source
            window.navigation[2].click()
            assert window.pages.currentIndex() == 2
            window.exclusions_input.setPlainText("*.tmp")
            window.apply_exclusions_button.click()
            assert state.exclusion_patterns == ("*.tmp",)
            QTest.mouseClick(window.settings_subfolders_check, Qt.MouseButton.LeftButton)
            assert not state.include_subfolders and not window.subfolders_check.isChecked()
            window.navigation[0].click()
            with patch.object(window, "ask_save_baseline", return_value=str(destination)):
                window.create_baseline_button.click()
            assert not window.choose_button.isEnabled()
            finish_task(window, state)
            assert len(state.baseline.files) == 2
            assert window.results_model.rowCount() == 2
            assert window.counter_labels["Усього"].text() == "2"
            window.exclusions_input.setPlainText("draft")
            controller.set_status_filter("Усі статуси")
            assert window.exclusions_input.toPlainText() == "draft"
            (source / "Документ.txt").write_bytes(b"after")
            (source / "empty.txt").unlink()
            (source / "Новий.txt").write_bytes(b"new")
            window.check_button.click()
            finish_task(window, state)
            result = state.check_result
            assert [result.counts[status] for status in FileStatus] == [0, 1, 1, 1, 0]
            assert window.results_model.rowCount() == 3
            window.status_filter.setCurrentText(FileStatus.CHANGED.value)
            pump()
            assert state.status_filter == FileStatus.CHANGED
            assert window.results_model.rowCount() == 1
            assert window.counter_labels["Усього"].text() == "3"
            window.results_table.selectRow(0)
            window.details_button.click()
            pump()
            assert result.files[-1].actual is not None or any(item.actual for item in result.files)
            detail = window._detail_windows[-1].findChild(type(window.exclusions_input))
            changed = next(item for item in result.files if item.status == FileStatus.CHANGED)
            assert changed.actual.sha256 in detail.toPlainText()
            report = directory / "report.csv"
            with patch.object(window, "ask_save_report", return_value=str(report)):
                window.export_menu.actions()[1].trigger()
            finish_task(window, state)
            with report.open(encoding="utf-8-sig", newline="") as stream:
                assert len(list(csv.DictReader(stream, delimiter=";"))) == 3
            window.status_filter.setCurrentText(FileStatus.ERROR.value)
            assert window.results_model.rowCount() == 0
            assert window.results_stack.currentIndex() == 1
            state.check_result = None
            state.baseline = replace(state.baseline, issues=(ScanIssue("locked.txt", "Немає доступу"),))
            controller.view.render_state(state)
            assert not window.issues_button.isHidden()
            window.issues_button.click()
            pump()
            assert "Немає доступу" in window._detail_windows[-1].findChild(type(window.exclusions_input)).toPlainText()
            rows = tuple(FileSnapshot(f"file_{i:04}.txt", "a" * 64, i, 0) for i in range(1200))
            state.baseline = replace(state.baseline, files=rows, issues=())
            window.render_state(state)
            assert window.results_model.rowCount() == 1200
            window.apply_window_size((1080, 820))
            window.navigation[2].click()
            pump()
            assert window.save_settings_button.isVisible()
        finally:
            dispose(window)
    print("Qt UI smoke: OK (signals, baseline, comparison, filters, details, errors, CSV, 1200 rows, resizing)")


if __name__ == "__main__":
    main()
