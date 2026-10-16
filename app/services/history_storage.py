"""Локальна історія SQLite: транзакції та незмінні знімки перевірок."""

import json
import sqlite3
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from uuid import uuid4

from app.models import CheckResult, FileStatus, HistoryEntry
from app.services.baseline_storage import BaselineStorage
from app.services.integrity_service import check_cancelled
from app.services.report_codec import ReportCodec


class HistoryStorage:
    MAX_PAYLOAD_BYTES = 128 * 1024 * 1024

    def __init__(self, path: Path):
        self.path = path
        self.codec = ReportCodec()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Непідтримувана версія бази історії.")
            connection.execute("""CREATE TABLE IF NOT EXISTS checks (
                id TEXT PRIMARY KEY, completed_at TEXT NOT NULL, root_folder TEXT NOT NULL,
                duration REAL NOT NULL, counts TEXT NOT NULL, payload TEXT NOT NULL)""")
            connection.execute("CREATE INDEX IF NOT EXISTS checks_date ON checks(completed_at DESC)")
            connection.execute("PRAGMA user_version=1")
            return connection
        except Exception:
            connection.close()
            raise

    def save(self, result: CheckResult, cancel: Event) -> str:
        check_cancelled(cancel)
        payload = json.dumps(self.codec.encode(result), ensure_ascii=False)
        if len(payload.encode("utf-8")) > self.MAX_PAYLOAD_BYTES:
            raise ValueError("Результат завеликий для збереження в історії (понад 128 МіБ).")
        identifier = uuid4().hex
        summary = result.counts
        counts = json.dumps({status.value: summary[status] for status in FileStatus}, ensure_ascii=False)
        connection = self._connect()
        try:
            with connection:
                connection.execute("INSERT INTO checks VALUES (?, ?, ?, ?, ?, ?)", (
                    identifier, result.completed_at.astimezone(timezone.utc).isoformat(),
                    str(result.baseline.root_folder), result.duration_seconds, counts, payload,
                ))
                check_cancelled(cancel)  # Виняток до COMMIT скасовує всю транзакцію.
        finally:
            connection.close()
        return identifier

    def list_entries(self, limit: int = 200) -> tuple[HistoryEntry, ...]:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Кількість записів списку повинна бути від 1 до 200.")
        connection = self._connect()
        try:
            records = connection.execute(
                "SELECT id, completed_at, root_folder, duration, counts FROM checks ORDER BY completed_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            connection.close()
        entries = []
        for identifier, completed, root, duration, raw_counts in records:
            counts = json.loads(raw_counts)
            if (not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier)
                    or not isinstance(root, str) or not Path(root).is_absolute()
                    or type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0):
                raise ValueError("Пошкоджено відомості запису історії.")
            if not isinstance(counts, dict) or any(type(counts.get(status.value)) is not int or counts[status.value] < 0 for status in FileStatus):
                raise ValueError("Пошкоджено лічильники в історії.")
            date = datetime.fromisoformat(completed)
            if date.tzinfo is None:
                raise ValueError("Некоректна дата запису історії.")
            date.astimezone()
            entries.append(HistoryEntry(identifier, date, Path(root), duration,
                                        {status: counts[status.value] for status in FileStatus}))
        return tuple(entries)

    def load(self, identifier: str, cancel: Event) -> CheckResult:
        check_cancelled(cancel)
        connection = self._connect()
        try:
            size = connection.execute("SELECT length(CAST(payload AS BLOB)) FROM checks WHERE id=?", (identifier,)).fetchone()
            if size is None:
                raise ValueError("Запис історії не знайдено.")
            if size[0] > self.MAX_PAYLOAD_BYTES:
                raise ValueError("Запис історії перевищує допустимий розмір.")
            payload = connection.execute("SELECT payload FROM checks WHERE id=?", (identifier,)).fetchone()[0]
        finally:
            connection.close()
        document = json.loads(payload, object_pairs_hook=BaselineStorage._unique_object)
        result = self.codec.decode(document)
        check_cancelled(cancel)
        return result
