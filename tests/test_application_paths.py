"""У збірці історія та налаштування повинні зберігатися біля exe."""

import unittest
from pathlib import Path
from unittest.mock import patch

from app.paths import application_directory
from app.services.baseline_storage import BaselineStorage
from app.services.report_service import ReportService


class ApplicationPathsTests(unittest.TestCase):
    def test_source_paths_are_relative_to_project_and_not_working_directory(self):
        self.assertEqual(application_directory(), Path(__file__).resolve().parents[1])
        self.assertEqual(BaselineStorage().default_directory, application_directory() / "data")
        self.assertEqual(ReportService().default_directory, application_directory() / "reports")

    def test_frozen_paths_use_executable_instead_of_temporary_bundle(self):
        executable = Path(__file__).resolve().parent / "Переносна збірка" / "FileGuard.exe"
        with patch("app.paths.sys.frozen", True, create=True), patch("app.paths.sys.executable", str(executable)):
            self.assertEqual(application_directory(), executable.parent)
            self.assertEqual(BaselineStorage().default_directory, executable.parent / "data")
            self.assertEqual(ReportService().default_directory, executable.parent / "reports")
