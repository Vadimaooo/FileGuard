"""Окремий перегляд завершеної перевірки без повторного читання файлів."""

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QHBoxLayout, QMenu, QPlainTextEdit, QPushButton, QVBoxLayout

from app.views.icons import icon
from app.views.widgets import label


class SavedResultWindow(QDialog):
    def __init__(self, parent, result, text, on_export):
        super().__init__(parent)
        self.setWindowTitle("Збережена перевірка — FileGuard")
        self.resize(960, 650)
        self.setMinimumSize(680, 420)
        box = QVBoxLayout(self)
        box.setContentsMargins(24, 22, 24, 24)
        box.setSpacing(16)
        top = QHBoxLayout()
        top.addWidget(label("Збережена перевірка", "Heading"))
        top.addStretch()
        self.export_button = QPushButton("Зберегти звіт")
        self.export_button.setIcon(icon("download"))
        self.export_menu = QMenu(self)
        for extension, title in (("txt", "Текстовий звіт (.txt)"), ("csv", "Таблиця CSV (.csv)")):
            self.export_menu.addAction(title, lambda checked=False, ext=extension: on_export(result, ext))
        self.export_button.setMenu(self.export_menu)
        top.addWidget(self.export_button)
        box.addLayout(top)
        box.addWidget(label("Збережений результат · поточні файли повторно не читаються", "Muted"))
        self.content = QPlainTextEdit()
        self.content.setReadOnly(True)
        self.content.setFont(QFont("Consolas", 10))
        box.addWidget(self.content)
        self._text, self._position = text, 0
        self._append_timer = QTimer(self)
        self._append_timer.setInterval(1)
        self._append_timer.timeout.connect(self._append_chunk)
        self._append_timer.start()

    def _append_chunk(self):
        cursor = self.content.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(self._text[self._position:self._position + 16384])
        self._position += 16384
        if self._position >= len(self._text):
            self._append_timer.stop()
            self._text = ""
            self.content.verticalScrollBar().setValue(0)

    def set_busy(self, busy):
        self.export_button.setEnabled(not busy)

    def closeEvent(self, event):
        self._append_timer.stop()
        super().closeEvent(event)
