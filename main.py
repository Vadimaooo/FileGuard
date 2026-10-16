"""Точка входу в застосунок FileGuard."""

from app.controllers.app_controller import AppController
from app.models import AppState
from app.services.baseline_storage import BaselineStorage
from app.services.directory_service import DirectoryService
from app.services.integrity_service import IntegrityService
from app.views.main_window import MainWindow
from app.paths import application_directory
from app.services.history_storage import HistoryStorage
from app.services.settings_storage import SettingsStorage
from PySide6.QtWidgets import QApplication
import sys


def main() -> None:
    """Створити компоненти MVC та запустити цикл оброблення подій."""
    application = QApplication(sys.argv)
    application.setApplicationName("FileGuard")
    application.setStyle("Fusion")
    state = AppState()
    window = MainWindow()
    # Залежності поєднуємо лише тут: сервіс нічого не знає про графічне вікно.
    root = application_directory()
    controller = AppController(state, window, DirectoryService(),
                               IntegrityService((root / "data", root / "reports")), BaselineStorage(),
                               HistoryStorage(root / "data" / "history.sqlite3"),
                               settings_storage=SettingsStorage(root / "data" / "settings.json"))
    window.set_controller(controller)
    window.show()
    controller.start()
    sys.exit(application.exec())


if __name__ == "__main__":
    main()
