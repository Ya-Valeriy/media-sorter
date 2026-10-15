"""
Модуль генерации отчётов и настройки логирования.
"""

from __future__ import annotations

import csv
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

logger = logging.getLogger(__name__)

# Столбцы CSV-отчёта
REPORT_FIELDS: list[str] = [
    'source_path', 'dest_path', 'date_source', 'date_value', 'is_approximate', 'warnings',
]


def setup_logging(
    log_file: Path,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
) -> None:
    """
    Настраивает логирование: вывод в консоль и в файл.

    В файл пишутся все уровни (DEBUG+), в консоль — INFO+.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Убираем существующие обработчики, чтобы не дублировать записи
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)


def generate_report(records: Iterable[Dict[str, Any]], report_path: Path) -> None:
    """
    Записывает отчёт о сортировке в CSV-файл.

    Кодировка utf-8-sig — для корректного открытия в Excel.
    """
    with open(report_path, 'w', newline='', encoding='utf-8-sig') as fh:
        writer = csv.DictWriter(fh, fieldnames=REPORT_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    logger.info('Отчёт сохранён: %s', report_path)


def write_duplicates_log(duplicates: Iterable[Dict[str, Any]], path: Path) -> None:
    """Записывает список дубликатов с хэшами в текстовый файл."""
    lines: list[str] = []
    for item in duplicates:
        lines.append(f"Хэш: {item.get('hash', '')}")
        lines.append(f"  Источник: {item.get('source_path', '')}")
        lines.append(f"  Дубликат: {item.get('dest_path', '')}")
        lines.append('')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))
    logger.info('Лог дубликатов сохранён: %s', path)


def write_errors_log(errors: Iterable[Dict[str, Any]], path: Path) -> None:
    """Записывает список ошибок обработки в текстовый файл."""
    lines: list[str] = []
    for item in errors:
        lines.append(
            f"{datetime.now().isoformat(timespec='seconds')} | "
            f"{item.get('source_path', '')} | {item.get('error', '')}"
        )
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))
    logger.info('Лог ошибок сохранён: %s', path)