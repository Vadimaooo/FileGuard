"""Таблиця читає знімки моделі; тисячі рядків не створюють тисячі віджетів."""

from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QRectF, QSize
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from app.models import FileStatus
from app.views.icons import icon


TONES = {
    FileStatus.UNCHANGED: ("#168443", "#e5f7ec", "check"),
    FileStatus.CHANGED: ("#ad6507", "#fff1d8", "changed"),
    FileStatus.ADDED: ("#176ce9", "#e7f0ff", "plus"),
    FileStatus.DELETED: ("#d44655", "#ffebee", "minus"),
    FileStatus.ERROR: ("#8051c7", "#f1eaff", "warning"),
}


def display_size(size):
    if size is None:
        return "—"
    if size < 1024:
        return f"{size} Б"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} КіБ"
    return f"{size / (1024 * 1024):.1f} МіБ"


def display_modified(snapshot):
    if snapshot is None:
        return "—"
    try:
        return datetime.fromtimestamp(snapshot.modified_ns / 1e9).strftime("%d.%m.%Y %H:%M")
    except (OSError, OverflowError, ValueError):
        return "Дата недоступна"


class ResultsModel(QAbstractTableModel):
    headers = ("Файл", "Статус", "Розмір", "Остання зміна")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = ()
        self.is_result = False

    def set_rows(self, rows, is_result):
        self.beginResetModel()
        self.rows, self.is_result = rows, is_result
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.rows[index.row()]
        snapshot = item.actual if self.is_result else item
        if role == Qt.ItemDataRole.UserRole and self.is_result:
            return item.status.value
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            return icon("file", "#28824c" if item.path.lower().endswith(".csv") else "#7e8da4", 20)
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.path + ("\n" + item.message if self.is_result else "")
        if role == Qt.ItemDataRole.DisplayRole:
            return (item.path, item.status.value if self.is_result else "В еталоні",
                    display_size(snapshot.size if snapshot else None), display_modified(snapshot))[index.column()]


class StatusDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        value = index.data(Qt.ItemDataRole.UserRole)
        if value not in TONES:
            return super().paint(painter, option, index)
        status = FileStatus(value)
        foreground, background, symbol = TONES[status]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#eaf2ff"))
        text = status.value
        width = min(option.rect.width() - 12, option.fontMetrics.horizontalAdvance(text) + 42)
        rect = QRectF(option.rect.x() + 6, option.rect.center().y() - 13, width, 26)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(rect, 13, 13)
        icon(symbol, foreground, 16).paint(painter, int(rect.x()) + 8, int(rect.y()) + 5, 16, 16)
        painter.setPen(QColor(foreground))
        painter.drawText(rect.adjusted(29, 0, -5, 0), Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()
