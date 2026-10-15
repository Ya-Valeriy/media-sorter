"""
CLI-интерфейс реорганизации структуры медиаархива.

Скрипт автоматически определяет уровень архива по содержимому --root:
- корень архива (годовые папки) -> обработка по годам и месяцам;
- годовая папка (месячные папки) -> обработка по месяцам;
- месячная папка (файлы) -> перенос в структуру года/месяца.

Алгоритм:
1. Проверка корневой папки.
2. Определение уровня архива (detector).
3. Подсчёт папок и файлов, вывод плана.
4. Запрос подтверждения (если не dry-run и не --yes).
5. Обработка: переименование папок, создание *_photo и *_video,
   перемещение файлов по типам.
6. Генерация отчётов: report.csv, errors.log, summary.txt.

Пример:
    python reorganize_media.py --root "D:\\Photos\\YamankinArchive" --dry-run
    python reorganize_media.py --root "D:\\Photos\\YamankinArchive"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .date_parser import (
    get_month_year_from_exif,
    is_year_range,
    parse_month_year,
    parse_year,
)
from .detector import (
    LEVEL_ARCHIVE_ROOT,
    LEVEL_MONTH,
    LEVEL_UNKNOWN,
    LEVEL_YEAR,
    detect_level,
)
from .file_classifier import (
    DEFAULT_IMAGE_EXTENSIONS,
    DEFAULT_VIDEO_EXTENSIONS,
    TYPE_IMAGE,
    TYPE_OTHER,
    TYPE_VIDEO,
    classify_file,
    parse_extensions,
)
from .mover import move_dir_safely, move_file_safely
from .renamer import (
    image_folder_name,
    month_folder_name,
    resolve_collision,
    video_folder_name,
    year_folder_name,
)
from .reporter import (
    generate_report,
    setup_logging,
    write_errors_log,
    write_summary,
)

logger = logging.getLogger(__name__)

# Папка для месячных папок с неопределённой датой
UNKNOWN_FOLDER: str = '_unknown_media'

# Подписи уровней для плана
LEVEL_LABELS: Dict[str, str] = {
    LEVEL_ARCHIVE_ROOT: 'корень архива (годовые папки)',
    LEVEL_YEAR: 'годовая папка (месячные папки)',
    LEVEL_MONTH: 'месячная папка (файлы)',
    LEVEL_UNKNOWN: 'структура не распознана',
}


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Разбирает аргументы командной строки."""
    parser = argparse.ArgumentParser(
        prog='reorganize_media',
        description='Реорганизация структуры медиаархива: переименование папок '
                    'и разделение файлов по типам (фото/видео).',
    )
    parser.add_argument('--root', '-r', required=True, help='Путь к корневой папке архива')
    parser.add_argument('--dry-run', action='store_true', help='Пробный прогон без изменений')
    parser.add_argument('--log-file', default='rename.log', help='Путь к логу (по умолчанию: rename.log)')
    parser.add_argument('--report-file', default='report.csv', help='Путь к CSV-отчёту (по умолчанию: report.csv)')
    parser.add_argument('--errors-file', default='errors.log', help='Путь к логу ошибок (по умолчанию: errors.log)')
    parser.add_argument('--summary-file', default='summary.txt', help='Путь к итоговой статистике (по умолчанию: summary.txt)')
    parser.add_argument(
        '--extensions-image',
        default='',
        help='Дополнительные расширения фото через запятую (например: jpg,cr2)',
    )
    parser.add_argument(
        '--extensions-video',
        default='',
        help='Дополнительные расширения видео через запятую (например: mp4,mov)',
    )
    parser.add_argument('--yes', action='store_true', help='Не запрашивать подтверждение перед изменениями')
    return parser.parse_args(argv)


def validate_root(root: Path) -> Optional[str]:
    """Проверяет, что root существует и является директорией."""
    if not root.exists():
        return f'Корневая папка не существует: {root}'
    if not root.is_dir():
        return f'Путь не является директорией: {root}'
    return None


