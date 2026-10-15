"""Створення файлового еталона SHA-256 без залежності від інтерфейсу."""

import hashlib
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Callable

from app.models import Baseline, FileSnapshot, ScanIssue, ScanProgress
from app.services.directory_service import DirectoryService


class OperationCancelled(Exception):
    """Користувач скасував операцію до її завершення."""


def check_cancelled(cancel: Event) -> None:
    if cancel.is_set():
        raise OperationCancelled("Операцію скасовано.")


class IntegrityService:
    """Читає файли блоками, не змінюючи їхнього вмісту."""

    CHUNK_SIZE = 1024 * 1024

    @staticmethod
    def _signature(info: os.stat_result) -> tuple[int, int, int, int]:
        return info.st_size, info.st_mtime_ns, info.st_ino, info.st_dev

    def create_baseline(
        self,
        root: Path,
        include_subfolders: bool,
        destination: Path,
        cancel: Event,
        on_progress: Callable[[ScanProgress], None],
    ) -> Baseline:
        root = DirectoryService.validate_folder(str(root))
        check_cancelled(cancel)
        excluded = (destination.relative_to(root).as_posix(),) if destination.is_relative_to(root) else ()
        excluded_keys = {path.casefold() for path in excluded}
        files: list[FileSnapshot] = []
        issues: list[ScanIssue] = []
        pending = [root]
        processed_bytes = 0
        last_update = 0.0

        while pending:
            check_cancelled(cancel)
            folder = pending.pop()
            try:
                # Не накопичуємо список усіх шляхів: пам'ять потрібна лише для знімків.
                with os.scandir(folder) as entries:
                    for entry in entries:
                        check_cancelled(cancel)
                        path = Path(entry.path)
                        relative = path.relative_to(root).as_posix()
                        if relative.casefold() in excluded_keys:
                            continue
                        try:
                            info = entry.stat(follow_symlinks=False)
                            is_directory = stat.S_ISDIR(info.st_mode)
                            is_junction = is_directory and bool(
                                getattr(info, "st_file_attributes", 0)
                                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                            )
                            # Посилання та junction можуть вивести сканування за межі папки.
                            if entry.is_symlink() or is_junction:
                                issues.append(ScanIssue(relative, "Посилання пропущено; його вміст не сканувався."))
                                continue
                            if is_directory:
                                if include_subfolders:
                                    pending.append(path)
                                continue
                            if not stat.S_ISREG(info.st_mode):
                                issues.append(ScanIssue(relative, "Спеціальний файл пропущено."))
                                continue

                            digest = hashlib.sha256()
                            with path.open("rb") as stream:
                                before = os.fstat(stream.fileno())
                                while True:
                                    check_cancelled(cancel)
                                    chunk = stream.read(self.CHUNK_SIZE)
                                    if not chunk:
                                        break
                                    digest.update(chunk)
                                    processed_bytes += len(chunk)
                                    if monotonic() - last_update >= 0.1:
                                        on_progress(ScanProgress(len(files), processed_bytes, relative))
                                        last_update = monotonic()
                                after = os.fstat(stream.fileno())
                            current = path.stat(follow_symlinks=False)
                            # Не зберігаємо суміш двох станів файлу, який змінювався під час читання.
                            if self._signature(before) != self._signature(after) or self._signature(after) != self._signature(current):
                                raise ValueError("Файл змінився під час читання. Повторіть створення еталона.")
                            files.append(FileSnapshot(relative, digest.hexdigest(), after.st_size, after.st_mtime_ns))
                        except (OSError, ValueError) as error:
                            issues.append(ScanIssue(relative, f"Не вдалося прочитати: {error}"))
                        on_progress(ScanProgress(len(files), processed_bytes, relative))
            except OSError as error:
                if folder == root:
                    raise ValueError(f"Неможливо відкрити обрану папку: {error}") from error
                issues.append(ScanIssue(folder.relative_to(root).as_posix(), f"Не вдалося відкрити папку: {error}"))

        check_cancelled(cancel)
        return Baseline(
            root_folder=root,
            created_at=datetime.now(timezone.utc),
            include_subfolders=include_subfolders,
            files=tuple(sorted(files, key=lambda item: item.path.casefold())),
            issues=tuple(sorted(issues, key=lambda item: item.path.casefold())),
            excluded_paths=excluded,
        )
