"""Перевірка та атомарне збереження локальних параметрів застосунку."""

import json
from pathlib import Path

from app.models import AppSettings, FileStatus
from app.services.atomic_file import atomic_text_file
from app.services.baseline_storage import BaselineStorage
from app.services.exclusions import ExclusionRules


class SettingsStorage:
    MAX_BYTES = 1024 * 1024

    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def _document(settings: AppSettings):
        return {"application": "FileGuard", "version": 1,
                "last_folder": str(settings.last_folder) if settings.last_folder else None,
                "include_subfolders": settings.include_subfolders,
                "exclusion_patterns": list(settings.exclusion_patterns),
                "status_filter": settings.status_filter.value if settings.status_filter else None,
                "window_size": list(settings.window_size) if settings.window_size else None}

    @staticmethod
    def _validate(document):
        if (not isinstance(document, dict) or document.get("application") != "FileGuard"
                or type(document.get("version")) is not int or document["version"] != 1):
            raise ValueError("Непідтримуваний формат налаштувань.")
        folder = document.get("last_folder")
        if folder is not None and (not isinstance(folder, str) or len(folder) > 32767
                                   or any(ord(c) < 32 for c in folder) or not Path(folder).is_absolute()):
            raise ValueError("Некоректна остання папка в налаштуваннях.")
        recursive = document.get("include_subfolders")
        if type(recursive) is not bool:
            raise ValueError("Параметр вкладених папок повинен бути логічним значенням.")
        patterns = ExclusionRules.validate(document.get("exclusion_patterns"))
        status = document.get("status_filter")
        status = FileStatus(status) if status is not None else None
        size = document.get("window_size")
        if size is not None and (not isinstance(size, list) or len(size) != 2
                                 or any(type(value) is not int for value in size)
                                 or not (980 <= size[0] <= 10000 and 820 <= size[1] <= 10000)):
            raise ValueError("Некоректний розмір вікна в налаштуваннях.")
        # Невідомі поля попередніх версій не заважають відновленню чинних параметрів.
        return AppSettings(Path(folder) if folder else None, recursive, patterns, status, tuple(size) if size else None)

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        with self.path.open("rb") as stream:
            raw = stream.read(self.MAX_BYTES + 1)
        if len(raw) > self.MAX_BYTES:
            raise ValueError("Файл налаштувань завеликий.")
        document = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=BaselineStorage._unique_object)
        return self._validate(document)

    def save(self, settings: AppSettings, cancel):
        document = self._document(settings)
        self._validate(document)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise ValueError("Файл налаштувань не може бути посиланням або папкою.")
        with atomic_text_file(self.path, cancel) as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
