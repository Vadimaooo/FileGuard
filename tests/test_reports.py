"""Перевірки повноти експорту, CSV та безпечного перезапису."""

import csv
import io
import unittest
from dataclasses import replace
from threading import Event
from unittest.mock import patch

from app.controllers.app_controller import AppController
from app.models import AppState, FileStatus
from app.services.directory_service import DirectoryService
from app.services.integrity_service import OperationCancelled
from app.services.report_service import ReportService
from test_history import HistoryFixture, HistoryView


class ExportView(HistoryView):
    def ask_save_report(self, directory, filename, extension):
        self.extension = extension
        return self.report_path


class ReportTests(HistoryFixture, unittest.TestCase):
    def test_txt_contains_metadata_all_hashes_and_statuses(self):
        target = self.root / "report.txt"
        ReportService().export(self.result, str(target), "txt", Event())
        text = target.read_text(encoding="utf-8")
        self.assertIn("Усього записів: 1", text)
        self.assertIn(self.result.files[0].actual.sha256, text)
        self.assertIn("Документ.txt", text)

    def test_csv_preserves_unicode_quoting_and_neutralizes_formula_cells(self):
        row = self.result.files[0]
        special = replace(row, path="=formula.txt", message='Причина; "текст"\nДругий рядок')
        result = replace(self.result, files=(special,))
        target = self.root / "report.csv"
        ReportService().export(result, str(target), "csv", Event())
        raw = target.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(rows[0]["Файл"], "'=formula.txt")
        self.assertEqual(rows[0]["Пояснення"], special.message)
        self.assertEqual(rows[0]["Усього"], "1")

    def test_empty_result_still_exports_metadata(self):
        target = self.root / "empty.csv"
        ReportService().export(replace(self.result, files=()), str(target), "csv", Event())
        with target.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(rows[0]["Усього"], "0")
        self.assertEqual(rows[0]["Файл"], "")

    def test_source_file_cannot_be_overwritten_by_export(self):
        target = self.result.baseline.root_folder / "Документ.txt"
        with self.assertRaises(ValueError):
            ReportService().export(self.result, str(target), "txt", Event())
        self.assertEqual(target.read_bytes(), b"abc")

    def test_cancel_or_write_failure_preserves_existing_report(self):
        target = self.root / "report.txt"
        target.write_bytes(b"old report")
        cancel = Event()
        cancel.set()
        with self.assertRaises(OperationCancelled):
            ReportService().export(self.result, str(target), "txt", cancel)
        with patch("app.services.atomic_file.os.replace", side_effect=PermissionError("Зайнято")):
            with self.assertRaises(PermissionError):
                ReportService().export(self.result, str(target), "txt", Event())
        self.assertEqual(target.read_bytes(), b"old report")
        self.assertFalse(list(self.root.glob(".fileguard-*.tmp")))

    def test_controller_exports_whole_result_even_when_filter_hides_it(self):
        view = ExportView()
        view.report_path = str(self.root / "full.csv")
        state = AppState(check_result=self.result, baseline=self.result.baseline, status_filter=FileStatus.ERROR)
        controller = AppController(state, view, DirectoryService())
        controller.export_result(extension="csv")
        self.finish(controller, view)
        with open(view.report_path, encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(len(list(csv.DictReader(stream, delimiter=";"))), 1)
        self.assertEqual(view.extension, "csv")
