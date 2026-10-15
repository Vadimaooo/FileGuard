"""Перевірки поведінки MVC без створення графічного вікна."""

import tempfile
import unittest
from pathlib import Path

from app.controllers.app_controller import AppController
from app.models import AppState
from app.services.directory_service import DirectoryService


class FakeView:
    """Замінює лише діалог і відображення; файловий сервіс залишається справжнім."""

    def __init__(self) -> None:
        self.selection = ""
        self.initial_directory: str | None = None
        self.render_count = 0
        self.errors: list[tuple[str, str]] = []

    def render_state(self, state: AppState) -> None:
        self.render_count += 1

    def ask_directory(self, initial_directory: str | None) -> str:
        self.initial_directory = initial_directory
        return self.selection

    def show_error(self, title: str, message: str) -> None:
        self.errors.append((title, message))


class StageOneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name).resolve()
        self.state = AppState()
        self.view = FakeView()
        self.controller = AppController(self.state, self.view, DirectoryService())

    def test_unicode_folder_is_selected_without_changing_its_content(self) -> None:
        folder = self.folder / "Тестова папка з пробілами"
        folder.mkdir()
        source = folder / "Документ.txt"
        source.write_text("Початковий вміст", encoding="utf-8")
        self.view.selection = str(folder)
        self.controller.choose_folder()
        self.assertEqual(self.state.selected_folder, folder)
        self.assertEqual(source.read_text(encoding="utf-8"), "Початковий вміст")
        self.assertEqual(list(folder.iterdir()), [source])
        self.assertFalse(self.view.errors)

    def test_cancel_keeps_previous_folder_and_status(self) -> None:
        self.controller.select_folder(str(self.folder))
        previous_status = self.state.status_message
        previous_renders = self.view.render_count
        self.controller.choose_folder()
        self.assertEqual(self.state.selected_folder, self.folder)
        self.assertEqual(self.state.status_message, previous_status)
        self.assertEqual(self.view.initial_directory, str(self.folder))
        self.assertEqual(self.view.render_count, previous_renders)

    def test_missing_folder_does_not_replace_valid_selection(self) -> None:
        self.controller.select_folder(str(self.folder))
        self.assertFalse(self.controller.select_folder(str(self.folder / "відсутня")))
        self.assertEqual(self.state.selected_folder, self.folder)
        self.assertEqual(len(self.view.errors), 1)

    def test_file_cannot_be_selected_as_folder(self) -> None:
        source = self.folder / "file.txt"
        source.write_text("test", encoding="utf-8")
        self.assertFalse(self.controller.select_folder(str(source)))
        self.assertIsNone(self.state.selected_folder)
        self.assertIn("файлу", self.view.errors[0][1])

    def test_empty_path_is_rejected(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value):
                self.assertFalse(self.controller.select_folder(value))
        self.assertIsNone(self.state.selected_folder)

    def test_subfolder_option_updates_model_and_notifies_view(self) -> None:
        self.controller.set_include_subfolders(False)
        self.assertFalse(self.state.include_subfolders)
        self.controller.set_include_subfolders(True)
        self.assertTrue(self.state.include_subfolders)
        self.assertEqual(self.view.render_count, 2)


if __name__ == "__main__":
    unittest.main()
