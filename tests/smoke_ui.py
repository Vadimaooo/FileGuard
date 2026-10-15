"""Коротка перевірка справжніх віджетів у графічному сеансі Windows."""

import sys
from pathlib import Path

# Прямий запуск файлу з tests/ також має знаходити пакет застосунку.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.controllers.app_controller import AppController
from app.models import AppState
from app.services.directory_service import DirectoryService
from app.views.main_window import MainWindow


def main() -> None:
    window = MainWindow()
    try:
        state = AppState()
        controller = AppController(state, window, DirectoryService())
        window.set_controller(controller)
        controller.start()
        window.update()
        assert len(window.notebook.tabs()) == 3, "Мають бути три вкладки"
        assert not window.results_table.get_children(), "Таблиця не повинна містити вигадані результати"
        assert all(label.cget("text") == "—" for label in window.counter_labels.values())
        assert controller.select_folder(str(PROJECT_ROOT / "demo_files"))
        window.update()
        assert window.folder_text.get() == str(PROJECT_ROOT / "demo_files")
        controller.set_include_subfolders(False)
        assert window.include_subfolders.get() is False
        for button in (window.create_baseline_button, window.load_baseline_button,
                       window.check_button, window.export_button):
            assert button.instate(("disabled",)), "Майбутні операції мають бути неактивні"
        for tab in window.notebook.tabs():
            window.notebook.select(tab)
            window.update()
        window.notebook.select(window.check_tab)
        for width, height in ((980, 780), (1240, 870)):
            window.geometry(f"{width}x{height}")
            window.update()
            assert window.results_table.winfo_height() > 120, "Для таблиці бракує висоти"
            assert window.check_button.winfo_rootx() + window.check_button.winfo_width() < (
                window.winfo_rootx() + window.winfo_width()
            ), "Кнопка виходить за межі вікна"
            assert window.choose_button.winfo_width() > 100
        print("UI smoke: OK (tabs, selection, settings, disabled actions, resizing)")
    finally:
        window.destroy()


if __name__ == "__main__":
    main()
