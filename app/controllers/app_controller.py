"""Координація інтерфейсу, стану застосунку та файлових операцій."""

from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full, Queue, SimpleQueue
from threading import Event, Thread
from typing import Callable, Protocol

from app.models import AppState, Baseline, CheckResult, FileStatus, HistoryEntry, ScanProgress
from app.services.baseline_storage import BaselineStorage
from app.services.directory_service import DirectoryService
from app.services.integrity_service import IntegrityService, OperationCancelled, check_cancelled
from app.services.exclusions import ExclusionRules
from app.services.history_storage import HistoryStorage
from app.services.report_codec import report_text
from app.services.report_service import ReportService


@dataclass(frozen=True)
class CheckCompletion:
    result: CheckResult
    entries: tuple[HistoryEntry, ...] | None = None
    warning: str = ""


class AppView(Protocol):
    """Мінімальний контракт вікна, потрібний контролеру."""

    def render_state(self, state: AppState) -> None: ...

    def ask_directory(self, initial_directory: str | None) -> str: ...

    def show_error(self, title: str, message: str) -> None: ...

    def ask_save_baseline(self, directory: Path, filename: str) -> str: ...

    def ask_open_baseline(self, directory: Path) -> str: ...

    def schedule(self, delay_ms: int, callback: Callable[[], None]) -> None: ...

    def close(self) -> None: ...

    def show_saved_result(self, result: CheckResult, text: str) -> None: ...

    def ask_save_report(self, directory: Path, filename: str, extension: str) -> str: ...


