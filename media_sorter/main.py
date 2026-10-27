"""
Точка входа: CLI-интерфейс для сортировки медиафайлов.

Пример использования:
    python sort_media.py --source "D:\\Photos\\Unsorted" --destination "D:\\Photos\\Sorted" \
        --dry-run --check-duplicates
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .date_extractor import RAW_EXTENSIONS, SUPPORTED_EXTENSIONS, get_creation_date, is_scanned_negative
from .hash_utils import get_file_hash
from .mover import (
    FOLDER_DUPLICATES,
    FOLDER_JUNK,
    FOLDER_NEGATIVES,
    build_destination_path,
    detect_messenger,
    is_junk_file,
    move_file_safely,
)
from .reporter import generate_report, setup_logging, write_duplicates_log, write_errors_log

logger = logging.getLogger(__name__)

# Порог количества файлов, при котором включается многопоточность
THREADING_THRESHOLD: int = 10_000


@dataclass
class ProcessResult:
    """Результат обработки одного файла."""

    record: Dict[str, Any]
    category: str  # 'ok' | 'duplicate' | 'error'
    date: Optional[datetime] = None
    messenger: Optional[str] = None


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Разбирает аргументы командной строки."""
    default_extensions = ','.join(sorted(SUPPORTED_EXTENSIONS))

    parser = argparse.ArgumentParser(
        prog='sort_media',
        description='Сортировка медиафайлов по дате съёмки.',
        epilog='Пример: python sort_media.py -s "D:\\Photos\\Unsorted" -d "D:\\Photos\\Sorted" --dry-run',
    )
    parser.add_argument('--source', '-s', required=True, help='Путь к папке-источнику')
    parser.add_argument('--destination', '-d', required=True, help='Путь к папке-назначению')
    parser.add_argument('--dry-run', action='store_true', help='Пробный прогон без перемещения файлов')
    parser.add_argument('--check-duplicates', action='store_true', help='Проверять дубликаты по MD5')
    parser.add_argument(
        '--junk-folder',
        default='Мусор',
        help='Имя папки для мелких файлов (по умолчанию: Мусор)',
    )
    parser.add_argument(
        '--photo-junk-max-kb',
        type=float,
        default=2048.0,
        help='Максимальный размер фото для папки «Мусор» в КБ (0 — не задано; по умолчанию: 2048)',
    )
    parser.add_argument(
        '--video-junk-max-sec',
        type=float,
        default=10.0,
        help='Максимальная длительность видео для папки «Мусор» в секундах (0 — не задано; по умолчанию: 10)',
    )
    parser.add_argument(
        '--video-junk-max-kb',
        type=float,
        default=0.0,
        help='Максимальный размер видео для папки «Мусор» в КБ (0 — не задано; по умолчанию: 0)',
    )
    parser.add_argument(
        '--no-junk',
        action='store_true',
        help='Не выделять мелкие файлы в отдельную папку',
    )
    parser.add_argument(
        '--no-rename',
        action='store_true',
        help='Не переименовывать файлы по дате съёмки (имена сохраняются)',
    )
    parser.add_argument(
        '--negative-folder',
        default='Негативы',
        help='Имя папки для сканированных негативов (по умолчанию: Негативы)',
    )
    parser.add_argument(
        '--no-negative',
        action='store_true',
        help='Не определять и не выделять сканированные негативы',
    )
    parser.add_argument('--log-file', default='sort_media.log', help='Путь к файлу лога (по умолчанию: sort_media.log)')
    parser.add_argument('--report-file', default='report.csv', help='Путь к CSV-отчёту (по умолчанию: report.csv)')
    parser.add_argument('--duplicates-log', default='duplicates.log', help='Путь к логу дубликатов (по умолчанию: duplicates.log)')
    parser.add_argument('--errors-log', default='errors.log', help='Путь к логу ошибок (по умолчанию: errors.log)')
    parser.add_argument(
        '--extensions',
        default=default_extensions,
        help='Список расширений через запятую (по умолчанию: все поддерживаемые)',
    )
    parser.add_argument('--workers', type=int, default=1, help='Количество потоков (по умолчанию: 1)')
    parser.add_argument('--yes', action='store_true', help='Не запрашивать подтверждение перед перемещением')
    return parser.parse_args(argv)


def validate_paths(source: Path, dest: Path) -> Optional[str]:
    """
    Проверяет корректность путей source и destination.

    Возвращает сообщение об ошибке или None, если всё в порядке.
    """
    if not source.exists():
        return f'Папка-источник не существует: {source}'
    if not source.is_dir():
        return f'Путь-источник не является директорией: {source}'
    if dest.exists() and not dest.is_dir():
        return f'Путь-назначение не является директорией: {dest}'
    try:
        if source.resolve() == dest.resolve():
            return f'Папки-источник и назначение совпадают: {source}'
    except OSError:
        pass
    return None


