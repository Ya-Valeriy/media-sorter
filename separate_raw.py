#!/usr/bin/env python3
"""
Скрипт для отделения RAW-файлов в отдельную папку.

Пример:
    python separate_raw.py --source "D:\\Photos\\Unsorted" --destination "D:\\Photos\\RAW" --move
    python separate_raw.py --source "D:\\Photos\\Unsorted" --dry-run
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Set

RAW_EXTENSIONS: frozenset[str] = frozenset({
    '.raw', '.cr2', '.cr3', '.nef', '.arw', '.dng',
})

logger = logging.getLogger(__name__)


def parse_args(argv: List[str] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='separate_raw',
        description='Отделяет RAW-файлы в отдельную папку.',
    )
    parser.add_argument('--source', '-s', required=True, help='Папка-источник')
    parser.add_argument('--destination', '-d', required=True, help='Папка для RAW-файлов')
    parser.add_argument('--dry-run', action='store_true', help='Показать план без выполнения')
    parser.add_argument('--move', action='store_true', help='Переместить файлы (по умолчанию — копировать)')
    parser.add_argument('--recursive', '-r', action='store_true', help='Рекурсивный поиск')
    parser.add_argument('--log-file', default='separate_raw.log', help='Путь к файлу лога')
    return parser.parse_args(argv)


def collect_raw_files(root: Path, recursive: bool = False) -> List[Path]:
    files: List[Path] = []
    if recursive:
        for path in root.rglob('*'):
            if path.is_file() and path.suffix.lower() in RAW_EXTENSIONS:
                files.append(path)
    else:
        for path in root.iterdir():
            if path.is_file() and path.suffix.lower() in RAW_EXTENSIONS:
                files.append(path)
    return sorted(files)


def separate_files(
    source: Path,
    dest: Path,
    files: List[Path],
    dry_run: bool = False,
    move: bool = False,
) -> Dict[str, int]:
    stats = {'total': len(files), 'copied': 0, 'moved': 0, 'errors': 0}

    for file_path in files:
        dest_path = dest / file_path.name

        # Разрешение коллизий
        if dest_path.exists():
            stem = dest_path.stem
            suffix = dest_path.suffix
            counter = 1
            while True:
                candidate = dest_path.parent / f'{stem}_{counter}{suffix}'
                if not candidate.exists():
                    dest_path = candidate
                    break
                counter += 1

        if dry_run:
            logger.info(f'ПЛАНИРУЕТСЯ: {file_path} -> {dest_path}')
            stats['copied'] += 1
        else:
            try:
                if move:
                    shutil.move(str(file_path), str(dest_path))
                    logger.info(f'ПЕРЕМЕЩЁН: {file_path} -> {dest_path}')
                    stats['moved'] += 1
                else:
                    shutil.copy2(str(file_path), str(dest_path))
                    logger.info(f'СКОПИРОВАН: {file_path} -> {dest_path}')
                    stats['copied'] += 1
            except OSError as exc:
                logger.error(f'ОШИБКА: {file_path} -> {exc}')
                stats['errors'] += 1

    return stats


def main(argv: List[str] = None) -> int:
    args = parse_args(argv)
    source = Path(args.source)
    dest = Path(args.destination)

    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(args.log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Валидация
    if not source.exists() or not source.is_dir():
        print(f'ОШИБКА: Папка не существует: {source}', file=sys.stderr)
        return 1

    # Сбор RAW-файлов
    files = collect_raw_files(source, args.recursive)
    print(f'Найдено RAW-файлов: {len(files)}')
    if not files:
        print('RAW-файлы не найдены.')
        return 0

    print(f'Режим: {"пробный прогон" if args.dry_run else ("перемещение" if args.move else "копирование")}')
    print(f'Источник: {source}')
    print(f'Назначение: {dest}')
    print()

    if not args.dry_run and not args.move:
        answer = input('Копировать RAW-файлы? [y/N]: ').strip().lower()
        if answer not in ('y', 'yes', 'д', 'да'):
            print('Отменено.')
            return 0

    if not args.dry_run:
        dest.mkdir(parents=True, exist_ok=True)

    stats = separate_files(source, dest, files, args.dry_run, args.move)

    print()
    print(f'Всего: {stats["total"]}')
    print(f'Скопировано: {stats["copied"]}')
    print(f'Перемещено: {stats["moved"]}')
    print(f'Ошибок: {stats["errors"]}')

    return 0 if stats['errors'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
