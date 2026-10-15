"""Точка входу в застосунок FileGuard."""

from app.controllers.app_controller import AppController
from app.models import AppState
from app.services.directory_service import DirectoryService
from app.views.main_window import MainWindow


def main() -> None:
    """Створити компоненти MVC та запустити цикл оброблення подій."""
    state = AppState()
    window = MainWindow()
    # Залежності поєднуємо лише тут: сервіс нічого не знає про графічне вікно.
    controller = AppController(state, window, DirectoryService())
    window.set_controller(controller)
    controller.start()
    window.mainloop()


if __name__ == "__main__":
    main()