def _count_files(
    folder: Path,
    plan: Dict[str, int],
    image_exts: frozenset[str],
    video_exts: frozenset[str],
) -> None:
    """Подсчитывает файлы в папке и добавляет в план."""
    for f in folder.iterdir():
        if not f.is_file():
            continue
        ftype = classify_file(f, image_exts, video_exts)
        if ftype == TYPE_IMAGE:
            plan['images'] += 1
        elif ftype == TYPE_VIDEO:
            plan['videos'] += 1
        else:
            plan['others'] += 1


def build_plan(
    root: Path,
    level: str,
    image_exts: frozenset[str],
    video_exts: frozenset[str],
) -> Dict[str, int]:
    """
    Подсчитывает количество папок и файлов для плана с учётом уровня.

    Учитываются только папки, подходящие под шаблон годов/месяцев.
    """
    plan: Dict[str, int] = {'years': 0, 'months': 0, 'images': 0, 'videos': 0, 'others': 0}

    if level == LEVEL_ARCHIVE_ROOT:
        for year_dir in root.iterdir():
            if not year_dir.is_dir():
                continue
            if is_year_range(year_dir.name) or parse_year(year_dir.name) is None:
                continue
            if parse_month_year(year_dir.name) is not None:
                continue
            plan['years'] += 1
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue
                plan['months'] += 1
                _count_files(month_dir, plan, image_exts, video_exts)
    elif level == LEVEL_YEAR:
        plan['years'] = 1
        for month_dir in root.iterdir():
            if not month_dir.is_dir():
                continue
            plan['months'] += 1
            _count_files(month_dir, plan, image_exts, video_exts)
    elif level == LEVEL_MONTH:
        plan['months'] = 1
        _count_files(root, plan, image_exts, video_exts)

    return plan


def _record(
    old_path: Path,
    new_path: Path,
    ftype: str,
    action: str,
    files_count: int,
    warnings: str,
) -> Dict[str, Any]:
    """Формирует запись для CSV-отчёта."""
    return {
        'old_path': str(old_path),
        'new_path': str(new_path),
        'type': ftype,
        'action': action,
        'files_count': files_count,
        'warnings': warnings,
    }


def _children_count(path: Path) -> int:
    """Возвращает количество элементов внутри папки (0 при ошибке)."""
    try:
        return sum(1 for _ in path.iterdir())
    except OSError:
        return 0


def _new_stats() -> Dict[str, Any]:
    """Возвращает пустую статистику обработки."""
    return {
        'years': 0,
        'months': 0,
        'images': 0,
        'videos': 0,
        'others': 0,
        'unknown': 0,
        'errors': 0,
    }


def _move_files_by_type(
    month_dir: Path,
    month: int,
    year: int,
    args: argparse.Namespace,
    image_exts: frozenset[str],
    video_exts: frozenset[str],
    records: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    stats: Dict[str, Any],
) -> None:
    """
    Создаёт подпапки *_photo и *_video и перемещает файлы по типам.

    Прочие файлы остаются на месте и фиксируются в отчёте.
    """
    img_dir = month_dir / image_folder_name(month, year)
    vid_dir = month_dir / video_folder_name(month, year)
    if not args.dry_run:
        img_dir.mkdir(parents=True, exist_ok=True)
        vid_dir.mkdir(parents=True, exist_ok=True)

    for f in sorted(month_dir.iterdir()):
        if not f.is_file():
            continue
        ftype = classify_file(f, image_exts, video_exts)
        if ftype == TYPE_IMAGE:
            final, status = move_file_safely(f, img_dir, args.dry_run)
            if status == 'error':
                errors.append({'path': str(f), 'error': 'не удалось переместить фото'})
                stats['errors'] += 1
                continue
            logger.info('Фото: %s -> %s', f, final)
            records.append(_record(f, final, 'image', 'move', 1, ''))
            stats['images'] += 1
        elif ftype == TYPE_VIDEO:
            final, status = move_file_safely(f, vid_dir, args.dry_run)
            if status == 'error':
                errors.append({'path': str(f), 'error': 'не удалось переместить видео'})
                stats['errors'] += 1
                continue
            logger.info('Видео: %s -> %s', f, final)
            records.append(_record(f, final, 'video', 'move', 1, ''))
            stats['videos'] += 1
        else:
            logger.info('Прочий файл оставлен: %s', f)
            records.append(_record(f, f, 'other', 'skip', 1, 'прочий файл, оставлен на месте'))
            stats['others'] += 1


