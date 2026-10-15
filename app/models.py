"""Моделі даних, які не залежать від графічного інтерфейсу."""

from dataclasses import dataclass, field
from datetime import datetime
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


@dataclass(frozen=True)
class ScanProgress:
    """Повідомлення фонового потоку без посилань на віджети tkinter."""

    processed_files: int = 0
    processed_bytes: int = 0
    current_path: str = ""


@dataclass
class AppState:
    """Поточні параметри роботи застосунку в межах одного запуску."""

    selected_folder: Path | None = None
    include_subfolders: bool = True
    baseline: Baseline | None = None
    baseline_path: Path | None = None
    busy: bool = False
    cancel_requested: bool = False
    progress: ScanProgress = field(default_factory=ScanProgress)
    # Створення еталона ще не є перевіркою поточного вмісту на незмінність.
    # Показники порівняння залишаються невизначеними до відповідної операції.
    status_message: str = "Оберіть папку для початку роботи"
