"""Сканування SHA-256 та перевірка цілісності без залежності від інтерфейсу."""

import hashlib
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Callable

from app.models import Baseline, CheckResult, FileCheckResult, FileSnapshot, FileStatus, ScanIssue, ScanProgress
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
        excluded = (destination.relative_to(root).as_posix(),) if destination.is_relative_to(root) else ()
        return self._scan(root, include_subfolders, excluded, cancel, on_progress)

    def _scan(
        self, root: Path, include_subfolders: bool, excluded: tuple[str, ...],
        cancel: Event, on_progress: Callable[[ScanProgress], None],
    ) -> Baseline:
        """Єдиний алгоритм читання для створення еталона та повторної перевірки."""
        check_cancelled(cancel)
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
                                raise ValueError("Файл змінився під час читання. Повторіть сканування.")
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

    @staticmethod
    def _covering_issue(path: str, issues: dict[str, ScanIssue]) -> ScanIssue | None:
        """Помилка папки поширюється на всі невидимі під час обходу вкладені файли."""
        candidate = path
        while True:
            if candidate in issues:
                return issues[candidate]
            if "/" not in candidate:
                return None
            candidate = candidate.rsplit("/", 1)[0]

    def check_integrity(
        self, baseline: Baseline, baseline_path: Path | None,
        cancel: Event, on_progress: Callable[[ScanProgress], None],
    ) -> CheckResult:
        started = monotonic()
        check_cancelled(cancel)
        # Недоступний корінь є помилкою операції, а не видаленням усіх його файлів.
        root = DirectoryService.validate_folder(str(baseline.root_folder))
        excluded = list(baseline.excluded_paths)
        if baseline_path is not None:
            source = baseline_path.absolute()
            if source.is_relative_to(root):
                relative = source.relative_to(root).as_posix()
                if relative.casefold() not in {path.casefold() for path in excluded}:
                    excluded.append(relative)
        current = self._scan(root, baseline.include_subfolders, tuple(excluded), cancel, on_progress)
        excluded_keys = {path.casefold() for path in excluded}
        expected = {item.path.casefold(): item for item in baseline.files if item.path.casefold() not in excluded_keys}
        actual = {item.path.casefold(): item for item in current.files}
        old_issues = {item.path.casefold(): item for item in baseline.issues if item.path.casefold() not in excluded_keys}
        new_issues = {item.path.casefold(): item for item in current.issues}
        results: list[FileCheckResult] = []
        paths = expected.keys() | actual.keys() | old_issues.keys() | new_issues.keys()

        for key in sorted(paths):
            check_cancelled(cancel)
            before, after = expected.get(key), actual.get(key)
            old_issue = self._covering_issue(key, old_issues)
            new_issue = self._covering_issue(key, new_issues)
            path = (after.path if after else before.path if before else
                    new_issues[key].path if key in new_issues else old_issues[key].path)
            if new_issue is not None and after is None:
                message = f"Не вдалося перевірити шлях «{new_issue.path}»: {new_issue.message}"
                results.append(FileCheckResult(path, FileStatus.ERROR, before, after, message))
            elif old_issue is not None and before is None:
                # Без початкового хешу не можна назвати відновлений доступ новим файлом.
                message = f"Еталон не охоплює шлях «{old_issue.path}»: {old_issue.message} Порівняння неможливе."
                results.append(FileCheckResult(path, FileStatus.ERROR, before, after, message))
            elif before is None:
                results.append(FileCheckResult(path, FileStatus.ADDED, actual=after,
                                               message="Файл відсутній в еталоні."))
            elif after is None:
                results.append(FileCheckResult(path, FileStatus.DELETED, expected=before,
                                               message="Файл з еталона не знайдено під час обходу папки."))
            elif before.sha256 == after.sha256:
                results.append(FileCheckResult(path, FileStatus.UNCHANGED, before, after,
                                               "SHA-256 вмісту збігається з еталоном."))
            else:
                results.append(FileCheckResult(path, FileStatus.CHANGED, before, after,
                                               "SHA-256 вмісту відрізняється від еталона."))

        check_cancelled(cancel)
        return CheckResult(baseline, datetime.now(timezone.utc), monotonic() - started, tuple(results))
