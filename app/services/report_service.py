"""Експорт повного результату з UTF-8 та захистом початкових файлів."""

import csv
from pathlib import Path

from app.models import CheckResult, FileStatus
from app.services.atomic_file import atomic_text_file
from app.services.exclusions import ExclusionRules
from app.services.integrity_service import check_cancelled
from app.services.report_codec import report_text


class ReportService:
    def __init__(self, directory: Path | None = None):
        self.default_directory = directory or Path(__file__).resolve().parents[2] / "reports"

    @staticmethod
    def safe_cell(value):
        # Excel не повинен виконувати ім'я файлу або пояснення як формулу.
        if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@"))
                                       or value.startswith(("\t", "\r", "\n"))):
            return "'" + value
        return value

    def export(self, result: CheckResult, selected: str, extension: str, cancel) -> Path:
        destination = Path(selected).expanduser()
        destination = destination.parent.resolve(strict=True) / destination.name
        if extension not in ("txt", "csv") or destination.suffix.lower() != "." + extension:
            raise ValueError(f"Оберіть назву з розширенням .{extension}.")
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise ValueError("Звіт потрібно зберігати у звичайний файл.")
        root = result.baseline.root_folder.resolve()
        if destination.is_relative_to(root):
            relative = destination.relative_to(root).as_posix()
            if not ExclusionRules.under_path(relative, result.baseline.excluded_paths):
                raise ValueError("Збережіть звіт поза папкою перевірки або у виключеній службовій папці reports.")
        encoding = "utf-8-sig" if extension == "csv" else "utf-8"
        with atomic_text_file(destination, cancel, encoding=encoding) as stream:
            if extension == "txt":
                text = report_text(result)
                for start in range(0, len(text), 65536):
                    check_cancelled(cancel)
                    stream.write(text[start:start + 65536])
            else:
                self._csv(stream, result, cancel)
        return destination

    def _csv(self, stream, result: CheckResult, cancel):
        writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
        writer.writerow(("Папка", "Дата перевірки", "Тривалість, с", "Усього", "Без змін", "Змінено",
                         "Додано", "Видалено", "Помилки", "Файл", "Статус", "Розмір еталона, Б",
                         "Поточний розмір, Б", "SHA-256 еталона", "Поточний SHA-256", "Пояснення",
                         "Вкладені папки", "Правила виключення", "Службові виключення"))
        counts = result.counts
        common = [str(result.baseline.root_folder), result.completed_at.isoformat(),
                  f"{result.duration_seconds:.6f}", len(result.files)] + [counts[s] for s in FileStatus]
        for item in result.files or (None,):
            check_cancelled(cancel)
            before, after = (item.expected, item.actual) if item else (None, None)
            row = common + [item.path if item else "", item.status.value if item else "Файлів немає",
                            before.size if before else "", after.size if after else "",
                            before.sha256 if before else "", after.sha256 if after else "",
                            item.message if item else "Порожній завершений результат",
                            "так" if result.baseline.include_subfolders else "ні",
                            ", ".join(result.baseline.exclusion_patterns), ", ".join(result.baseline.excluded_paths)]
            writer.writerow([self.safe_cell(value) for value in row])