class AppController:
    """Обробляє команди; не створює віджетів і не обчислює хешів."""

    def __init__(
        self, state: AppState, view: AppView, directory_service: DirectoryService,
        integrity_service: IntegrityService | None = None,
        baseline_storage: BaselineStorage | None = None,
        history_storage: HistoryStorage | None = None,
        report_service: ReportService | None = None,
    ) -> None:
        self.state = state
        self.view = view
        self.directory_service = directory_service
        self.integrity_service = integrity_service or IntegrityService()
        self.baseline_storage = baseline_storage or BaselineStorage()
        self.history_storage = history_storage
        self.report_service = report_service or ReportService()
        self.state.history_available = history_storage is not None
        self._cancel = Event()
        self._progress_queue: Queue[ScanProgress] = Queue(maxsize=1)
        self._result_queue: SimpleQueue[tuple[str, object]] = SimpleQueue()
        self._close_requested = False
        self._worker: Thread | None = None
        self._task_kind = ""

    def start(self) -> None:
        """Показати початковий стан застосунку."""
        self.view.render_state(self.state)
        if self.history_storage is not None:
            self.refresh_history()

    def choose_folder(self) -> None:
        """Отримати вибір із діалогу та передати шлях на перевірку сервісу."""
        if self.state.busy:
            return
        initial = str(self.state.selected_folder) if self.state.selected_folder else None
        selected = self.view.ask_directory(initial)
        if not selected:
            # Скасування діалогу не змінює вже вибрану папку.
            return
        self.select_folder(selected)

    def select_folder(self, folder: str) -> bool:
        """Оновити модель лише після успішної перевірки шляху."""
        if self.state.busy:
            return False
        try:
            resolved = self.directory_service.validate_folder(folder)
        except (OSError, ValueError, RuntimeError) as error:
            self.view.show_error("Не вдалося обрати папку", str(error))
            return False

        if resolved != self.state.selected_folder:
            self.state.baseline = None
            self.state.baseline_path = None
        self.state.check_result = None
        self.state.selected_folder = resolved
        self.state.status_message = "Папку обрано · перевірку ще не виконано"
        self.view.render_state(self.state)
        return True

    def set_include_subfolders(self, enabled: bool) -> None:
        """Зберегти параметр у моделі та синхронізувати обидві вкладки."""
        if self.state.busy:
            return
        self.state.include_subfolders = bool(enabled)
        if self.state.baseline is not None:
            self.state.status_message = "Параметр нового еталона змінено · перевірка використовує параметри еталона"
        self.view.render_state(self.state)

    def create_baseline(self) -> None:
        """Зібрати параметри в головному потоці, а читання виконати у фоновому."""
        if self.state.busy or self.state.selected_folder is None:
            return
        filename = f"baseline_{datetime.now():%Y%m%d_%H%M%S}.json"
        selected = self.view.ask_save_baseline(self.baseline_storage.default_directory, filename)
        if not selected:
            return
        try:
            destination = self.baseline_storage.prepare_destination(selected)
        except (OSError, ValueError, RuntimeError) as error:
            self.view.show_error("Не вдалося зберегти еталон", str(error))
            return

        root = self.state.selected_folder
        recursive = self.state.include_subfolders
        patterns = self.state.exclusion_patterns

        def task() -> tuple[Baseline, Path]:
            baseline = self.integrity_service.create_baseline(
                root, recursive, destination, self._cancel, self._report_progress, patterns
            )
            self.baseline_storage.save(baseline, destination, self._cancel)
            return baseline, destination

        self._start_task(task, "Створення еталона…", "created")

    def set_exclusion_patterns(self, patterns) -> None:
        if self.state.busy:
            return
        try:
            self.state.exclusion_patterns = ExclusionRules.validate(patterns)
        except ValueError as error:
            self.view.show_error("Некоректні виключення", str(error))
            return
        self.state.status_message = "Виключення застосовано для нового еталона · чинний еталон зберігає власні правила"
        self.view.render_state(self.state)

    def set_status_filter(self, status: str) -> None:
        if self.state.busy:
            return
        self.state.status_filter = None if status == "Усі статуси" else FileStatus(status)
        self.view.render_state(self.state)

    def load_baseline(self) -> None:
        if self.state.busy:
            return
        selected = self.view.ask_open_baseline(self.baseline_storage.default_directory)
        if not selected:
            return
        source = Path(selected).absolute()

        def task() -> tuple[Baseline, Path]:
            return self.baseline_storage.load(source, self._cancel), source

        self._start_task(task, "Завантаження еталона…", "loaded")

    def check_integrity(self) -> None:
        """Перевірка використовує охоплення еталона, а не параметри нового знімка."""
        if self.state.busy or self.state.baseline is None:
            return
        baseline = self.state.baseline
        source = self.state.baseline_path

        def task() -> CheckCompletion:
            result = self.integrity_service.check_integrity(
                baseline, source, self._cancel, self._report_progress
            )
            if self.history_storage is None:
                return CheckCompletion(result)
            try:
                self.history_storage.save(result, self._cancel)
                return CheckCompletion(result, self.history_storage.list_entries())
            except OperationCancelled:
                raise
            except Exception as error:
                # Збій сховища не скасовує вже отриманий достовірний результат.
                return CheckCompletion(result, warning=f"Не вдалося оновити історію: {error}")

        self._start_task(task, "Перевірка цілісності…", "checked")

    def refresh_history(self) -> None:
        if self.state.busy or self.history_storage is None:
            return
        self._start_task(self.history_storage.list_entries, "Завантаження історії…", "history_list")

    def open_history(self, identifier: str) -> None:
        if self.state.busy or self.history_storage is None:
            return

        def task():
            result = self.history_storage.load(identifier, self._cancel)
            return result, report_text(result)

        self._start_task(task, "Відкриття збереженої перевірки…", "history_open")

    def export_result(self, result: CheckResult | None = None, extension: str = "txt") -> None:
        if self.state.busy:
            return
        result = result or self.state.check_result
        if result is None:
            return
        filename = f"FileGuard_{result.completed_at:%Y%m%d_%H%M%S}.{extension}"
        selected = self.view.ask_save_report(self.report_service.default_directory, filename, extension)
        if not selected:
            return

        def task():
            return self.report_service.export(result, selected, extension, self._cancel)

        self._start_task(task, "Збереження звіту…", "exported")

    def _report_progress(self, progress: ScanProgress) -> None:
        # Зберігаємо лише найновіше повідомлення, щоб великі папки не переповнили чергу.
        try:
            self._progress_queue.get_nowait()
        except Empty:
            pass
        try:
            self._progress_queue.put_nowait(progress)
        except Full:
            pass

    def _start_task(self, task: Callable[[], object], message: str, kind: str) -> None:
        self._cancel = Event()
        self._task_kind = kind
        self._progress_queue = Queue(maxsize=1)
        self.state.busy = True
        self.state.cancel_requested = False
        self.state.progress = ScanProgress()
        self.state.status_message = message
        self.view.render_state(self.state)

        def work() -> None:
            # Фоновий потік не звертається ані до tkinter, ані до моделі вікна.
            try:
                check_cancelled(self._cancel)
                self._result_queue.put((kind, task()))
            except OperationCancelled:
                self._result_queue.put(("cancelled", None))
            except Exception as error:
                self._result_queue.put(("error", str(error)))

        self._worker = Thread(target=work, name="FileGuard-worker", daemon=True)
        self._worker.start()
        self.view.schedule(60, self._poll_task)

    def _poll_task(self) -> None:
        """Обробляється тільки циклом tkinter у головному потоці."""
        try:
            self.state.progress = self._progress_queue.get_nowait()
            if not self.state.cancel_requested:
                progress = self.state.progress
                action = "Перевірка цілісності" if self._task_kind == "checked" else "Створення еталона"
                self.state.status_message = (
                    f"{action} · файлів: {progress.processed_files} · "
                    f"прочитано: {progress.processed_bytes / (1024 * 1024):.1f} МіБ"
                )
        except Empty:
            pass
        try:
            kind, value = self._result_queue.get_nowait()
        except Empty:
            self.view.render_state(self.state)
            self.view.schedule(60, self._poll_task)
            return

        self.state.busy = False
        self.state.cancel_requested = False
        warning = ""
        if kind == "checked":
            self.state.check_result = value.result
            if value.entries is not None:
                self.state.history_entries = value.entries
            warning = value.warning
            result = value.result
            counts = result.counts
            changes = sum(counts[status] for status in (FileStatus.CHANGED, FileStatus.ADDED, FileStatus.DELETED))
            action = "Перевірку завершено з помилками" if counts[FileStatus.ERROR] else "Перевірку завершено"
            self.state.status_message = (
                f"{action} · змін: {changes} · помилок: {counts[FileStatus.ERROR]}"
                f" · {result.duration_seconds:.2f} с"
            )
        elif kind == "history_list":
            self.state.history_entries = value
            self.state.status_message = f"Історію оновлено · записів у списку: {len(value)}"
        elif kind == "history_open":
            self.state.status_message = "Відкрито збережену перевірку · поточний еталон не змінено"
            if not self._close_requested:
                self.view.show_saved_result(*value)
        elif kind == "exported":
            self.state.status_message = f"Звіт збережено: {value.name}"
        elif kind in ("created", "loaded"):
            baseline, path = value
            self.state.baseline = baseline
            self.state.baseline_path = path
            self.state.selected_folder = baseline.root_folder
            self.state.include_subfolders = baseline.include_subfolders
            self.state.exclusion_patterns = baseline.exclusion_patterns
            self.state.check_result = None
            action = "Еталон створено" if kind == "created" else "Еталон завантажено"
            self.state.status_message = f"{action} · файлів: {len(baseline.files)}"
            if baseline.issues:
                self.state.status_message += f" · пропущено шляхів: {len(baseline.issues)}"
        elif kind == "cancelled":
            self.state.status_message = (
                "Перевірку скасовано · неповні результати не застосовано"
                if self._task_kind == "checked"
                else "Операцію скасовано · файл еталона не змінено"
            )
        else:
            self.state.status_message = "Операцію не завершено · попередній стан збережено"
        self.view.render_state(self.state)
        if self._close_requested:
            self.view.close()
        elif kind == "error":
            titles = {"checked": "Не вдалося перевірити цілісність", "history_list": "Історія недоступна",
                      "history_open": "Не вдалося відкрити запис історії", "exported": "Не вдалося зберегти звіт"}
            title = titles.get(self._task_kind, "Не вдалося опрацювати еталон")
            self.view.show_error(title, str(value))
        elif warning:
            self.view.show_error("Результат отримано, історія недоступна", warning)

    def cancel_operation(self) -> None:
        if self.state.busy:
            self._cancel.set()
            self.state.cancel_requested = True
            self.state.status_message = "Скасування операції…"
            self.view.render_state(self.state)

    def request_close(self) -> None:
        """Перед закриттям даємо потоку завершити читання та прибрати тимчасовий файл."""
        if self.state.busy:
            self._close_requested = True
            self.cancel_operation()
        else:
            self.view.close()
