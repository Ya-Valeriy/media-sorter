"""
Модуль генерации отчётов и настройки логирования.

Создаёт:
- report.csv — отчёт обо всех операциях
- errors.log — список ошибок
- summary.txt — итоговая статистика
- rename.log — полный лог операций (через logging)
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
REPORT_FIELDS: List[str] = [
    'old_path', 'new_path', 'type', 'action', 'files_count', 'warnings',
]


def setup_logging(log_file: Path) -> None:
    """
    Настраивает логирование: вывод в консоль (INFO+) и в файл (DEBUG+).

    В файл пишутся все уровни, в консоль — только информационные.
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
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)


def generate_report(records: Iterable[Dict[str, Any]], report_path: Path) -> None:
    """
    Записывает отчёт о реорганизации в CSV-файл.

    Кодировка utf-8-sig — для корректного открытия в Excel.
    """
    with open(report_path, 'w', newline='', encoding='utf-8-sig') as fh:
        writer = csv.DictWriter(fh, fieldnames=REPORT_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    logger.info('Отчёт сохранён: %s', report_path)


def write_errors_log(errors: Iterable[Dict[str, Any]], path: Path) -> None:
    """Записывает список ошибок в текстовый файл."""
    lines: List[str] = []
    for item in errors:
        lines.append(
            f"{datetime.now().isoformat(timespec='seconds')} | "
            f"{item.get('path', '')} | {item.get('error', '')}"
        )
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))
    logger.info('Лог ошибок сохранён: %s', path)


def write_summary(stats: Dict[str, Any], path: Path) -> None:
    """Записывает итоговую статистику в summary.txt."""
    lines: List[str] = [
        'ИТОГОВАЯ СТАТИСТИКА',
        '=' * 40,
        f'Годовых папок обработано: {stats["years"]}',
        f'Месячных папок обработано: {stats["months"]}',
        f'Фото перемещено: {stats["images"]}',
        f'Видео перемещено: {stats["videos"]}',
        f'Прочих файлов оставлено: {stats["others"]}',
        f'Папок с неопределённой датой: {stats["unknown"]}',
        f'Ошибок: {stats["errors"]}',
    ]
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    logger.info('Статистика сохранена: %s', path)