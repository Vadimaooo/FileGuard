"""Моделі даних, які не залежать від графічного інтерфейсу."""

from dataclasses import dataclass, field
from collections import Counter
from datetime import datetime
from enum import Enum
from pathlib import Path


@dataclass(frozen=True)
class FileSnapshot:
    """Стан одного файлу; шлях зберігається відносно кореневої папки."""

    path: str
    sha256: str
    size: int
    modified_ns: int


@dataclass(frozen=True)
class ScanIssue:
    """Шлях, який не вдалося включити до еталона, та причина."""

    path: str
    message: str


@dataclass(frozen=True)
class Baseline:
    """Незмінний знімок папки, придатний до збереження та порівняння."""

    root_folder: Path
    created_at: datetime
    include_subfolders: bool
    files: tuple[FileSnapshot, ...]
    issues: tuple[ScanIssue, ...] = ()
    excluded_paths: tuple[str, ...] = ()
    exclusion_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScanProgress:
    """Повідомлення фонового потоку без посилань на графічні віджети."""

    processed_files: int = 0
    processed_bytes: int = 0
    current_path: str = ""


class FileStatus(str, Enum):
    """Статус стосується вмісту файлу, а не лише його дати або розміру."""

    UNCHANGED = "Без змін"
    CHANGED = "Змінено"
    ADDED = "Додано"
    DELETED = "Видалено"
    ERROR = "Помилка"


@dataclass(frozen=True)
class FileCheckResult:
    """Результат для одного шляху з даними для пояснення в інтерфейсі."""

    path: str
    status: FileStatus
    expected: FileSnapshot | None = None
    actual: FileSnapshot | None = None
    message: str = ""


@dataclass(frozen=True)
class CheckResult:
    """Лише завершена перевірка; скасована операція не створює цього результату."""

    baseline: Baseline
    completed_at: datetime
    duration_seconds: float
    files: tuple[FileCheckResult, ...]

    @property
    def counts(self) -> Counter[FileStatus]:
        return Counter(item.status for item in self.files)


@dataclass(frozen=True)
class HistoryEntry:
    """Короткі відомості для списку без завантаження повного звіту."""

    identifier: str
    completed_at: datetime
    root_folder: Path
    duration_seconds: float
    counts: dict[FileStatus, int]


@dataclass(frozen=True)
class AppSettings:
    last_folder: Path | None = None
    include_subfolders: bool = True
    exclusion_patterns: tuple[str, ...] = ()
    status_filter: FileStatus | None = None
    window_size: tuple[int, int] | None = None
    glass_enabled: bool = True


@dataclass
class AppState:
    """Поточні параметри роботи застосунку в межах одного запуску."""

    selected_folder: Path | None = None
    include_subfolders: bool = True
    exclusion_patterns: tuple[str, ...] = ()
    status_filter: FileStatus | None = None
    history_available: bool = False
    history_entries: tuple[HistoryEntry, ...] = ()
    window_size: tuple[int, int] | None = None
    glass_enabled: bool = True
    baseline: Baseline | None = None
    baseline_path: Path | None = None
    check_result: CheckResult | None = None
    busy: bool = False
    cancel_requested: bool = False
    progress: ScanProgress = field(default_factory=ScanProgress)
    # Створення еталона ще не є перевіркою поточного вмісту на незмінність.
    # Показники порівняння залишаються невизначеними до відповідної операції.
    status_message: str = "Оберіть папку для початку роботи"
