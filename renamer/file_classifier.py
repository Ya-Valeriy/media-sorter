"""
Модуль классификации файлов по типу (фото/видео/прочее).

Классификация выполняется по расширению файла. Списки расширений
можно дополнить через аргументы командной строки.
"""

from __future__ import annotations

from pathlib import Path
from typing import AbstractSet, FrozenSet

# Расширения фото (перемещаются в папку *_photo)
DEFAULT_IMAGE_EXTENSIONS: FrozenSet[str] = frozenset({
    '.jpg', '.jpeg', '.png', '.heic', '.heif', '.tiff', '.tif',
    '.raw', '.cr2', '.cr3', '.nef', '.arw', '.dng',
    '.bmp', '.gif', '.webp', '.svg',
})

# Расширения видео (перемещаются в папку *_video)
DEFAULT_VIDEO_EXTENSIONS: FrozenSet[str] = frozenset({
    '.mp4', '.mov', '.avi', '.mkv', '.mts', '.m2ts', '.3gp',
    '.wmv', '.flv', '.webm', '.mpg', '.mpeg', '.m4v', '.vob',
})

# Типы файлов
TYPE_IMAGE: str = 'image'
TYPE_VIDEO: str = 'video'
TYPE_OTHER: str = 'other'


def parse_extensions(raw: str) -> FrozenSet[str]:
    """
    Разбирает строку расширений 'jpg,png, .mp4' в множество '.jpg', '.png', '.mp4'.

    Пустая строка даёт пустое множество.
    """
    result: set[str] = set()
    for part in raw.split(','):
        ext = part.strip().lower()
        if not ext:
            continue
        if not ext.startswith('.'):
            ext = '.' + ext
        result.add(ext)
    return frozenset(result)


def classify_file(
    path: Path,
    image_extensions: AbstractSet[str] = DEFAULT_IMAGE_EXTENSIONS,
    video_extensions: AbstractSet[str] = DEFAULT_VIDEO_EXTENSIONS,
) -> str:
    """
    Определяет тип файла по расширению.

    Возвращает 'image' | 'video' | 'other'.
    """
    ext = path.suffix.lower()
    if ext in image_extensions:
        return TYPE_IMAGE
    if ext in video_extensions:
        return TYPE_VIDEO
    return TYPE_OTHER