def _process_month_dir(
    month_dir: Path,
    year_dir: Path,
    archive_root: Path,
    args: argparse.Namespace,
    image_exts: frozenset[str],
    video_exts: frozenset[str],
    records: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    stats: Dict[str, Any],
) -> None:
    """
    Обрабатывает одну месячную папку: определяет месяц/год, переименовывает,
    создаёт подпапки *_photo/*_video и перемещает файлы.

    Если дату определить нельзя — папка перемещается в _unknown_media
    (в корне архива).
    """
    mname = month_dir.name

    # Определение месяца и года: имя папки -> EXIF-фолбэк
    mmyy = parse_month_year(mname)
    if mmyy is None:
        mmyy = get_month_year_from_exif(month_dir, image_exts)

    if mmyy is None:
        unknown_dir = archive_root / UNKNOWN_FOLDER
        target = resolve_collision(unknown_dir / mname)
        final, status = move_dir_safely(month_dir, target, args.dry_run)
        if status == 'error':
            errors.append({'path': str(month_dir), 'error': 'не удалось переместить в _unknown_media'})
            stats['errors'] += 1
            return
        logger.warning('Дата не определена: %s -> %s', month_dir, final)
        records.append(_record(month_dir, final, 'month', 'move', _children_count(month_dir), 'дата не определена'))
        stats['unknown'] += 1
        return

    month, myear = mmyy

    # Переименование месячной папки
    new_month_name = month_folder_name(month, myear)
    if mname == new_month_name:
        logger.info('Месячная папка уже в нужном формате: %s', month_dir)
        records.append(_record(month_dir, month_dir, 'month', 'skip', _children_count(month_dir), ''))
    else:
        target = resolve_collision(year_dir / new_month_name)
        final, status = move_dir_safely(month_dir, target, args.dry_run)
        if status == 'error':
            errors.append({'path': str(month_dir), 'error': 'не удалось переименовать месячную папку'})
            stats['errors'] += 1
            return
        logger.info('Месячная папка: %s -> %s', month_dir, final)
        records.append(_record(month_dir, final, 'month', 'rename', _children_count(month_dir), ''))
        if status == 'moved':
            month_dir = final
    stats['months'] += 1

    _move_files_by_type(month_dir, month, myear, args, image_exts, video_exts, records, errors, stats)


def process_archive(
    root: Path,
    args: argparse.Namespace,
    image_exts: frozenset[str],
    video_exts: frozenset[str],
    records: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    stats: Dict[str, Any],
) -> None:
    """
    Обрабатывает корень архива: годовые папки -> месячные -> файлы.

    Папки-диапазоны годов, не-годовые папки и папки, похожие на месячные,
    пропускаются с предупреждением.
    """
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir():
            continue
        name = year_dir.name

        if is_year_range(name):
            logger.warning('Пропуск: диапазон годов в имени: %s', year_dir)
            records.append(_record(year_dir, year_dir, 'year', 'skip', 0, 'диапазон годов, пропущен'))
            continue

        if parse_month_year(name) is not None:
            logger.warning('Пропуск: похожа на месячную папку: %s', year_dir)
            records.append(_record(year_dir, year_dir, 'year', 'skip', 0, 'похожа на месячную папку, пропущена'))
            continue

        year = parse_year(name)
        if year is None:
            logger.warning('Пропуск: имя не похоже на годовую папку: %s', year_dir)
            records.append(_record(year_dir, year_dir, 'year', 'skip', 0, 'не похожа на годовую папку'))
            continue

        # Переименование годовой папки
        new_year_name = year_folder_name(year)
        if name == new_year_name:
            logger.info('Годовая папка уже в нужном формате: %s', year_dir)
            records.append(_record(year_dir, year_dir, 'year', 'skip', _children_count(year_dir), ''))
        else:
            target = resolve_collision(root / new_year_name)
            final, status = move_dir_safely(year_dir, target, args.dry_run)
            if status == 'error':
                errors.append({'path': str(year_dir), 'error': 'не удалось переименовать годовую папку'})
                stats['errors'] += 1
                continue
            logger.info('Годовая папка: %s -> %s', year_dir, final)
            records.append(_record(year_dir, final, 'year', 'rename', _children_count(year_dir), ''))
            if status == 'moved':
                year_dir = final
        stats['years'] += 1

        # Обработка месячных папок
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                logger.warning('Файл прямо в годовой папке (оставлен): %s', month_dir)
                records.append(_record(month_dir, month_dir, 'other', 'skip', 1, 'файл в годовой папке, оставлен'))
                continue
            _process_month_dir(month_dir, year_dir, root, args, image_exts, video_exts, records, errors, stats)


