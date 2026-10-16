"""Перевірка формату JSON та атомарне збереження еталонів."""

import json
import os
import re
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path, PurePosixPath
from threading import Event
from typing import Any

from app.models import Baseline, FileSnapshot, ScanIssue
from app.paths import application_directory
from app.services.integrity_service import check_cancelled
from app.services.exclusions import ExclusionRules


class BaselineStorage:
    """Сховище з явною версією формату; JSON не виконується як код."""

    MAX_JSON_BYTES = 64 * 1024 * 1024

    @property
    def default_directory(self) -> Path:
        # Розташування не залежить від папки, з якої запущено main.py.
        return application_directory() / "data"

    @staticmethod
    def prepare_destination(value: str) -> Path:
        path = Path(value).expanduser()
        parent = path.parent.resolve(strict=True)
        destination = parent / path.name
        if destination.suffix.lower() != ".json":
            raise ValueError("Назва файлу еталона повинна мати розширення .json.")
        if not parent.is_dir() or not path.name:
            raise ValueError("Оберіть наявну папку для збереження еталона.")
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise ValueError("Еталон потрібно зберігати у звичайний файл, а не папку або посилання.")
        return destination

    @staticmethod
    def _document(baseline: Baseline) -> dict[str, Any]:
        return {
            "application": "FileGuard",
            "schema_version": 2,
            "algorithm": "SHA-256",
            "created_at": baseline.created_at.isoformat(),
            "root_folder": str(baseline.root_folder),
            "include_subfolders": baseline.include_subfolders,
            "excluded_paths": list(baseline.excluded_paths),
            "exclusion_patterns": list(baseline.exclusion_patterns),
            "files": [asdict(item) for item in baseline.files],
            "issues": [asdict(item) for item in baseline.issues],
        }

    def save(self, baseline: Baseline, destination: Path, cancel: Event) -> None:
        check_cancelled(cancel)
        document = self._document(baseline)
        self._validate(document)
        temporary: Path | None = None
        try:
            # Тимчасовий файл у тій самій папці дозволяє замінити еталон атомарно.
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=destination.parent,
                prefix=".fileguard-", suffix=".tmp", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(document, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                if stream.tell() > self.MAX_JSON_BYTES:
                    raise ValueError("Еталон перевищує підтримуваний розмір 64 МіБ.")
                os.fsync(stream.fileno())
            check_cancelled(cancel)
            # Старий файл залишається цілим у разі помилки запису або скасування.
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"JSON містить повторюване поле: {key}.")
            result[key] = value
        return result

    @staticmethod
    def _relative_path(value: Any) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("Шлях файлу в еталоні має бути непорожнім текстом.")
        path = PurePosixPath(value)
        if (not path.parts or path.is_absolute() or path.as_posix() != value or "\\" in value or ":" in value
                or any(ord(char) < 32 for char in value)
                or any(part in (".", "..") or part.endswith((" ", ".")) for part in path.parts)):
            raise ValueError(f"Неприпустимий відносний шлях в еталоні: {value!r}.")
        return value

    @staticmethod
    def _integer(value: Any, nonnegative: bool = False) -> int:
        if type(value) is not int or (nonnegative and not 0 <= value <= 2**63 - 1):
            raise ValueError("Некоректний розмір або час зміни файлу в еталоні.")
        return value

    def _validate(self, document: Any) -> Baseline:
        if not isinstance(document, dict):
            raise ValueError("Кореневим елементом еталона має бути об'єкт JSON.")
        if document.get("application") != "FileGuard":
            raise ValueError("Цей файл не є еталоном FileGuard.")
        if type(document.get("schema_version")) is not int or document["schema_version"] not in (1, 2):
            raise ValueError("Непідтримувана версія формату еталона.")
        if document.get("algorithm") != "SHA-256":
            raise ValueError("Підтримуються лише еталони SHA-256.")
        recursive = document.get("include_subfolders")
        if type(recursive) is not bool:
            raise ValueError("Параметр вкладених папок повинен мати значення true або false.")
        root_value = document.get("root_folder")
        if not isinstance(root_value, str) or not root_value or "\x00" in root_value:
            raise ValueError("В еталоні відсутній коректний шлях до кореневої папки.")
        root = Path(root_value)
        if not root.is_absolute():
            raise ValueError("Коренева папка еталона повинна мати абсолютний шлях.")
        try:
            created = datetime.fromisoformat(document["created_at"])
            if created.tzinfo is None:
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Некоректна дата створення еталона або відсутній часовий пояс.") from error

        raw_files, raw_issues, raw_excluded = (
            document.get("files"), document.get("issues"), document.get("excluded_paths")
        )
        if not all(isinstance(items, list) for items in (raw_files, raw_issues, raw_excluded)):
            raise ValueError("Списки файлів, помилок і виключених шляхів мають бути масивами JSON.")
        excluded = tuple(self._relative_path(value) for value in raw_excluded)
        excluded_keys = {value.casefold() for value in excluded}
        patterns = document.get("exclusion_patterns", []) if document["schema_version"] == 1 else document.get("exclusion_patterns")
        rules = ExclusionRules(patterns)
        if document["schema_version"] == 1 and rules.patterns:
            raise ValueError("Правила виключення потребують формату еталона версії 2.")
        if len(excluded_keys) != len(excluded):
            raise ValueError("Список виключень містить повторювані шляхи.")
        files: list[FileSnapshot] = []
        seen: set[str] = set()
        for item in raw_files:
            if not isinstance(item, dict):
                raise ValueError("Запис про файл повинен бути об'єктом JSON.")
            path = self._relative_path(item.get("path"))
            if path.casefold() in seen or ExclusionRules.under_path(path, excluded) or rules.matches(path):
                raise ValueError("Повторюваний шлях або файл одночасно присутній у списку виключень.")
            if not recursive and "/" in path:
                raise ValueError("Еталон без вкладених папок містить вкладений шлях.")
            digest = item.get("sha256")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                raise ValueError(f"Некоректний SHA-256 для файлу: {path}.")
            files.append(FileSnapshot(path, digest.lower(), self._integer(item.get("size"), nonnegative=True),
                                      self._integer(item.get("modified_ns"))))
            seen.add(path.casefold())
        issues: list[ScanIssue] = []
        for item in raw_issues:
            if not isinstance(item, dict) or not isinstance(item.get("message"), str) or not item["message"]:
                raise ValueError("Некоректний запис про помилку сканування.")
            path = self._relative_path(item.get("path"))
            if path.casefold() in seen or ExclusionRules.under_path(path, excluded) or rules.matches(path):
                raise ValueError("Список помилок містить повторюваний або суперечливий шлях.")
            issues.append(ScanIssue(path, item["message"]))
            seen.add(path.casefold())
        return Baseline(root, created, recursive, tuple(files), tuple(issues), excluded, rules.patterns)

    def load(self, source: Path, cancel: Event) -> Baseline:
        check_cancelled(cancel)
        with source.open("rb") as stream:
            raw = stream.read(self.MAX_JSON_BYTES + 1)
        if len(raw) > self.MAX_JSON_BYTES:
            raise ValueError("Файл еталона перевищує підтримуваний розмір 64 МіБ.")
        try:
            document = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=self._unique_object)
        except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError("Файл не містить коректного JSON у кодуванні UTF-8.") from error
        check_cancelled(cancel)
        baseline = self._validate(document)
        check_cancelled(cancel)
        return baseline
