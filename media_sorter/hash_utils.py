"""
Модуль вычисления хэшей файлов и поиска дубликатов.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

logger = logging.getLogger(__name__)

# Размер буфера для чтения файла порциями (8 КБ)
HASH_BUFFER_SIZE: int = 8192


def get_file_hash(path: Path, buffer_size: int = HASH_BUFFER_SIZE) -> str:
    """
    Вычисляет MD5-хэш файла, читая его порциями по buffer_size байт.

    Позволяет обрабатывать большие файлы без загрузки в память целиком.
    """
    hasher = hashlib.md5()
    with open(path, 'rb') as fh:
        while chunk := fh.read(buffer_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_hash_index(files: Iterable[Path]) -> Dict[str, List[Path]]:
    """
    Строит индекс «хэш -> список файлов» для переданных файлов.

    Файлы, которые не удалось прочитать, пропускаются с предупреждением.
    """
    index: Dict[str, List[Path]] = {}
    for path in files:
        try:
            digest = get_file_hash(path)
        except OSError as exc:
            logger.warning('Не удалось вычислить хэш %s: %s', path, exc)
            continue
        index.setdefault(digest, []).append(path)
    return index


def find_duplicates(
    source_files: Iterable[Path],
    destination_index: Dict[str, List[Path]],
) -> Dict[str, Tuple[Path, Path]]:
    """
    Находит дубликаты: файлы из source_files, чей MD5-хэш уже есть в destination_index.

    Возвращает словарь «хэш -> (файл-источник, файл-назначение)».
    """
    duplicates: Dict[str, Tuple[Path, Path]] = {}
    for path in source_files:
        try:
            digest = get_file_hash(path)
        except OSError as exc:
            logger.warning('Не удалось вычислить хэш %s: %s', path, exc)
            continue
        if digest in destination_index:
            duplicates[digest] = (path, destination_index[digest][0])
    return duplicates