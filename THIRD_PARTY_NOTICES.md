# Компоненти сторонніх розробників

FileGuard використовує Python, PySide6/Shiboken6 та Qt 6.10.3.
PySide6 і модулі Qt, використані у цьому застосунку, доступні за LGPL v3.
Тексти LGPL v3 та GPL v3, на яку вона посилається, наведено у папці licenses.

- [Qt for Python](https://doc.qt.io/qtforpython-6/)
- [Вихідний код PySide6/Shiboken6](https://code.qt.io/cgit/pyside/pyside-setup.git/?h=6.10.3)
- [Вихідний код Qt Base](https://code.qt.io/cgit/qt/qtbase.git/?h=6.10.3)
- [Вихідний код Qt SVG](https://code.qt.io/cgit/qt/qtsvg.git/?h=6.10.3)
- [Вихідний код Python](https://www.python.org/downloads/source/)

Вихідний код FileGuard і скрипт повторного збирання надаються у репозиторії
проєкту. Залежності Qt не модифіковані. Для іншої сумісної збірки Qt можна
створити окреме середовище Python, установити потрібні залежності й виконати
tools/build_windows.py. PyInstaller 6.22.3 використовується як засіб пакування.
