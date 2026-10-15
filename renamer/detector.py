"""
Модуль определения уровня архива по содержимому корневой папки.

Скрипт может быть запущен с любой точки входа:
- корень архива (внутри годовые папки) -> обработка по годам и месяцам;
- годовая папка (внутри месячные папки) -> обработка по месяцам;
- месячная папка (внутри только файлы) -> перенос в структуру года/месяца.

Уровень определяется по большинству прямых потомков папки.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

from .date_parser import is_year_range, parse_month_year, parse_year

logger = logging.getLogger(__name__)

# Уровни архива
LEVEL_ARCHIVE_ROOT: str = 'archive_root'
LEVEL_YEAR: str = 'year'
LEVEL_MONTH: str = 'month'
LEVEL_UNKNOWN: str = 'unknown'


def _is_year_dir_name(name: str) -> bool:
    """
    Проверяет, что имя подходит под годовую папку.

    Годовая папка: содержит год, не является диапазоном годов
    и не является месячной папкой (например, '05-2024' — это месяц).
    """
    if is_year_range(name):
        return False
    if parse_month_year(name) is not None:
        return False
    return parse_year(name) is not None


def _split_children(root: Path) -> Tuple[List[Path], List[Path]]:
    """Возвращает (подпапки, файлы) — прямые потомки root."""
    dirs: List[Path] = []
    files: List[Path] = []
    for child in root.iterdir():
        if child.is_dir():
            dirs.append(child)
        elif child.is_file():
            files.append(child)
    return dirs, files


def detect_level(root: Path) -> str:
    """
    Определяет уровень архива по содержимому папки root.

    Возвращает одну из констант LEVEL_*:
    - LEVEL_ARCHIVE_ROOT: большинство подпапок — годовые;
    - LEVEL_YEAR: большинство подпапок — месячные;
    - LEVEL_MONTH: подпапок нет, есть только файлы;
    - LEVEL_UNKNOWN: структура не распознана.
    """
    dirs, files = _split_children(root)
    if not dirs and not files:
        return LEVEL_UNKNOWN

    year_dirs = [d for d in dirs if _is_year_dir_name(d.name)]
    month_dirs = [d for d in dirs if parse_month_year(d.name) is not None]

    if year_dirs and len(year_dirs) >= len(month_dirs):
        return LEVEL_ARCHIVE_ROOT
    if month_dirs and len(month_dirs) > len(year_dirs):
        return LEVEL_YEAR
    if files and not dirs:
        return LEVEL_MONTH
    return LEVEL_UNKNOWN