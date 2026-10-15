"""Перевірка папки, яку користувач обирає для подальшого контролю."""

from pathlib import Path


class DirectoryService:
    """Перевіряє шлях без сканування або зміни вмісту папки."""

    @staticmethod
    def validate_folder(value: str) -> Path:
        if not value or not value.strip():
            raise ValueError("Шлях до папки не може бути порожнім.")

        try:
            # strict=True виявляє видалену папку ще до оновлення моделі.
            folder = Path(value).expanduser().resolve(strict=True)
            if not folder.is_dir():
                raise ValueError("Обраний шлях веде до файлу. Оберіть папку.")
            return folder
        except FileNotFoundError as error:
            raise ValueError("Папку не знайдено. Можливо, її видалено або переміщено.") from error
        except PermissionError as error:
            raise ValueError("Немає дозволу на доступ до обраної папки.") from error