def _is_relative_to(path: Path, other: Path) -> bool:
    """Проверяет, находится ли path внутри other (кроссплатформенно)."""
    try:
        path.resolve().relative_to(other.resolve())
        return True
    except ValueError:
        return False


def _parse_extensions(raw: str) -> Set[str]:
    """Разбирает строку расширений 'jpg,png,mp4' в множество '.jpg', '.png'."""
    result: Set[str] = set()
    for part in raw.split(','):
        ext = part.strip().lower()
        if not ext:
            continue
        if not ext.startswith('.'):
            ext = '.' + ext
        result.add(ext)
    return result


def collect_media_files(root: Path, extensions: Set[str], exclude: Optional[Path] = None) -> List[Path]:
    """
    Рекурсивно собирает медиафайлы в папке root.

    Если задан exclude — файлы внутри этой папки пропускаются
    (используется, когда destination находится внутри source).
    """
    files: List[Path] = []
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        if exclude is not None and _is_relative_to(path, exclude):
            continue
        if path.suffix.lower() in extensions:
            files.append(path)
    return sorted(files)


def _iter_with_progress(items: List[Path], desc: str = ''):
    """Обёртка над tqdm (если установлен), иначе обычный итератор."""
    try:
        from tqdm import tqdm

        return tqdm(items, desc=desc, unit='file', ncols=100)
    except ImportError:
        return items


def _make_duplicate_result(
    file_path: Path,
    dest: Path,
    digest: str,
    warnings: List[str],
    args: argparse.Namespace,
    date: Optional[datetime] = None,
) -> ProcessResult:
    """Формирует результат для файла-дубликата (перемещение в «Дубликаты») с переименованием по дате."""
    dup_dest = build_destination_path(
        dest, file_path.name, date, FOLDER_DUPLICATES, rename_by_date=True
    )
    final_path, status = move_file_safely(file_path, dup_dest, args.dry_run)
    record = {
        'source_path': str(file_path),
        'dest_path': str(final_path),
        'date_source': 'duplicate',
        'date_value': date.isoformat() if date else '',
        'is_approximate': False,
        'warnings': '; '.join(warnings + ['дубликат (MD5 совпадает)']),
        'hash': digest,
    }
    logger.warning('Дубликат: %s (MD5: %s) -> %s', file_path, digest, final_path)
    return ProcessResult(record=record, category='duplicate', date=date)


