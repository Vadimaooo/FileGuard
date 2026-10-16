"""Невеликі векторні значки: однакові форми для кнопок, меню та таблиць."""

from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


PATHS = {
    "shield": '<path d="M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6Z"/><path d="m8 12 3 3 5-6"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
    "settings": '<path d="m9 3 1-1h4l1 3 3 1 3-1 2 4-2 2v3l2 2-2 4-3-1-3 1-1 3h-4l-1-3-3-1-3 1-2-4 2-2v-3L1 9l2-4 3 1 3-1Z"/><circle cx="12" cy="12" r="3"/>',
    "folder": '<path d="M3 5h7l2 3h9v12H3Z"/>',
    "file": '<path d="M5 2h9l5 5v15H5Z"/><path d="M14 2v6h5M8 12h8M8 16h8"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "warning": '<path d="m12 3 10 18H2Z"/><path d="M12 9v5m0 3v1"/>',
    "changed": '<circle cx="12" cy="12" r="9"/><path d="M12 6v7m0 3v1"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 10v7m0-11v1"/>',
    "download": '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    "refresh": '<path d="M20 8a9 9 0 1 0 1 7M20 3v6h-6"/>',
    "close": '<path d="m6 6 12 12M6 18 18 6"/>',
    "maximize": '<rect x="5" y="5" width="14" height="14" rx="1"/>',
}


@lru_cache(maxsize=128)
def icon(name: str, color: str = "#62728b", size: int = 24) -> QIcon:
    """SVG малюється з подвійною щільністю, щоб залишатися чітким на HiDPI."""
    body = PATHS.get(name, PATHS["file"])
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