def process_year_folder(
    root: Path,
    args: argparse.Namespace,
    image_exts: frozenset[str],
    video_exts: frozenset[str],
    records: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    stats: Dict[str, Any],
) -> None:
    """
    Обрабатывает точку входа «годовая папка»: определяет год, переименовывает
    папку в <год>_<семья>_media и обрабатывает месячные папки внутри.
    """
    # Определение года: из имени папки, иначе из первой месячной папки
    year = parse_year(root.name)
    if year is None:
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            mmyy = parse_month_year(d.name)
            if mmyy:
                year = mmyy[1]
                break

    if year is None:
        logger.error('Не удалось определить год для папки: %s', root)
        errors.append({'path': str(root), 'error': 'не удалось определить год'})
        stats['errors'] += 1
        return

    # Переименование годовой папки
    new_year_name = year_folder_name(year)
    if root.name == new_year_name:
        logger.info('Годовая папка уже в нужном формате: %s', root)
        records.append(_record(root, root, 'year', 'skip', _children_count(root), ''))
        year_dir = root
    else:
        target = resolve_collision(root.parent / new_year_name)
        final, status = move_dir_safely(root, target, args.dry_run)
        if status == 'error':
            errors.append({'path': str(root), 'error': 'не удалось переименовать годовую папку'})
            stats['errors'] += 1
            return
        logger.info('Годовая папка: %s -> %s', root, final)
        records.append(_record(root, final, 'year', 'rename', _children_count(root), ''))
        year_dir = final if status == 'moved' else root
    stats['years'] += 1

    archive_root = root.parent
    for month_dir in sorted(year_dir.iterdir()):
        if not month_dir.is_dir():
            logger.warning('Файл прямо в годовой папке (оставлен): %s', month_dir)
            records.append(_record(month_dir, month_dir, 'other', 'skip', 1, 'файл в годовой папке, оставлен'))
            continue
        _process_month_dir(month_dir, year_dir, archive_root, args, image_exts, video_exts, records, errors, stats)


def process_month_folder(
    root: Path,
    args: argparse.Namespace,
    image_exts: frozenset[str],
    video_exts: frozenset[str],
    records: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    stats: Dict[str, Any],
) -> None:
    """
    Обрабатывает точку входа «месячная папка»: определяет месяц/год,
    переносит папку в структуру <год>_<семья>_media/<мм>-<гггг>_<семья>_media
    и разделяет файлы по типам.
    """
    # Определение месяца и года: имя папки -> EXIF-фолбэк
    mmyy = parse_month_year(root.name)
    if mmyy is None:
        mmyy = get_month_year_from_exif(root, image_exts)

    if mmyy is None:
        unknown_dir = root.parent / UNKNOWN_FOLDER
        target = resolve_collision(unknown_dir / root.name)
        final, status = move_dir_safely(root, target, args.dry_run)
        if status == 'error':
            errors.append({'path': str(root), 'error': 'не удалось переместить в _unknown_media'})
            stats['errors'] += 1
            return
        logger.warning('Дата не определена: %s -> %s', root, final)
        records.append(_record(root, final, 'month', 'move', _children_count(root), 'дата не определена'))
        stats['unknown'] += 1
        return

    month, year = mmyy

    # Целевая годовая папка (создаётся при необходимости)
    year_dir = root.parent / year_folder_name(year)
    if not args.dry_run:
        year_dir.mkdir(parents=True, exist_ok=True)

    # Перенос месячной папки в структуру
    month_target = year_dir / month_folder_name(month, year)
    target = resolve_collision(month_target)
    final, status = move_dir_safely(root, target, args.dry_run)
    if status == 'error':
        errors.append({'path': str(root), 'error': 'не удалось переместить месячную папку'})
        stats['errors'] += 1
        return
    logger.info('Месячная папка: %s -> %s', root, final)
    records.append(_record(root, final, 'month', 'move', _children_count(root), ''))
    stats['months'] += 1

    month_dir = final if status == 'moved' else root
    _move_files_by_type(month_dir, month, year, args, image_exts, video_exts, records, errors, stats)


