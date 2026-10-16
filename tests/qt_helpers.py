"""Цикл подій Qt для перевірки асинхронного контролера у справжньому вікні."""

import time
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication


def application():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    return app


def pump(milliseconds=30):
    deadline = time.monotonic() + milliseconds / 1000
    while time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.002)


def finish_task(window, state):
    deadline = time.monotonic() + 15
    while state.busy and time.monotonic() < deadline:
        pump(5)
    assert not state.busy, "Фонова операція не завершилася вчасно"
    pump()


def dispose(window):
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    pump()
