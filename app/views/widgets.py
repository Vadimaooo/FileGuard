"""Повторно використовувані елементи Qt: перемикач, картка та рамка вікна."""

from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QCheckBox, QFrame, QLabel, QVBoxLayout, QWidget


def label(text="", name="", parent=None):
    widget = QLabel(text, parent)
    widget.setObjectName(name)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


class Switch(QCheckBox):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(text)

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 65, 32)

    def hitButton(self, point):
        return self.rect().contains(point)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(1 if self.isEnabled() else 0.45)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1675ff" if self.isChecked() else "#ced6e3"))
        painter.drawRoundedRect(0, 5, 43, 23, 11.5, 11.5)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(23 if self.isChecked() else 3, 8, 17, 17)
        painter.setPen(QColor("#26334c"))
        painter.drawText(self.rect().adjusted(54, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, self.text())
        if self.hasFocus():
            painter.setPen(QPen(QColor("#579aff"), 1, Qt.PenStyle.DotLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(0, 1, -1, -1), 8, 8)


class Card(QFrame):
    def __init__(self, parent=None, name="Card", margins=20):
        super().__init__(parent)
        self.setObjectName(name)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(margins, margins, margins, margins)
        self.box.setSpacing(12)


class WindowFrame(QWidget):
    """Рамка підтримує системне перетягування, зміну розміру та Alt+F4."""
    def __init__(self):
        super().__init__()
        self.glass_active = False
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowSystemMenuHint | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        QApplication.instance().installEventFilter(self)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background = QColor(244, 248, 255, 115) if self.glass_active else QColor("#eaf1fd")
        painter.setBrush(background)
        painter.setPen(QPen(QColor(222, 231, 245, 180), 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 18, 18)

    def eventFilter(self, watched, event):
        if (event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton
                and isinstance(watched, QWidget) and watched.window() is self and not self.isMaximized()):
            point = self.mapFromGlobal(event.globalPosition().toPoint())
            edges = Qt.Edge(0)
            if point.x() < 6:
                edges |= Qt.Edge.LeftEdge
            elif point.x() >= self.width() - 6:
                edges |= Qt.Edge.RightEdge
            if point.y() < 6:
                edges |= Qt.Edge.TopEdge
            elif point.y() >= self.height() - 6:
                edges |= Qt.Edge.BottomEdge
            if edges and self.windowHandle():
                return self.windowHandle().startSystemResize(edges)
        return super().eventFilter(watched, event)


class DragBar(QWidget):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        window = self.window()
        window.showNormal() if window.isMaximized() else window.showMaximized()