def process_single_file(
    file_path: Path,
    source: Path,
    dest: Path,
    args: argparse.Namespace,
    seen_hashes: Set[str],
    lock: threading.Lock,
) -> ProcessResult:
    """
    Обрабатывает один файл: определяет дату, формирует путь, перемещает.

    Возвращает ProcessResult с записью для отчёта.
    """
    filename = file_path.name
    warnings: List[str] = []

    # 1. Определяем мессенджер (только для статистики)
    messenger = detect_messenger(filename)

    # 2. Проверка «мусорности»: мелкие файлы в отдельную папку
    if not args.no_junk:
        photo_max = int(args.photo_junk_max_kb * 1024) if args.photo_junk_max_kb > 0 else None
        video_sec = args.video_junk_max_sec if args.video_junk_max_sec > 0 else None
        video_kb = int(args.video_junk_max_kb * 1024) if args.video_junk_max_kb > 0 else None
        junk_reason = is_junk_file(file_path, photo_max, video_sec, video_kb)
        if junk_reason:
            junk_dest = build_destination_path(dest, filename, None, FOLDER_JUNK)
            final_path, status = move_file_safely(file_path, junk_dest, args.dry_run)
            record = {
                'source_path': str(file_path),
                'dest_path': str(final_path),
                'date_source': '',
                'date_value': '',
                'is_approximate': False,
                'warnings': '; '.join(warnings + [junk_reason]),
            }
            logger.info(
                '%s: %s -> %s (%s)',
                'ПЛАНИРУЕТСЯ' if args.dry_run else 'ПЕРЕМЕЩЁН',
                file_path,
                final_path,
                junk_reason,
            )
            return ProcessResult(record=record, category='junk', date=None, messenger=messenger)

    # 3. Проверка на сканированный негатив (RAW от сканера)
    is_negative = False
    if not args.no_negative and file_path.suffix.lower() in RAW_EXTENSIONS:
        try:
            is_negative = is_scanned_negative(file_path)
        except Exception as exc:  # noqa: BLE001
            logger.debug('Не удалось проверить негатив %s: %s', file_path, exc)

    if is_negative:
        neg_dest = build_destination_path(dest, filename, None, FOLDER_NEGATIVES)
        final_path, status = move_file_safely(file_path, neg_dest, args.dry_run)
        record = {
            'source_path': str(file_path),
            'dest_path': str(final_path),
            'date_source': '',
            'date_value': '',
            'is_approximate': False,
            'warnings': 'сканированный негатив (RAW)',
        }
        logger.info(
            '%s: %s -> %s (негатив)',
            'ПЛАНИРУЕТСЯ' if args.dry_run else 'ПЕРЕМЕЩЁН',
            file_path,
            final_path,
        )
        return ProcessResult(record=record, category='negative', date=None, messenger=messenger)

    # 4. Определяем дату съёмки (только метаданные или имя файла, без mtime)
    date, date_source, is_approximate = get_creation_date(file_path)

    # 5. Формируем путь назначения (переименование по дате — если включено)
    dest_path = build_destination_path(
        dest, filename, date, None, rename_by_date=not args.no_rename,
    )

    # 6. Проверка дубликатов
    if args.check_duplicates:
        try:
            digest = get_file_hash(file_path)
        except OSError as exc:
            warnings.append(f'не удалось вычислить хэш: {exc}')
            digest = None
        if digest:
            with lock:
                if digest in seen_hashes:
                    return _make_duplicate_result(file_path, dest, digest, warnings, args)
                seen_hashes.add(digest)

    # 7. Перемещение
    final_path, status = move_file_safely(file_path, dest_path, args.dry_run)

    if status == 'error':
        record = {
            'source_path': str(file_path),
            'dest_path': str(dest_path),
            'date_source': date_source or '',
            'date_value': date.isoformat() if date else '',
            'is_approximate': is_approximate,
            'warnings': '; '.join(warnings + ['ошибка перемещения']),
        }
        return ProcessResult(record=record, category='error', date=date, messenger=messenger)

    record = {
        'source_path': str(file_path),
        'dest_path': str(final_path),
        'date_source': date_source or '',
        'date_value': date.isoformat() if date else '',
        'is_approximate': is_approximate,
        'warnings': '; '.join(warnings),
    }
    logger.info(
        '%s: %s -> %s (источник даты: %s%s)',
        'ПЛАНИРУЕТСЯ' if args.dry_run else 'ПЕРЕМЕЩЁН',
        file_path,
        final_path,
        date_source or 'нет',
        ', приблизительно' if is_approximate else '',
    )
    return ProcessResult(record=record, category='ok', date=date, messenger=messenger)


def accumulate_result(
    result: ProcessResult,
    records: List[Dict[str, Any]],
    duplicates: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    stats: Dict[str, Any],
    lock: threading.Lock,
) -> None:
    """Добавляет результат обработки файла в общие списки и статистику."""
    with lock:
        records.append(result.record)
        if result.category == 'duplicate':
            stats['duplicates'] += 1
            duplicates.append({
                'hash': result.record.get('hash', ''),
                'source_path': result.record['source_path'],
                'dest_path': result.record['dest_path'],
            })
        elif result.category == 'junk':
            stats['junk'] += 1
            if result.messenger:
                stats['messengers'] += 1
        elif result.category == 'negative':
            stats['negatives'] += 1
            if result.messenger:
                stats['messengers'] += 1
        elif result.category == 'error':
            stats['errors'] += 1
            errors.append({
                'source_path': result.record['source_path'],
                'dest_path': result.record['dest_path'],
                'error': 'ошибка перемещения',
            })
        else:
            stats['moved'] += 1
            if result.date:
                stats['by_year'][result.date.year] += 1
                stats['by_month'][f'{result.date.month:02d}.{result.date.year}'] += 1
            else:
                stats['undefined'] += 1
            if result.messenger:
                stats['messengers'] += 1


