"""
Модуль безопасного перемещения файлов и папок.

Файлы и папки перемещаются через shutil.move без перезаписи существующих.
При ошибке объект остаётся на месте, а ошибка логируется.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Tuple

from .renamer import resolve_collision

logger = logging.getLogger(__name__)


def move_file_safely(src: Path, dest_dir: Path, dry_run: bool = False) -> Tuple[Path, str]:
    """
    Перемещает файл src в папку dest_dir без перезаписи существующих.

    При dry_run возвращает (итоговый путь, 'planned') без изменений.
    При успехе — (итоговый путь, 'moved').
    При ошибке — (запрошенный путь, 'error'), файл остаётся на месте.
    """
    dest = resolve_collision(dest_dir / src.name)
    if dry_run:
        return dest, 'planned'
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        return dest, 'moved'
    except (OSError, shutil.Error) as exc:
        logger.error('Не удалось переместить %s -> %s: %s', src, dest, exc)
        return dest, 'error'


def move_dir_safely(src: Path, dest: Path, dry_run: bool = False) -> Tuple[Path, str]:
    """
    Перемещает (переименовывает) папку src в dest без перезаписи.

    При dry_run возвращает (итоговый путь, 'planned') без изменений.
    При успехе — (итоговый путь, 'moved').
    При ошибке — (запрошенный путь, 'error'), папка остаётся на месте.
    """
    if dry_run:
        return dest, 'planned'
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        return dest, 'moved'
    except (OSError, shutil.Error) as exc:
        logger.error('Не удалось переместить папку %s -> %s: %s', src, dest, exc)
        return dest, 'error'