def main(argv: Optional[List[str]] = None) -> int:
    """Главная функция: разбор аргументов, план, обработка, отчёты."""
    args = parse_args(argv)
    setup_logging(Path(args.log_file))

    root = Path(args.root)
    error = validate_root(root)
    if error:
        logger.error(error)
        print(f'ОШИБКА: {error}', file=sys.stderr)
        return 1

    # Дополняем стандартные списки расширений пользовательскими
    image_exts = DEFAULT_IMAGE_EXTENSIONS | parse_extensions(args.extensions_image)
    video_exts = DEFAULT_VIDEO_EXTENSIONS | parse_extensions(args.extensions_video)

    # Определение уровня архива
    level = detect_level(root)
    if level == LEVEL_UNKNOWN:
        logger.warning('Структура папки не распознана: %s', root)
        print(f'ОШИБКА: не удалось определить структуру папки: {root}', file=sys.stderr)
        return 1

    # --- План ---
    plan = build_plan(root, level, image_exts, video_exts)
    print('\n' + '=' * 50)
    print('ПЛАН РЕОРГАНИЗАЦИИ')
    print('=' * 50)
    print(f'Корневая папка: {root}')
    print(f'Уровень: {LEVEL_LABELS[level]}')
    print(f'Годовых папок: {plan["years"]}')
    print(f'Месячных папок: {plan["months"]}')
    print(f'Фото: {plan["images"]}')
    print(f'Видео: {plan["videos"]}')
    print(f'Прочих файлов: {plan["others"]}')
    print(f'Режим: {"пробный прогон (dry-run)" if args.dry_run else "реальные изменения"}')

    # --- Подтверждение ---
    if not args.dry_run and not args.yes:
        answer = input('\nПродолжить? [y/N]: ').strip().lower()
        if answer not in ('y', 'yes', 'д', 'да'):
            logger.info('Операция отменена пользователем.')
            print('Операция отменена.')
            return 0

    # --- Обработка ---
    records: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    stats = _new_stats()

    if level == LEVEL_ARCHIVE_ROOT:
        process_archive(root, args, image_exts, video_exts, records, errors, stats)
    elif level == LEVEL_YEAR:
        process_year_folder(root, args, image_exts, video_exts, records, errors, stats)
    elif level == LEVEL_MONTH:
        process_month_folder(root, args, image_exts, video_exts, records, errors, stats)

    # --- Отчёты ---
    generate_report(records, Path(args.report_file))
    write_errors_log(errors, Path(args.errors_file))
    write_summary(stats, Path(args.summary_file))

    # --- Итог ---
    print('\n' + '=' * 50)
    print('ИТОГ')
    print('=' * 50)
    print(f'Годовых папок обработано: {stats["years"]}')
    print(f'Месячных папок обработано: {stats["months"]}')
    print(f'Фото перемещено: {stats["images"]}')
    print(f'Видео перемещено: {stats["videos"]}')
    print(f'Прочих файлов оставлено: {stats["others"]}')
    print(f'Папок с неопределённой датой: {stats["unknown"]}')
    print(f'Ошибок: {stats["errors"]}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())