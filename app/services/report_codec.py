"""Перетворення завершеної перевірки у перевірений знімок для історії."""

import math
from dataclasses import asdict
from datetime import datetime

from app.models import CheckResult, FileCheckResult, FileSnapshot, FileStatus
from app.services.baseline_storage import BaselineStorage


class ReportCodec:
    def __init__(self):
        self.baselines = BaselineStorage()

    def encode(self, result: CheckResult) -> dict:
        return {
            "application": "FileGuard", "version": 1,
            "baseline": self.baselines._document(result.baseline),
            "completed_at": result.completed_at.isoformat(), "duration_seconds": result.duration_seconds,
            "files": [{"path": item.path, "status": item.status.value,
                       "expected": asdict(item.expected) if item.expected else None,
                       "actual": asdict(item.actual) if item.actual else None, "message": item.message}
                      for item in result.files],
        }

    def _snapshot(self, value):
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("Некоректні відомості про файл в історії.")
        # Використовуємо ті самі правила шляхів, хешів і розмірів, що й для еталона.
        import re
        digest = value.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError("Некоректний SHA-256 у збереженій перевірці.")
        return FileSnapshot(self.baselines._relative_path(value.get("path")), digest.lower(),
                            self.baselines._integer(value.get("size"), True),
                            self.baselines._integer(value.get("modified_ns")))

    def decode(self, document: dict) -> CheckResult:
        if (not isinstance(document, dict) or document.get("application") != "FileGuard"
                or type(document.get("version")) is not int or document["version"] != 1):
            raise ValueError("Непідтримуваний формат збереженої перевірки.")
        baseline = self.baselines._validate(document.get("baseline"))
        completed = datetime.fromisoformat(document["completed_at"])
        if completed.tzinfo is None:
            raise ValueError("Дата перевірки не містить часового поясу.")
        completed.astimezone()  # Перевіряємо, що дата придатна для відображення.
        duration = document.get("duration_seconds")
        if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
            raise ValueError("Некоректна тривалість збереженої перевірки.")
        if not isinstance(document.get("files"), list):
            raise ValueError("В історії відсутній список результатів.")
        known = {item.path.casefold(): item for item in baseline.files}
        rows, seen = [], set()
        for item in document["files"]:
            if not isinstance(item, dict) or not isinstance(item.get("message"), str):
                raise ValueError("Пошкоджено запис результату в історії.")
            path = self.baselines._relative_path(item.get("path"))
            key = path.casefold()
            if key in seen:
                raise ValueError("Історія містить повторювані шляхи.")
            seen.add(key)
            status = FileStatus(item.get("status"))
            before, after = self._snapshot(item.get("expected")), self._snapshot(item.get("actual"))
            if any(snapshot.path.casefold() != key for snapshot in (before, after) if snapshot):
                raise ValueError("Шляхи у збереженому результаті не узгоджені.")
            if before is not None and known.get(key) != before:
                raise ValueError("Початковий стан не відповідає збереженому еталону.")
            valid = {
                FileStatus.UNCHANGED: before is not None and after is not None and before.sha256 == after.sha256,
                FileStatus.CHANGED: before is not None and after is not None and before.sha256 != after.sha256,
                FileStatus.ADDED: before is None and after is not None,
                FileStatus.DELETED: before is not None and after is None,
                FileStatus.ERROR: bool(item["message"]),
            }
            if not valid[status]:
                raise ValueError("Статус не узгоджений зі збереженими хешами.")
            rows.append(FileCheckResult(path, status, before, after, item["message"]))
        return CheckResult(baseline, completed, float(duration), tuple(rows))


def report_text(result: CheckResult) -> str:
    """Один текстовий формат для перегляду історії та майбутнього експорту."""
    counts = result.counts
    lines = ["FileGuard — Звіт про контроль цілісності файлів", "",
             f"Папка: {result.baseline.root_folder}",
             f"Перевірку завершено: {result.completed_at.astimezone().isoformat(timespec='seconds')}",
             f"Еталон створено: {result.baseline.created_at.isoformat()}",
             f"Тривалість: {result.duration_seconds:.3f} с", "Алгоритм: SHA-256",
             f"Вкладені папки: {'так' if result.baseline.include_subfolders else 'ні'}",
             "Правила виключення: " + (", ".join(result.baseline.exclusion_patterns) or "немає"),
             "Службові виключення: " + (", ".join(result.baseline.excluded_paths) or "немає"),
             f"Усього записів: {len(result.files)}"]
    lines += [f"{status.value}: {counts[status]}" for status in FileStatus]
    for item in result.files:
        lines += ["", f"Файл: {item.path}", f"Статус: {item.status.value}", f"Пояснення: {item.message}"]
        for label, snapshot in (("Еталон", item.expected), ("Поточний стан", item.actual)):
            lines.append(f"{label}: " + (f"{snapshot.size} Б; SHA-256: {snapshot.sha256}" if snapshot else "дані відсутні"))
    return "\n".join(lines) + "\n"
