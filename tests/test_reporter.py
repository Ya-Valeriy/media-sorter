"""
Unit-тесты для media_sorter/reporter.py и renamer/reporter.py:
- generate_report (структура CSV, BOM, игнор лишних полей, пустой отчёт)
- write_duplicates_log / write_errors_log / write_summary
- setup_logging (файл + консоль, очистка старых обработчиков)
"""

import csv
import logging
from pathlib import Path

import pytest

import media_sorter.reporter as ms_reporter
import renamer.reporter as rn_reporter
from media_sorter.reporter import REPORT_FIELDS as MS_FIELDS
from media_sorter.reporter import (
    generate_report as ms_generate_report,
    setup_logging as ms_setup_logging,
    write_duplicates_log,
    write_errors_log,
)
from renamer.reporter import REPORT_FIELDS as RN_FIELDS
from renamer.reporter import (
    generate_report as rn_generate_report,
    setup_logging as rn_setup_logging,
    write_errors_log as rn_write_errors_log,
    write_summary,
)


@pytest.fixture(autouse=True)
def _restore_logging():
    """После каждого теста возвращает корневому логгеру исходные обработчики."""
    root = logging.getLogger()
    saved = list(root.handlers)
    saved_level = root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in saved:
        root.addHandler(handler)
    root.setLevel(saved_level)


# ======================== media_sorter.reporter ========================


class TestGenerateReport:
    def test_header_fields(self, tmp_path):
        report = tmp_path / "report.csv"
        ms_generate_report([], report)
        with open(report, encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == MS_FIELDS
            assert list(reader) == []

    def test_utf8_bom(self, tmp_path):
        report = tmp_path / "report.csv"
        ms_generate_report([], report)
        assert report.read_bytes()[:3] == b"\xef\xbb\xbf"

    def test_row_written_and_extra_keys_ignored(self, tmp_path):
        report = tmp_path / "report.csv"
        records = [
            {
                "source_path": "src/тест.jpg",
                "dest_path": "dst/тест.jpg",
                "date_source": "filename",
                "date_value": "2024-05-13T14:20:35",
                "is_approximate": False,
                "warnings": "",
                "hash": "abc123",  # лишнее поле — должно быть проигнорировано
            }
        ]
        ms_generate_report(records, report)
        with open(report, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 1
        assert rows[0]["source_path"] == "src/тест.jpg"
        assert rows[0]["date_source"] == "filename"
        assert "hash" not in rows[0]

    def test_cyrillic_survives_excel_encoding(self, tmp_path):
        report = tmp_path / "report.csv"
        records = [{"source_path": "фото/отпуск.jpg", "dest_path": "d.jpg", "date_source": "", "date_value": "", "is_approximate": False, "warnings": "мелкий файл"}]
        ms_generate_report(records, report)
        text = report.read_text(encoding="utf-8-sig")
        assert "отпуск" in text
        assert "мелкий файл" in text


class TestDuplicatesLog:
    def test_writes_hash_and_paths(self, tmp_path):
        log = tmp_path / "duplicates.log"
        duplicates = [
            {"hash": "aaa", "source_path": "src/a.jpg", "dest_path": "dst/Дубликаты/a.jpg"},
            {"hash": "bbb", "source_path": "src/b.jpg", "dest_path": "dst/Дубликаты/b.jpg"},
        ]
        write_duplicates_log(duplicates, log)
        text = log.read_text(encoding="utf-8")
        assert "Хэш: aaa" in text
        assert "src/a.jpg" in text
        assert "Хэш: bbb" in text

    def test_empty_duplicates(self, tmp_path):
        log = tmp_path / "duplicates.log"
        write_duplicates_log([], log)
        assert log.exists()
        assert log.read_text(encoding="utf-8") == ""


class TestErrorsLog:
    def test_writes_path_and_error(self, tmp_path):
        log = tmp_path / "errors.log"
        errors = [{"source_path": "src/x.jpg", "dest_path": "", "error": "ошибка перемещения"}]
        write_errors_log(errors, log)
        text = log.read_text(encoding="utf-8")
        assert "src/x.jpg" in text
        assert "ошибка перемещения" in text

    def test_empty_errors(self, tmp_path):
        log = tmp_path / "errors.log"
        write_errors_log([], log)
        assert log.read_text(encoding="utf-8") == ""


class TestSetupLogging:
    def test_writes_to_file(self, tmp_path):
        log_file = tmp_path / "sort_media.log"
        ms_setup_logging(log_file, console_level=logging.CRITICAL)
        logging.getLogger("test.ms").info("тестовое сообщение")
        for handler in logging.getLogger().handlers:
            handler.flush()
        assert "тестовое сообщение" in log_file.read_text(encoding="utf-8")

    def test_replaces_old_handlers(self, tmp_path):
        """Повторный вызов не должен дублировать записи (старые обработчики удаляются)."""
        log1 = tmp_path / "one.log"
        log2 = tmp_path / "two.log"
        ms_setup_logging(log1, console_level=logging.CRITICAL)
        ms_setup_logging(log2, console_level=logging.CRITICAL)
        logging.getLogger("test.ms").warning("дубль")
        for handler in logging.getLogger().handlers:
            handler.flush()
        assert "дубль" not in log1.read_text(encoding="utf-8")
        assert "дубль" in log2.read_text(encoding="utf-8")


# ======================== renamer.reporter ========================


class TestRenamerGenerateReport:
    def test_header_fields(self, tmp_path):
        report = tmp_path / "report.csv"
        rn_generate_report([], report)
        with open(report, encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == RN_FIELDS
            assert list(reader) == []

    def test_utf8_bom_and_row(self, tmp_path):
        report = tmp_path / "report.csv"
        records = [
            {
                "old_path": "2024",
                "new_path": "2024_media",
                "type": "year",
                "action": "renamed",
                "files_count": 5,
                "warnings": "",
                "extra": "лишнее",
            }
        ]
        rn_generate_report(records, report)
        assert report.read_bytes()[:3] == b"\xef\xbb\xbf"
        with open(report, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        assert rows[0]["new_path"] == "2024_media"
        assert rows[0]["files_count"] == "5"
        assert "extra" not in rows[0]


class TestRenamerErrorsLog:
    def test_writes_path_and_error(self, tmp_path):
        log = tmp_path / "errors.log"
        rn_write_errors_log([{"path": "2024/05", "error": "нет доступа"}], log)
        text = log.read_text(encoding="utf-8")
        assert "2024/05" in text
        assert "нет доступа" in text


class TestWriteSummary:
    def test_full_stats(self, tmp_path):
        summary = tmp_path / "summary.txt"
        stats = {"years": 3, "months": 12, "images": 100, "videos": 40, "others": 2, "unknown": 1, "errors": 0}
        write_summary(stats, summary)
        text = summary.read_text(encoding="utf-8")
        assert "ИТОГОВАЯ СТАТИСТИКА" in text
        assert "Годовых папок обработано: 3" in text
        assert "Фото перемещено: 100" in text
        assert "Ошибок: 0" in text


# ======================== согласованность констант ========================


class TestReportFieldsConstants:
    def test_ms_fields_content(self):
        assert MS_FIELDS == [
            "source_path", "dest_path", "date_source", "date_value", "is_approximate", "warnings",
        ]

    def test_rn_fields_content(self):
        assert RN_FIELDS == ["old_path", "new_path", "type", "action", "files_count", "warnings"]
