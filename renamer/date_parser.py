"""
Модуль определения года и месяца из имени папки.

Поддерживаемые форматы:
- Год: 2024, 2024_Яманкины, Photos_2024, 2024_yamankin_media
- Месяц-год: 05.2024, 2024-05, 05-2024, Май 2024, May_2024, 10.2017 Ч

Если дату из имени определить нельзя, используется EXIF-фолбэк:
год и месяц берутся из DateTimeOriginal самого старого фото в папке.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import AbstractSet, Optional, Tuple

logger = logging.getLogger(__name__)

# --- Словари месяцев (русские и английские названия) ---

MONTHS_RU: dict[str, int] = {
    'январь': 1, 'января': 1, 'янв': 1,
    'февраль': 2, 'февраля': 2, 'фев': 2,
    'март': 3, 'марта': 3, 'мар': 3,
    'апрель': 4, 'апреля': 4, 'апр': 4,
    'май': 5, 'мая': 5,
    'июнь': 6, 'июня': 6, 'июн': 6,
    'июль': 7, 'июля': 7, 'июл': 7,
    'август': 8, 'августа': 8, 'авг': 8,
    'сентябрь': 9, 'сентября': 9, 'сен': 9,
    'октябрь': 10, 'октября': 10, 'окт': 10,
    'ноябрь': 11, 'ноября': 11, 'ноя': 11,
    'декабрь': 12, 'декабря': 12, 'дек': 12,
}

MONTHS_EN: dict[str, int] = {
    'january': 1, 'jan': 1,
    'february': 2, 'feb': 2,
    'march': 3, 'mar': 3,
    'april': 4, 'apr': 4,
    'may': 5,
    'june': 6, 'jun': 6,
    'july': 7, 'jul': 7,
    'august': 8, 'aug': 8,
    'september': 9, 'sep': 9,
    'october': 10, 'oct': 10,
    'november': 11, 'nov': 11,
    'december': 12, 'dec': 12,
}

MONTHS: dict[str, int] = {**MONTHS_RU, **MONTHS_EN}

# --- Регулярные выражения ---

# Год: 2024 (4 цифры, не внутри большего числа)
YEAR_RE: re.Pattern[str] = re.compile(r'(?<!\d)(19\d{2}|20\d{2})(?!\d)')

# Диапазон годов: 2003-2005, 2003–2005, 2003 - 2005
YEAR_RANGE_RE: re.Pattern[str] = re.compile(
    r'(?<!\d)(19\d{2}|20\d{2})\s*[-–—]\s*(19\d{2}|20\d{2})(?!\d)'
)

# Месяц.год: 05.2024, 05-2024
MONTH_YEAR_RE: re.Pattern[str] = re.compile(
    r'(?<!\d)(\d{1,2})[.\-](\d{4})(?!\d)'
)

# Год-месяц: 2024-05
YEAR_MONTH_RE: re.Pattern[str] = re.compile(
    r'(?<!\d)(\d{4})[.\-](\d{1,2})(?!\d)'
)

# Название месяца + год: Май 2024, May_2024, май2024
MONTH_NAME_YEAR_RE: re.Pattern[str] = re.compile(
    r'(?i)(?<![a-zа-яё])'
    r'(янв|фев|мар|апр|май|июн|июл|авг|сен|окт|ноя|дек|'
    r'jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)'
    r'[а-яёa-z]*'
    r'[\s_\-.,]*'
    r'(\d{4})'
)

MIN_YEAR: int = 1900
MAX_YEAR: int = 2100


def parse_year(name: str) -> Optional[int]:
    """
    Определяет год из имени папки.

    Примеры: '2024' -> 2024, '2024_Яманкины' -> 2024, 'Photos_2024' -> 2024.
    Возвращает None, если год определить нельзя.
    """
    match = YEAR_RE.search(name)
    if not match:
        return None
    year = int(match.group(1))
    if MIN_YEAR <= year <= MAX_YEAR:
        return year
    return None


def is_year_range(name: str) -> bool:
    """
    Проверяет, является ли имя диапазоном годов (например, '2003-2005 Ч').

    Такие папки не обрабатываются, так как им нельзя сопоставить один год.
    """
    return YEAR_RANGE_RE.search(name) is not None


def parse_month_year(name: str) -> Optional[Tuple[int, int]]:
    """
    Определяет (месяц, год) из имени папки.

    Поддерживаемые форматы:
    - '05.2024', '05-2024' -> (5, 2024)
    - '2024-05' -> (5, 2024)
    - 'Май 2024', 'May_2024' -> (5, 2024)
    - '10.2017 Ч' -> (10, 2017)

    Возвращает None, если месяц и год определить нельзя.
    """
    # 1. Числовой формат «месяц.год» / «месяц-год»
    match = MONTH_YEAR_RE.search(name)
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12 and MIN_YEAR <= year <= MAX_YEAR:
            return month, year

    # 2. Числовой формат «год-месяц»
    match = YEAR_MONTH_RE.search(name)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12 and MIN_YEAR <= year <= MAX_YEAR:
            return month, year

    # 3. Название месяца + год
    match = MONTH_NAME_YEAR_RE.search(name)
    if match:
        month = MONTHS.get(match.group(1).lower())
        year = int(match.group(2))
        if month is not None and MIN_YEAR <= year <= MAX_YEAR:
            return month, year

    return None


# --- EXIF-фолбэк ---


def _parse_exif_datetime(value: str) -> Optional[datetime]:
    """Разбирает строку даты EXIF вида '2024:05:13 14:20:35'."""
    value = value.strip().strip('\x00')
    for fmt in ('%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y:%m:%d %H:%M:%S.%f'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def get_date_from_exif(path: Path) -> Optional[datetime]:
    """
    Читает дату съёмки (DateTimeOriginal) из EXIF через Pillow.

    Возвращает datetime или None (если Pillow не установлен,
    EXIF отсутствует или не читается).
    """
    try:
        from PIL import ExifTags, Image
    except ImportError:
        logger.debug('Pillow не установлен: EXIF недоступен')
        return None

    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            tags = {
                ExifTags.TAGS.get(tag_id, tag_id): value
                for tag_id, value in exif.items()
            }
            for tag_name in ('DateTimeOriginal', 'DateTimeDigitized', 'DateTime'):
                value = tags.get(tag_name)
                if value:
                    dt = _parse_exif_datetime(str(value))
                    if dt:
                        return dt
    except Exception as exc:
        logger.debug('Не удалось прочитать EXIF из %s: %s', path, exc)
    return None


def get_month_year_from_exif(
    folder: Path,
    image_extensions: AbstractSet[str],
) -> Optional[Tuple[int, int]]:
    """
    Определяет (месяц, год) по EXIF самого старого фото в папке.

    Файлы сортируются по дате изменения (mtime), берётся первое фото
    с читаемым EXIF. Возвращает None, если фото с EXIF нет.
    """
    images = [
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in image_extensions
    ]
    if not images:
        return None
    images.sort(key=lambda p: p.stat().st_mtime)
    for img in images:
        dt = get_date_from_exif(img)
        if dt:
            return dt.month, dt.year
    return None