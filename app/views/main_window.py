"""Представлення MVC на Qt Widgets: компонування, діалоги та відображення."""

from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer, QSignalBlocker, QDir
from PySide6.QtGui import QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QComboBox, QDialog, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QTableView, QVBoxLayout, QWidget,
)

from app import __version__
from app.models import FileStatus
from app.views.icons import icon
from app.views.saved_result_window import SavedResultWindow
from app.views.table_models import ResultsModel, StatusDelegate, TONES, display_modified, display_size
from app.views.widgets import Card, DragBar, Switch, WindowFrame, label


class MainWindow(WindowFrame):
    def __init__(self):
        super().__init__()
        self._controller = None
        self._allow_close = False
        self._busy = False
        self._rendered = None
        self._rendered_patterns = None
        self._rendered_history = None
        self._result = self._baseline = None
        self._saved_result_window = None
        self._detail_windows = []
        self._counts = {}
        self.setWindowTitle("FileGuard — Контроль цілісності файлів")
        self.setWindowIcon(icon("shield", "#1675ff"))
        self.setMinimumSize(1080, 820)
        self.resize(1400, 920)
        QDir.addSearchPath("fgicons", str(Path(__file__).with_name("assets")))
        self.setStyleSheet(Path(__file__).with_name("theme.qss").read_text(encoding="utf-8"))
        self._build_layout()
        self.apply_window_size((1400, 920))

    @staticmethod
    def button(text, callback, primary=False, symbol=None):
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            button.setObjectName("Primary")
        if symbol:
            button.setIcon(icon(symbol))
        button.clicked.connect(callback)
        return button

    def _build_layout(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)
        self.sidebar = Card(name="Sidebar", margins=20)
        self.sidebar.setFixedWidth(226)
        brand = QHBoxLayout()
        shield = QLabel()
        shield.setPixmap(icon("shield", "#1675ff", 38).pixmap(38, 38))
        brand.addWidget(shield)
        brand.addWidget(label("FileGuard", "Brand"))
        brand.addStretch()
        self.sidebar.box.addLayout(brand)
        self.sidebar.box.addSpacing(25)
        self.pages = QStackedWidget()
        self.navigation = []
        self.nav_group = QButtonGroup(self)
        for index, (text, symbol) in enumerate((("Перевірка", "search"), ("Історія", "clock"),
                                                ("Налаштування", "settings"))):
            button = self.button(text, lambda checked=False, page=index: self.pages.setCurrentIndex(page), symbol=symbol)
            button.setObjectName("Navigation")
            button.setIconSize(QSize(23, 23))
            button.setCheckable(True)
            self.nav_group.addButton(button)
            self.navigation.append(button)
            self.sidebar.box.addWidget(button)
        self.navigation[0].setChecked(True)
        self.pages.currentChanged.connect(lambda index: self.navigation[index].setChecked(True))
        self.sidebar.box.addStretch()
        self.sidebar.box.addWidget(label(f"FileGuard {__version__}", "Footer"))
        root.addWidget(self.sidebar)

        body = QWidget()
        body.setObjectName("MainBody")
        body_box = QVBoxLayout(body)
        body_box.setContentsMargins(24, 8, 24, 16)
        body_box.setSpacing(12)
        chrome = DragBar()
        chrome.setFixedHeight(32)
        chrome_box = QHBoxLayout(chrome)
        chrome_box.setContentsMargins(0, 0, 0, 0)
        chrome_box.addStretch()
        for symbol, text, callback in (("minus", "Згорнути", self.showMinimized),
                                        ("maximize", "Розгорнути або відновити", self._maximize),
                                        ("close", "Закрити", self._request_close)):
            control = self.button("", callback, symbol=symbol)
            control.setAccessibleName(text)
            control.setToolTip(text)
            control.setFixedSize(39, 29)
            control.setObjectName("WindowClose" if symbol == "close" else "WindowControl")
            chrome_box.addWidget(control)
        body_box.addWidget(chrome)
        self.title_label = label("Контроль цілісності", "Title")
        self.subtitle_label = label("Порівняння файлів зі збереженим еталоном", "Subtitle")
        body_box.addWidget(self.title_label)
        body_box.addWidget(self.subtitle_label)
        body_box.addWidget(self.pages, 1)
        self.pages.currentChanged.connect(self._page_changed)
        self._build_check_page()
        self._build_history_page()
        self._build_settings_page()
        self.footer = label("Оберіть папку для початку роботи", "Footer")
        self.footer.setWordWrap(True)
        body_box.addWidget(self.footer)
        root.addWidget(body, 1)

    def _page_changed(self, index):
        self.title_label.setText(("Контроль цілісності", "Історія перевірок", "Налаштування")[index])
        self.subtitle_label.setText(("Порівняння файлів зі збереженим еталоном",
                                     "Завершені перевірки та збережені звіти",
                                     "Параметри нового еталона та виключення")[index])

    def _build_check_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 2, 0, 0)
        box.setSpacing(12)
        source = Card(margins=18)
        top = QHBoxLayout()
        folder = QLabel()
        folder.setPixmap(icon("folder", "#e9ab24", 42).pixmap(42, 42))
        top.addWidget(folder)
        names = QVBoxLayout()
        self.folder_name = label("Папку ще не обрано", "FolderName")
        self.folder_path = label("Оберіть папку, стан якої потрібно контролювати", "Muted")
        self.folder_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        names.addWidget(self.folder_name)
        names.addWidget(self.folder_path)
        top.addLayout(names, 1)
        self.choose_button = self.button("Обрати папку", lambda: self._controller.choose_folder())
        top.addWidget(self.choose_button)
        source.box.addLayout(top)
        metadata = QHBoxLayout()
        self.subfolders_check = Switch("Вкладені папки")
        self.subfolders_check.toggled.connect(lambda enabled: self._controller.set_include_subfolders(enabled))
        metadata.addWidget(self.subfolders_check)
        self.baseline_summary = label("Еталон не завантажено · SHA-256", "Muted")
        self.baseline_summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        metadata.addWidget(self.baseline_summary, 1)
        self.issues_button = self.button("Пропущені шляхи", self._show_issues)
        metadata.addWidget(self.issues_button)
        self.issues_button.hide()
        source.box.addLayout(metadata)
        actions = QHBoxLayout()
        self.create_baseline_button = self.button("Створити еталон", lambda: self._controller.create_baseline())
        self.load_baseline_button = self.button("Завантажити еталон", lambda: self._controller.load_baseline())
        self.check_button = self.button("Перевірити цілісність", lambda: self._controller.check_integrity(), True)
        for widget in (self.create_baseline_button, self.load_baseline_button, self.check_button):
            actions.addWidget(widget, 1)
        source.box.addLayout(actions)
        self.progress_area = QWidget()
        progress = QHBoxLayout(self.progress_area)
        progress.setContentsMargins(0, 0, 0, 0)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        progress.addWidget(self.progress_bar, 1)
        self.cancel_button = self.button("Скасувати", lambda: self._controller.cancel_operation())
        progress.addWidget(self.cancel_button)
        source.box.addWidget(self.progress_area)
        self.progress_area.hide()
        box.addWidget(source)

        counters = QHBoxLayout()
        counters.setSpacing(10)
        self.counter_labels = {}
        for text, status in (("Усього", None), ("Без змін", FileStatus.UNCHANGED), ("Змінено", FileStatus.CHANGED),
                             ("Додано", FileStatus.ADDED), ("Видалено", FileStatus.DELETED), ("Помилки", FileStatus.ERROR)):
            card = Card(name="Counter", margins=12)
            caption = label(text, "Muted")
            card.box.addWidget(caption)
            line = QHBoxLayout()
            color, background, symbol = TONES[status] if status else ("#354967", "#edf1f7", "file")
            value = label("—", "Count")
            value.setStyleSheet(f"color: {color}")
            self.counter_labels[text] = value
            line.addWidget(value)
            line.addStretch()
            badge = QLabel()
            badge.setPixmap(icon(symbol, color, 22).pixmap(22, 22))
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedSize(34, 34)
            badge.setStyleSheet(f"background:{background}; border-radius:17px")
            line.addWidget(badge)
            card.box.addLayout(line)
            counters.addWidget(card, 1)
        box.addLayout(counters)

        results = Card(margins=16)
        toolbar = QHBoxLayout()
        self.table_title = label("Результати перевірки", "Heading")
        toolbar.addWidget(self.table_title, 1)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Усі статуси"] + [status.value for status in FileStatus])
        self.status_filter.setAccessibleName("Фільтр статусу")
        self.status_filter.currentTextChanged.connect(lambda text: self._controller.set_status_filter(text))
        toolbar.addWidget(self.status_filter)
        self.export_button = self.button("Зберегти звіт", lambda: None, symbol="download")
        self.export_menu = self._export_menu(self.export_button, lambda ext: self._controller.export_result(extension=ext))
        toolbar.addWidget(self.export_button)
        results.box.addLayout(toolbar)
        self.results_model = ResultsModel(self)
        self.results_table = self._table()
        self.results_table.setModel(self.results_model)
        self.results_table.setItemDelegateForColumn(1, StatusDelegate(self.results_table))
        self.results_table.setColumnWidth(1, 145)
        self.results_table.setColumnWidth(2, 95)
        self.results_table.setColumnWidth(3, 160)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.results_table.selectionModel().selectionChanged.connect(self._sync_details)
        self.results_table.doubleClicked.connect(self._show_file_details)
        self.results_table.activated.connect(self._show_file_details)
        self.results_stack = QStackedWidget()
        self.results_stack.addWidget(self.results_table)
        empty = QWidget()
        empty_box = QVBoxLayout(empty)
        empty_box.addStretch()
        self.empty_title = label("Перевірку ще не виконано", "Heading")
        self.empty_hint = label("Оберіть папку та створіть або завантажте еталон", "Muted")
        for widget in (self.empty_title, self.empty_hint):
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            widget.setWordWrap(True)
            empty_box.addWidget(widget)
        empty_box.addStretch()
        self.results_stack.addWidget(empty)
        results.box.addWidget(self.results_stack, 1)
        bottom = QHBoxLayout()
        self.details_button = self.button("Відомості", self._show_file_details, symbol="info")
        bottom.addWidget(self.details_button)
        bottom.addStretch()
        self.table_footer = label("Результатів поки немає", "Footer")
        bottom.addWidget(self.table_footer)
        results.box.addLayout(bottom)
        box.addWidget(results, 1)
        self.pages.addWidget(page)

    def _table(self):
        table = QTableView()
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(43)
        table.horizontalHeader().setHighlightSections(False)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        table.setMinimumHeight(130)
        return table

    @staticmethod
    def _export_menu(parent, callback):
        menu = QMenu(parent)
        for extension, title in (("txt", "Текстовий звіт (.txt)"), ("csv", "Таблиця CSV (.csv)")):
            menu.addAction(title, lambda checked=False, ext=extension: callback(ext))
        parent.setMenu(menu)
        return menu

    def _build_history_page(self):
        page = Card(margins=20)
        top = QHBoxLayout()
        top.addWidget(label("Збережені результати", "Heading"), 1)
        self.history_refresh_button = self.button("Оновити", lambda: self._controller.refresh_history(), symbol="refresh")
        self.history_open_button = self.button("Відкрити", self._open_history)
        top.addWidget(self.history_refresh_button)
        top.addWidget(self.history_open_button)
        page.box.addLayout(top)
        self.history_table = self._table()
        self.history_model = QStandardItemModel(0, 6, self)
        self.history_model.setHorizontalHeaderLabels(["Дата", "Папка", "Усього", "Зміни", "Помилки", "Час, с"])
        self.history_table.setModel(self.history_model)
        self.history_table.setColumnWidth(0, 155)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for index in range(2, 6):
            self.history_table.setColumnWidth(index, 72)
        self.history_table.doubleClicked.connect(self._open_history)
        self.history_table.activated.connect(self._open_history)
        self.history_table.selectionModel().selectionChanged.connect(self._sync_history)
        page.box.addWidget(self.history_table, 1)
        self.history_summary = label("Збережених перевірок поки немає", "Muted")
        self.history_summary.setWordWrap(True)
        page.box.addWidget(self.history_summary)
        self.pages.addWidget(page)

    def _build_settings_page(self):
        scroll = QScrollArea()
        scroll.setObjectName("SettingsScroll")
        scroll.viewport().setObjectName("SettingsViewport")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        page = Card(margins=24)
        page.box.addWidget(label("Параметри нового еталона", "Heading"))
        self.settings_subfolders_check = Switch("Включати вкладені папки")
        self.settings_subfolders_check.toggled.connect(lambda enabled: self._controller.set_include_subfolders(enabled))
        page.box.addWidget(self.settings_subfolders_check)
        note = label("Перевірка використовує параметри завантаженого еталона. Алгоритм: SHA-256.", "Muted")
        note.setWordWrap(True)
        page.box.addWidget(note)
        page.box.addSpacing(12)
        page.box.addWidget(label("Виключення", "Heading"))
        hint = label("Одне правило на рядок. Приклади: *.tmp, .git, __pycache__, cache/, logs/*.log.", "Muted")
        hint.setWordWrap(True)
        page.box.addWidget(hint)
        self.exclusions_input = QPlainTextEdit()
        self.exclusions_input.setAccessibleName("Правила виключення")
        self.exclusions_input.setFont(QFont("Consolas", 10))
        self.exclusions_input.setMinimumHeight(120)
        self.exclusions_input.setMaximumHeight(170)
        page.box.addWidget(self.exclusions_input)
        self.apply_exclusions_button = self.button("Застосувати виключення", self._apply_exclusions)
        page.box.addWidget(self.apply_exclusions_button, 0, Qt.AlignmentFlag.AlignLeft)
        page.box.addSpacing(12)
        self.save_settings_button = self.button("Зберегти налаштування", lambda: self._controller.save_settings(), True)
        page.box.addWidget(self.save_settings_button, 0, Qt.AlignmentFlag.AlignLeft)
        automatic = label("Застосовані параметри також зберігаються під час закриття програми.", "Muted")
        automatic.setWordWrap(True)
        page.box.addWidget(automatic)
        page.box.addStretch()
        scroll.setWidget(page)
        # setWidget вмикає прямокутну заливку палітрою; вона перекривала
        # світлий фон у прозорих кутах округленої картки на темній Windows.
        page.setAutoFillBackground(False)
        self.pages.addWidget(scroll)

    def set_controller(self, controller):
        self._controller = controller

    def render_state(self, state):
        """Синхронізація не викликає повторних команд через сигнали віджетів."""
        self._busy = state.busy
        self._result, self._baseline = state.check_result, state.baseline
        self.folder_name.setText(state.selected_folder.name if state.selected_folder else "Папку ще не обрано")
        self.folder_path.setText(str(state.selected_folder) if state.selected_folder else "Оберіть папку для контролю")
        self.folder_path.setToolTip(self.folder_path.text())
        if state.baseline:
            baseline = state.baseline
            name = state.baseline_path.name if state.baseline_path else "Еталон"
            self.baseline_summary.setText(f"{name} · SHA-256 · {len(baseline.files)} файлів")
            self.baseline_summary.setToolTip(f"Створено: {baseline.created_at.astimezone():%d.%m.%Y %H:%M}\n"
                                             f"Вкладені папки: {'так' if baseline.include_subfolders else 'ні'}\n"
                                             f"Правила виключення: {', '.join(baseline.exclusion_patterns) or 'немає'}")
        else:
            self.baseline_summary.setText("Еталон не завантажено · SHA-256")
        for switch in (self.subfolders_check, self.settings_subfolders_check):
            with QSignalBlocker(switch):
                switch.setChecked(state.include_subfolders)
        with QSignalBlocker(self.status_filter):
            self.status_filter.setCurrentText(state.status_filter.value if state.status_filter else "Усі статуси")
        if self._rendered_patterns != state.exclusion_patterns:
            self.exclusions_input.setPlainText("\n".join(state.exclusion_patterns))
            self._rendered_patterns = state.exclusion_patterns
        # Стан змінюється часто під час прогресу, але завершену таблицю не перебудовуємо.
        signature = (id(state.baseline), id(state.check_result), state.status_filter)
        if signature != self._rendered:
            self._rendered = signature
            self._counts = state.check_result.counts if state.check_result else {}
            rows = (tuple(item for item in state.check_result.files
                          if state.status_filter is None or item.status == state.status_filter)
                    if state.check_result else state.baseline.files if state.baseline else ())
            self.results_model.set_rows(rows, state.check_result is not None)
            self.results_stack.setCurrentIndex(0 if rows else 1)
            self.empty_title.setText("За цим фільтром немає записів" if state.check_result and state.check_result.files
                                     else "Файлів немає" if state.baseline else "Перевірку ще не виконано")
            self.empty_hint.setText("Спробуйте обрати інший статус" if state.check_result and state.check_result.files
                                    else "Оберіть папку та створіть або завантажте еталон" if not state.baseline
                                    else "Еталон або завершена перевірка не містить файлів")
        result = state.check_result
        for index, (text, value) in enumerate(self.counter_labels.items()):
            number = (len(result.files) if index == 0 else self._counts[list(FileStatus)[index - 1]]) if result else (
                len(state.baseline.files) if index == 0 and state.baseline else None)
            value.setText(str(number) if number is not None else "—")
        self.table_title.setText("Попередні результати" if state.busy and result else
                                 "Результати перевірки" if result else "Файли еталона" if state.baseline else "Результати перевірки")
        total = len(result.files) if result else len(state.baseline.files) if state.baseline else 0
        finished = f" · {result.completed_at.astimezone():%d.%m.%Y %H:%M}" if result else ""
        self.table_footer.setText(f"Показано {len(self.results_model.rows)} із {total}{finished}")
        error_count = self._counts[FileStatus.ERROR] if result else len(state.baseline.issues) if state.baseline else 0
        self.issues_button.setVisible(bool(error_count))
        self.issues_button.setText("Помилки перевірки" if result else "Пропущені шляхи")
        self.progress_area.setVisible(state.busy)
        self.cancel_button.setEnabled(not state.cancel_requested)
        for widget in (self.choose_button, self.load_baseline_button, self.subfolders_check,
                       self.settings_subfolders_check, self.apply_exclusions_button, self.exclusions_input,
                       self.save_settings_button, self.issues_button):
            widget.setEnabled(not state.busy)
        self.create_baseline_button.setEnabled(not state.busy and state.selected_folder is not None)
        self.check_button.setEnabled(not state.busy and state.baseline is not None)
        self.export_button.setEnabled(not state.busy and result is not None)
        self.status_filter.setEnabled(not state.busy and result is not None)
        self.history_refresh_button.setEnabled(not state.busy and state.history_available)
        self._history_available = state.history_available
        if self._rendered_history != state.history_entries:
            self._rendered_history = state.history_entries
            self.history_model.removeRows(0, self.history_model.rowCount())
            for entry in state.history_entries:
                changes = sum(entry.counts[status] for status in (FileStatus.CHANGED, FileStatus.ADDED, FileStatus.DELETED))
                values = [entry.completed_at.astimezone().strftime("%d.%m.%Y %H:%M"), str(entry.root_folder),
                          str(sum(entry.counts.values())), str(changes), str(entry.counts[FileStatus.ERROR]),
                          f"{entry.duration_seconds:.2f}"]
                items = [QStandardItem(value) for value in values]
                items[0].setData(entry.identifier, Qt.ItemDataRole.UserRole)
                for item in items:
                    item.setToolTip(item.text())
                self.history_model.appendRow(items)
        self.history_summary.setText(f"Показано {len(state.history_entries)} останніх перевірок (до 200). Повний звіт доступний через «Відкрити».")
        self._sync_details()
        self._sync_history()
        if self._saved_result_window:
            self._saved_result_window.set_busy(state.busy)
        self.footer.setText(state.status_message)

    def _apply_exclusions(self):
        self._controller.set_exclusion_patterns(tuple(line.strip() for line in self.exclusions_input.toPlainText().splitlines() if line.strip()))

    def _sync_details(self, *args):
        self.details_button.setEnabled(not self._busy and bool(self.results_table.selectionModel().selectedRows()))

    def _sync_history(self, *args):
        self.history_open_button.setEnabled(not self._busy and getattr(self, "_history_available", False)
                                            and bool(self.history_table.selectionModel().selectedRows()))

    def _open_history(self, *args):
        rows = self.history_table.selectionModel().selectedRows()
        if rows and not self._busy:
            self._controller.open_history(rows[0].data(Qt.ItemDataRole.UserRole))

    def _show_file_details(self, *args):
        rows = self.results_table.selectionModel().selectedRows()
        if not rows or self._busy:
            return
        item = self.results_model.rows[rows[0].row()]
        before, after = (item.expected, item.actual) if self._result else (item, None)
        lines = [item.path, "", f"Статус: {item.status.value if self._result else 'В еталоні'}",
                 item.message if self._result else "Порівняння ще не виконано."]
        for title, snapshot in (("Еталон", before), ("Поточний стан", after)):
            lines += ["", title, f"Розмір: {display_size(snapshot.size)}" if snapshot else "Дані відсутні"]
            if snapshot:
                lines += [f"Дата: {display_modified(snapshot)}", f"SHA-256: {snapshot.sha256}"]
        self._text_dialog("Відомості про файл", "\n".join(lines))

    def _show_issues(self):
        issues = [(item.path, item.message) for item in self._result.files if item.status == FileStatus.ERROR] if self._result else (
            [(item.path, item.message) for item in self._baseline.issues] if self._baseline else [])
        text = "\n\n".join(f"{path}\n{message}" for path, message in issues[:1000])
        if len(issues) > 1000:
            text += "\n\nПоказано перші 1000 записів. Повний список збережено у результаті."
        self._text_dialog("Помилки перевірки" if self._result else "Пропущені шляхи", text)

    def _text_dialog(self, title, text):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(780, 500)
        box = QVBoxLayout(dialog)
        box.setContentsMargins(20, 20, 20, 20)
        box.addWidget(label(title, "Heading"))
        content = QPlainTextEdit()
        content.setReadOnly(True)
        content.setPlainText(text)
        content.setFont(QFont("Consolas", 10))
        box.addWidget(content)
        self._detail_windows.append(dialog)
        dialog.finished.connect(lambda: self._detail_windows.remove(dialog))
        dialog.show()

    def show_saved_result(self, result, text):
        if self._saved_result_window:
            self._saved_result_window.close()
            self._saved_result_window.deleteLater()
        self._saved_result_window = SavedResultWindow(self, result, text,
                                                      lambda saved, ext: self._controller.export_result(saved, ext))
        self._saved_result_window.show()

    def ask_directory(self, initial_directory):
        return QFileDialog.getExistingDirectory(self, "Оберіть папку для контролю цілісності", initial_directory or str(Path.home()))

    def ask_save_baseline(self, directory, filename):
        return QFileDialog.getSaveFileName(self, "Зберегти еталон", str(directory / filename), "Еталон JSON (*.json)")[0]

    def ask_open_baseline(self, directory):
        return QFileDialog.getOpenFileName(self, "Завантажити еталон", str(directory), "Еталон JSON (*.json);;Усі файли (*)")[0]

    def ask_save_report(self, directory, filename, extension):
        title = "Текстовий звіт (*.txt)" if extension == "txt" else "Таблиця CSV (*.csv)"
        return QFileDialog.getSaveFileName(self, "Зберегти звіт", str(directory / filename), title)[0]

    def show_error(self, title, message):
        QMessageBox.warning(self, title, message)

    def schedule(self, delay_ms, callback):
        QTimer.singleShot(delay_ms, self, callback)

    def get_window_size(self):
        return max(1080, self.width()), max(820, self.height())

    def apply_window_size(self, size):
        area = self.screen().availableGeometry()
        self.resize(max(1080, min(size[0], area.width() - 40)), max(820, min(size[1], area.height() - 40)))
        self.move(area.center() - self.rect().center())

    def _maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _request_close(self):
        self._controller.request_close() if self._controller else self.close()

    def close(self):
        self._allow_close = True
        return super().close()

    def closeEvent(self, event):
        if self._allow_close or not self._controller:
            event.accept()
        else:
            event.ignore()
            self._controller.request_close()
