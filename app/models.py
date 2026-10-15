"""Моделі даних, які не залежать від графічного інтерфейсу."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppState:
    """Поточні параметри роботи застосунку в межах одного запуску."""

    selected_folder: Path | None = None
    include_subfolders: bool = True
    # Відсутність результату відрізняється від перевірки порожньої папки.
    # Тому до першої перевірки інтерфейс показує тире, а не вигадані нулі.
    status_message: str = "Оберіть папку для початку роботи"
