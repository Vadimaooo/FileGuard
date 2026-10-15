"""Координація інтерфейсу, стану застосунку та файлових операцій."""

from typing import Protocol

from app.models import AppState
from app.services.directory_service import DirectoryService


class AppView(Protocol):
    """Мінімальний контракт вікна, потрібний контролеру."""

    def render_state(self, state: AppState) -> None: ...

    def ask_directory(self, initial_directory: str | None) -> str: ...

    def show_error(self, title: str, message: str) -> None: ...


class AppController:
    """Обробляє команди; не створює віджетів і не обчислює хешів."""

    def __init__(
        self, state: AppState, view: AppView, directory_service: DirectoryService
    ) -> None:
        self.state = state
        self.view = view
        self.directory_service = directory_service

    def start(self) -> None:
        """Показати початковий стан застосунку."""
        self.view.render_state(self.state)

    def choose_folder(self) -> None:
        """Отримати вибір із діалогу та передати шлях на перевірку сервісу."""
        initial = str(self.state.selected_folder) if self.state.selected_folder else None
        selected = self.view.ask_directory(initial)
        if not selected:
            # Скасування діалогу не змінює вже вибрану папку.
            return
        self.select_folder(selected)

    def select_folder(self, folder: str) -> bool:
        """Оновити модель лише після успішної перевірки шляху."""
        try:
            resolved = self.directory_service.validate_folder(folder)
        except (OSError, ValueError, RuntimeError) as error:
            self.view.show_error("Не вдалося обрати папку", str(error))
            return False

        self.state.selected_folder = resolved
        self.state.status_message = "Папку обрано · перевірку ще не виконано"
        self.view.render_state(self.state)
        return True

    def set_include_subfolders(self, enabled: bool) -> None:
        """Зберегти параметр у моделі та синхронізувати обидві вкладки."""
        self.state.include_subfolders = bool(enabled)
        self.view.render_state(self.state)
