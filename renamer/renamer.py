"""
Модуль формирования новых имён папок и разрешения коллизий имён.

Целевая структура:
<Корень>/
├── <гггг>_media/
│   └── <мм.гггг>_media/
│       ├── <мм.гггг>_photo/
│       └── <мм.гггг>_video/
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def year_folder_name(year: int) -> str:
    """Формирует имя годовой папки: '<гггг>_media'."""
    return f'{year}_media'


def month_folder_name(month: int, year: int) -> str:
    """Формирует имя месячной папки: '<мм.гггг>_media'."""
    return f'{month:02d}.{year}_media'


def image_folder_name(month: int, year: int) -> str:
    """Формирует имя папки с фото: '<мм.гггг>_photo'."""
    return f'{month:02d}.{year}_photo'


def video_folder_name(month: int, year: int) -> str:
    """Формирует имя папки с видео: '<мм.гггг>_video'."""
    return f'{month:02d}.{year}_video'


def resolve_collision(path: Path) -> Path:
    """
    Разрешает коллизию имён: добавляет суффиксы _1, _2, _3...

    Если путь (файл или папка) уже существует, возвращает путь с суффиксом.
    Существующие файлы никогда не перезаписываются.
    """
    if not path.exists():
        return path
    parent = path.parent
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = parent / f'{stem}_{counter}{suffix}'
        if not candidate.exists():
            return candidate
        counter += 1