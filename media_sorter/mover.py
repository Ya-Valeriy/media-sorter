"""
Модуль формирования путей назначения и безопасного перемещения файлов.
"""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from .date_extractor import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

logger = logging.getLogger(__name__)

# --- Специальные папки ---

FOLDER_UNDEFINED: str = 'Дата_не_определена'
FOLDER_DUPLICATES: str = 'Дубликаты'
FOLDER_JUNK: str = 'Мусор'

# --- Паттерны имён файлов из мессенджеров ---

MESSENGER_PATTERNS: dict[str, re.Pattern[str]] = {
    # WhatsApp: IMG-20240513-WA0001.jpg, VID-20240513-WA0002.mp4
    'whatsapp': re.compile(r'^(?:IMG|VID)-\d{8}-WA\d+\.', re.IGNORECASE),
    # Telegram: photo_2024-05-13_14-20-35.jpg, video_2024-05-13_14-20-35.mp4
    'telegram': re.compile(r'^(?:photo|video)_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.', re.IGNORECASE),
    # Viber: IMG_20240513_142035.jpg
    'viber': re.compile(r'^IMG_\d{8}_\d{6}\.', re.IGNORECASE),
}


def detect_messenger(filename: str) -> Optional[str]:
    """
    Определяет, из какого мессенджера файл, по паттернам имени.

    Возвращает 'whatsapp' | 'telegram' | 'viber' | None.
    """
    for name, pattern in MESSENGER_PATTERNS.items():
        if pattern.match(filename):
            return name
    return None


def is_junk_file(
    path: Path,
    photo_max_bytes: int,
    video_max_bytes: int,
) -> Optional[str]:
    """
    Определяет, является ли файл «мусором» (слишком маленьким).

    Фото (расширение из IMAGE_EXTENSIONS) размером <= photo_max_bytes
    и видео (VIDEO_EXTENSIONS) размером < video_max_bytes считаются мусором.

    Возвращает причину ('мелкий файл (фото <= 1 МБ)' / 'мелкий файл (видео < 50 МБ)')
    или None, если файл не является мусором.
    """
    ext = path.suffix.lower()
    try:
        size = path.stat().st_size
    except OSError as exc:
        logger.warning('Не удалось получить размер %s: %s', path, exc)
        return None
    if ext in IMAGE_EXTENSIONS and size <= photo_max_bytes:
        return f'мелкий файл (фото <= {photo_max_bytes / (1024 * 1024):g} МБ)'
    if ext in VIDEO_EXTENSIONS and size < video_max_bytes:
        return f'мелкий файл (видео < {video_max_bytes / (1024 * 1024):g} МБ)'
    return None


def build_renamed_filename(filename: str, date: Optional[datetime]) -> str:
    """
    Формирует новое имя файла по дате съёмки: 'ГГГГ-ММ-ДД_ЧЧ-ММ-СС' + расширение.

    Пример: 'IMG_20200325_114014.jpg' -> '2020-03-25_11-40-14.jpg'.
    Если дата не определена — возвращает исходное имя.
    """
    if date is None:
        return filename
    suffix = Path(filename).suffix
    return f'{date:%Y-%m-%d_%H-%M-%S}{suffix}'


def build_destination_path(
    dest_root: Path,
    filename: str,
    date: Optional[datetime] = None,
    special_folder: Optional[str] = None,
    rename_by_date: bool = False,
) -> Path:
    """
    Формирует путь назначения.

    Структура: <dest_root>/<Год>_media/<ММ.ГГГГ>_media/<ММ.ГГГГ>_photo|_video/<файл>.
    Если задан special_folder — файл кладётся в <dest_root>/<special_folder>/<файл>.
    Если дата не определена — в <dest_root>/Дата_не_определена/<файл>.

    При rename_by_date=True файл дополнительно переименовывается по дате
    (см. build_renamed_filename). Если даты нет — имя сохраняется.
    """
    if rename_by_date:
        filename = build_renamed_filename(filename, date)
    if special_folder:
        return dest_root / special_folder / filename
    if date is None:
        return dest_root / FOLDER_UNDEFINED / filename
    year_dir = f'{date.year}_media'
    month_dir = f'{date.month:02d}.{date.year}_media'
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return dest_root / year_dir / month_dir / f'{date.month:02d}.{date.year}_photo' / filename
    if ext in VIDEO_EXTENSIONS:
        return dest_root / year_dir / month_dir / f'{date.month:02d}.{date.year}_video' / filename
    return dest_root / year_dir / month_dir / filename


def resolve_collision(dest_path: Path) -> Path:
    """
    Разрешает коллизии имён: добавляет суффиксы _1, _2, _3...

    Если файл с таким именем уже существует, возвращает путь с суффиксом.
    """
    if not dest_path.exists():
        return dest_path
    parent = dest_path.parent
    stem = dest_path.stem
    suffix = dest_path.suffix
    counter = 1
    while True:
        candidate = parent / f'{stem}_{counter}{suffix}'
        if not candidate.exists():
            return candidate
        counter += 1


def move_file_safely(src: Path, dest: Path, dry_run: bool = False) -> Tuple[Path, str]:
    """
    Перемещает файл без перезаписи существующих.

    При dry_run только возвращает итоговый путь со статусом 'planned'.
    При успехе — (итоговый путь, 'moved').
    При ошибке — (запрошенный путь, 'error'), файл остаётся на месте.
    """
    dest = resolve_collision(dest)
    if dry_run:
        return dest, 'planned'
    try:
        # Создаём родительские папки (<Год>/<ММ.ГГГГ>/), если их ещё нет
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        return dest, 'moved'
    except (OSError, shutil.Error) as exc:
        logger.error('Не удалось переместить %s -> %s: %s', src, dest, exc)
        return dest, 'error'