"""Коротка перевірка справжніх віджетів у графічному сеансі Windows."""

import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

# Прямий запуск файлу з tests/ також має знаходити пакет застосунку.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.controllers.app_controller import AppController
from app.models import AppState, FileSnapshot, FileStatus, ScanIssue
from app.services.directory_service import DirectoryService
from app.views.main_window import MainWindow


def finish_task(window, state) -> None:
    deadline = time.monotonic() + 10
    while state.busy and time.monotonic() < deadline:
        window.update()
        time.sleep(0.005)
    assert not state.busy, "Фонова операція не завершилася вчасно"
    window.update()


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve() / "Тестова папка"
        root.mkdir()
        (root / "Документ.txt").write_text("abc", encoding="utf-8")
        (root / "empty.txt").write_bytes(b"")
        destination = root / "baseline.json"
        window = MainWindow()
        try:
            state = AppState()
            controller = AppController(state, window, DirectoryService())
            window.set_controller(controller)
            controller.start()
            window.update()
            assert len(window.notebook.tabs()) == 3, "Мають бути три вкладки"
            assert not window.results_table.get_children(), "Таблиця має бути порожньою до створення еталона"
            assert all(label.cget("text") == "—" for label in window.counter_labels.values())
            assert window.create_baseline_button.instate(("disabled",))
            assert window.load_baseline_button.instate(("!disabled",))
            assert controller.select_folder(str(root))
            assert window.folder_text.get() == str(root)
            assert window.create_baseline_button.instate(("!disabled",))
            controller.set_include_subfolders(False)
            assert window.include_subfolders.get() is False

            with patch.object(window, "ask_save_baseline", return_value=str(destination)):
                controller.create_baseline()
            assert window.create_baseline_button.instate(("disabled",))
            assert window.load_baseline_button.instate(("disabled",))
            finish_task(window, state)
            assert destination.exists()
            assert state.baseline is not None
            assert len(window.results_table.get_children()) == 2
            assert window.counter_labels["Усього"].cget("text") == "2"
            assert window.counter_labels["Без змін"].cget("text") == "—"
            assert window.table_title.get() == "Файли еталона"
            assert window.check_button.instate(("!disabled",))
            for tab in window.notebook.tabs():
                window.notebook.select(tab)
                window.update()
            window.notebook.select(window.check_tab)
            for width, height in ((980, 820), (1240, 870)):
                window.geometry(f"{width}x{height}")
                window.update()
                assert window.results_table.winfo_height() > 120, "Для таблиці бракує висоти"
                assert window.check_button.winfo_rootx() + window.check_button.winfo_width() < (
                    window.winfo_rootx() + window.winfo_width()
                ), "Кнопка виходить за межі вікна"
            saved = state.baseline
        finally:
            window.destroy()

        # Нове вікно та нова модель імітують повторний запуск застосунку.
        window = MainWindow()
        try:
            state = AppState()
            controller = AppController(state, window, DirectoryService())
            window.set_controller(controller)
            controller.start()
            with patch.object(window, "ask_open_baseline", return_value=str(destination)):
                controller.load_baseline()
            finish_task(window, state)
            assert state.baseline == saved
            assert window.folder_text.get() == str(root)
            assert window.include_subfolders.get() is False
            assert len(window.results_table.get_children()) == 2

            # Зміна, додавання та видалення виконуються лише у тимчасовій тестовій папці.
            (root / "Документ.txt").write_bytes(b"xyz")
            (root / "empty.txt").unlink()
            (root / "new.txt").write_bytes(b"new")
            window.check_button.invoke()
            assert window.check_button.instate(("disabled",))
            finish_task(window, state)
            assert state.check_result.counts[FileStatus.CHANGED] == 1
            assert state.check_result.counts[FileStatus.ADDED] == 1
            assert state.check_result.counts[FileStatus.DELETED] == 1
            assert window.counter_labels["Усього"].cget("text") == "3"
            assert window.counter_labels["Змінено"].cget("text") == "1"
            assert window.counter_labels["Помилки"].cget("text") == "0"
            assert window.table_title.get() == "Результати перевірки"
            first = window.results_table.get_children()[0]
            assert window.results_table.item(first, "tags")
            window.results_table.selection_set(first)
            window.update()
            assert window.details_button.instate(("!disabled",))
            window.details_button.invoke()
            window.update()
            assert window._details_window.winfo_exists()
            window._details_window.destroy()
            window._details_window = None

            # Помилка, що була в еталоні, повинна бути видима у картці та в окремому вікні.
            state.baseline = replace(saved, issues=(ScanIssue("unknown.txt", "Немає початкового хешу"),))
            state.check_result = None
            window.render_state(state)
            window.check_button.invoke()
            finish_task(window, state)
            assert window.counter_labels["Помилки"].cget("text") == "1"
            window.issues_button.invoke()
            window.update()
            assert window._issues_window.winfo_exists()
            window._issues_window.destroy()
            window._issues_window = None
            window.geometry("980x820")
            window.update()
            assert window.check_button.winfo_rootx() + window.check_button.winfo_width() < (
                window.winfo_rootx() + window.winfo_width()
            )

            # Великий набір лише для тесту: рядки додаються порціями, а події вікна обробляються.
            state.check_result = None
            state.baseline = replace(saved, files=tuple(
                FileSnapshot(f"file_{index}.txt", "a" * 64, index, 0) for index in range(1200)
            ))
            window.render_state(state)
            assert len(window.results_table.get_children()) == 200
            heartbeat = []
            window.after(0, lambda: heartbeat.append(True))
            deadline = time.monotonic() + 5
            while len(window.results_table.get_children()) < 1200 and time.monotonic() < deadline:
                window.update()
                time.sleep(0.005)
            assert heartbeat and len(window.results_table.get_children()) == 1200
        finally:
            window.destroy()
    print("UI smoke: OK (baseline, comparison, counters, colors, details, errors, resizing, incremental table)")


if __name__ == "__main__":
    main()