def process_files(
    files: List[Path],
    source: Path,
    dest: Path,
    args: argparse.Namespace,
    seen_hashes: Set[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Обрабатывает все файлы (последовательно или в потоках).

    Возвращает (records, duplicates, errors, stats).
    """
    lock = threading.Lock()

    stats: Dict[str, Any] = {
        'total': len(files),
        'moved': 0,
        'duplicates': 0,
        'errors': 0,
        'undefined': 0,
        'messengers': 0,
        'negatives': 0,
        'junk': 0,
        'by_year': Counter(),
        'by_month': Counter(),
    }

    records: List[Dict[str, Any]] = []
    duplicates: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    use_threads = args.workers > 1 and len(files) > THREADING_THRESHOLD
    if use_threads:
        logger.info('Многопоточная обработка: %d потоков', args.workers)

    def process_one(path: Path) -> ProcessResult:
        return process_single_file(path, source, dest, args, seen_hashes, lock)

    if use_threads:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(process_one, f) for f in files]
            for future in as_completed(futures):
                result = future.result()
                accumulate_result(result, records, duplicates, errors, stats, lock)
    else:
        for path in _iter_with_progress(files, desc='Обработка файлов'):
            result = process_one(path)
            accumulate_result(result, records, duplicates, errors, stats, lock)

    return records, duplicates, errors, stats


def print_statistics(stats: Dict[str, Any], elapsed: float) -> None:
    """Выводит итоговую статистику в консоль."""
    print('\n' + '=' * 50)
    print('СТАТИСТИКА')
    print('=' * 50)
    print(f'Всего файлов обработано: {stats["total"]}')
    print(f'Перемещено: {stats["moved"]}')
    print(f'Дубликатов: {stats["duplicates"]}')
    print(f'Из мессенджеров: {stats["messengers"]}')
    print(f'Мусор (мелкие файлы): {stats["junk"]}')
    print(f'Негативы (сканированные RAW): {stats["negatives"]}')
    print(f'Без данных (дата не определена): {stats["undefined"]}')
    print(f'Ошибок: {stats["errors"]}')

    if stats['by_year']:
        print('\nРаспределение по годам:')
        for year, count in sorted(stats['by_year'].items()):
            print(f'  {year}: {count}')

    if stats['by_month']:
        print('\nРаспределение по месяцам:')
        for month, count in sorted(stats['by_month'].items()):
            print(f'  {month}: {count}')

    print(f'\nВремя выполнения: {elapsed:.2f} с')


def _run(args: argparse.Namespace) -> int:
    """Основная логика сортировки (после разбора аргументов)."""
    source = Path(args.source)
    dest = Path(args.destination)

    # 1. Проверка путей
    error = validate_paths(source, dest)
    if error:
        logger.error(error)
        print(f'ОШИБКА: {error}', file=sys.stderr)
        return 1

    if args.workers < 1:
        logger.error('--workers должен быть не меньше 1.')
        return 1

    # 2. Создание папки-назначения
    if not dest.exists():
        dest.mkdir(parents=True)
        logger.info('Создана папка-назначение: %s', dest)

    # 3. Сбор медиафайлов
    extensions = _parse_extensions(args.extensions)
    if not extensions:
        logger.error('Не задано ни одного расширения.')
        return 1

    exclude = dest if _is_relative_to(dest, source) else None
    files = collect_media_files(source, extensions, exclude=exclude)
    logger.info('Найдено медиафайлов: %d', len(files))
    print(f'Найдено медиафайлов: {len(files)}')

    if not files:
        logger.warning('Медиафайлы не найдены.')
        return 0

    # 4. План и подтверждение
    if not args.dry_run and not args.yes:
        print(f'\nИсточник:      {source}')
        print(f'Назначение:    {dest}')
        print(f'Файлов:        {len(files)}')
        print('Режим:         перемещение')
        answer = input('\nПродолжить? [y/N]: ').strip().lower()
        if answer not in ('y', 'yes', 'д', 'да'):
            logger.info('Операция отменена пользователем.')
            print('Операция отменена.')
            return 0

    # 5. Индекс хэшей файлов в папке-назначении (для проверки дубликатов)
    seen_hashes: Set[str] = set()
    if args.check_duplicates:
        dest_files = collect_media_files(dest, extensions)
        logger.info('Индексирование %d файлов в папке-назначении...', len(dest_files))
        for path in _iter_with_progress(dest_files, desc='Индексация destination'):
            try:
                seen_hashes.add(get_file_hash(path))
            except OSError as exc:
                logger.warning('Не удалось вычислить хэш %s: %s', path, exc)

    # 6. Обработка файлов
    start_time = time.perf_counter()
    records, duplicates, errors, stats = process_files(files, source, dest, args, seen_hashes)
    elapsed = time.perf_counter() - start_time

    # 7. Отчёты
    generate_report(records, Path(args.report_file))
    write_duplicates_log(duplicates, Path(args.duplicates_log))
    write_errors_log(errors, Path(args.errors_log))

    # 8. Статистика
    print_statistics(stats, elapsed)

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Главная функция: разбор аргументов, валидация, обработка, отчёты."""
    args = parse_args(argv)

    # Настройка логирования
    setup_logging(Path(args.log_file))

    try:
        return _run(args)
    except KeyboardInterrupt:
        logger.warning('Операция прервана пользователем (Ctrl+C).')
        return 130


if __name__ == '__main__':
    raise SystemExit(main())