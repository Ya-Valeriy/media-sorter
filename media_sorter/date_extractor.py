"""
Модуль определения даты создания медиафайлов.

Приоритет источников даты:
1. EXIF-данные фото (DateTimeOriginal -> CreateDate -> ModifyDate).
2. Метаданные видео (ffprobe: creation_time контейнера -> потока -> date).
3. Имя файла (известные шаблоны камер, скриншотов, мессенджеров).
4. Дата изменения файла (mtime) — помечается как приблизительная.
5. Восстановление по геолокации (GPS) — выполняется в основном цикле main.py.
"""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# --- Регистрация поддержки HEIC/HEIF (pillow-heif) ---

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    logger.debug('pillow-heif не установлен: HEIC/HEIF будут обработаны без EXIF')

# --- Расширения файлов ---

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    '.jpg', '.jpeg', '.png', '.heic', '.heif', '.tiff', '.tif',
    '.raw', '.cr2', '.cr3', '.nef', '.arw', '.dng',
    '.mp4', '.mov', '.avi', '.mkv', '.mts', '.3gp',
})

IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    '.jpg', '.jpeg', '.png', '.heic', '.heif', '.tiff', '.tif',
    '.raw', '.cr2', '.cr3', '.nef', '.arw', '.dng',
})

VIDEO_EXTENSIONS: frozenset[str] = frozenset({
    '.mp4', '.mov', '.avi', '.mkv', '.mts', '.3gp',
})

RAW_EXTENSIONS: frozenset[str] = frozenset({
    '.raw', '.cr2', '.cr3', '.nef', '.arw', '.dng',
})

# --- Шаблоны дат в именах файлов ---
# Порядок важен: сначала более специфичные шаблоны.

FILENAME_DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # IMG_20240513_142035.jpg, VID_20240513_142035.mp4,
    # Screenshot_20240513-142035.png, 20240513_142035.mp4
    re.compile(
        r'(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})'
        r'[_-]'
        r'(?P<hour>\d{2})(?P<minute>\d{2})(?P<second>\d{2})'
    ),
    # 2024-05-13 14.20.35.jpg, 2024-05-13_14-20-35.jpg,
    # Screen Shot 2024-05-13 at 14.20.35.png,
    # photo_2024-05-13_14-20-35.jpg (Telegram)
    re.compile(
        r'(?P<year>\d{4})[-_](?P<month>\d{2})[-_](?P<day>\d{2})'
        r'\D+'
        r'(?P<hour>\d{2})[._:-](?P<minute>\d{2})[._:-](?P<second>\d{2})'
    ),
    # IMG-20240513-WA0001.jpg (WhatsApp), PXL_20240513_...
    re.compile(
        r'(?:IMG|VID|PXL)[-_]?(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})'
    ),
    # 2024-05-13 (только дата)
    re.compile(
        r'(?P<year>\d{4})[-_](?P<month>\d{2})[-_](?P<day>\d{2})'
    ),
    # 20240513 (только дата)
    re.compile(
        r'(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})'
    ),
)


def _validate_date(
    year: Optional[str],
    month: Optional[str],
    day: Optional[str],
    hour: Optional[str] = None,
    minute: Optional[str] = None,
    second: Optional[str] = None,
) -> Optional[datetime]:
    """Проверяет корректность компонентов даты и возвращает datetime или None."""
    if not (year and month and day):
        return None
    try:
        return datetime(
            int(year), int(month), int(day),
            int(hour or 0), int(minute or 0), int(second or 0),
        )
    except ValueError:
        return None


def extract_date_from_filename(path: Path) -> Optional[datetime]:
    """
    Извлекает дату из имени файла по известным шаблонам.

    Поддерживаемые шаблоны:
    - IMG_20240513_142035.jpg, VID_20240513_142035.mp4
    - 2024-05-13 14.20.35.jpg, 2024-05-13_14-20-35.jpg
    - Screenshot_20240513-142035.png, Screen Shot 2024-05-13 at 14.20.35.png
    - IMG-20240513-WA0001.jpg (WhatsApp), photo_2024-05-13_14-20-35.jpg (Telegram)
    - 20240513.jpg, 2024_05_13.jpg (только дата)
    """
    name = path.name
    for pattern in FILENAME_DATE_PATTERNS:
        match = pattern.search(name)
        if not match:
            continue
        groups = match.groupdict()
        dt = _validate_date(
            groups.get('year'), groups.get('month'), groups.get('day'),
            groups.get('hour'), groups.get('minute'), groups.get('second'),
        )
        if dt:
            return dt
    return None


# --- Чтение EXIF (с кэшированием, чтобы не читать файл дважды) ---


@lru_cache(maxsize=4096)
def _read_pillow_exif(path_str: str) -> Optional[Dict[str, Any]]:
    """Читает EXIF-теги изображения через Pillow. Результат кэшируется."""
    path = Path(path_str)
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
            gps_ifd = exif.get_ifd(0x8825) if hasattr(exif, 'get_ifd') else {}
            gps = {
                ExifTags.GPSTAGS.get(tag_id, tag_id): value
                for tag_id, value in gps_ifd.items()
            }
            return {'tags': tags, 'gps': gps}
    except Exception as exc:
        logger.debug('Не удалось прочитать EXIF из %s: %s', path, exc)
        return None


@lru_cache(maxsize=4096)
def _read_raw_exif(path_str: str) -> Optional[Dict[str, Any]]:
    """Читает EXIF-теги RAW-файла через exifread. Результат кэшируется."""
    path = Path(path_str)
    try:
        import exifread
    except ImportError:
        logger.debug('exifread не установлен: RAW EXIF недоступен')
        return None

    try:
        with open(path, 'rb') as fh:
            tags = exifread.process_file(fh, details=False)
        return {'tags': tags}
    except Exception as exc:
        logger.debug('Не удалось прочитать RAW EXIF из %s: %s', path, exc)
        return None


def _parse_exif_datetime(value: str) -> Optional[datetime]:
    """Разбирает строку даты EXIF вида '2024:05:13 14:20:35'."""
    value = value.strip().strip('\x00')
    for fmt in ('%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y:%m:%d %H:%M:%S.%f'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _apply_offset(dt: datetime, offset_str: Optional[str]) -> datetime:
    """
    Применяет OffsetTimeOriginal: переводит локальное время съёмки
    в локальное время системы.
    """
    if not offset_str:
        return dt
    match = re.match(r'([+-])(\d{2}):?(\d{2})', offset_str.strip())
    if not match:
        return dt
    sign = 1 if match.group(1) == '+' else -1
    delta = timedelta(hours=int(match.group(2)), minutes=int(match.group(3))) * sign
    try:
        aware = dt.replace(tzinfo=timezone(delta))
        return aware.astimezone().replace(tzinfo=None)
    except (ValueError, OverflowError):
        return dt


def extract_date_from_exif(path: Path) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Извлекает дату съёмки из EXIF-данных.

    Приоритет полей: DateTimeOriginal -> CreateDate -> ModifyDate.
    Для HEIC/HEIF используется pillow-heif, для RAW — exifread.

    Возвращает кортеж (дата, offset_time), где offset_time — значение
    OffsetTimeOriginal (часовой пояс съёмки), если оно есть.
    """
    ext = path.suffix.lower()

    if ext in RAW_EXTENSIONS:
        data = _read_raw_exif(str(path))
        if not data:
            return None, None
        tags = data['tags']
        offset = tags.get('EXIF OffsetTimeOriginal')
        for tag_name in (
            'EXIF DateTimeOriginal',
            'EXIF CreateDate',
            'EXIF DateTimeDigitized',
            'Image DateTime',
        ):
            tag = tags.get(tag_name)
            if tag:
                dt = _parse_exif_datetime(str(tag))
                if dt:
                    return dt, str(offset) if offset else None
        return None, None

    if ext in IMAGE_EXTENSIONS:
        data = _read_pillow_exif(str(path))
        if not data:
            return None, None
        tags = data['tags']
        offset = tags.get('OffsetTimeOriginal')
        for tag_name in ('DateTimeOriginal', 'CreateDate', 'DateTimeDigitized', 'DateTime'):
            value = tags.get(tag_name)
            if value:
                dt = _parse_exif_datetime(str(value))
                if dt:
                    return dt, str(offset) if offset else None
        return None, None

    return None, None


# --- GPS-координаты ---


def _gps_to_decimal(value: Any, ref: Any) -> Optional[float]:
    """Преобразует GPS-координату (градусы, минуты, секунды) в десятичные градусы."""
    if not value or not ref:
        return None
    try:
        d, m, s = (float(x) for x in value)
        decimal = d + m / 60.0 + s / 3600.0
        if str(ref).strip().upper() in ('S', 'W'):
            decimal = -decimal
        return decimal
    except (TypeError, ValueError):
        return None


def _gps_ratio_to_decimal(value: Any, ref: Any) -> Optional[float]:
    """Преобразует GPS-координату из exifread (Ratio-объекты) в десятичные градусы."""
    if not value or not ref:
        return None
    try:
        parts = [float(v.num) / float(v.den) for v in value.values]
        decimal = parts[0] + parts[1] / 60.0 + parts[2] / 3600.0
        if str(ref).strip().upper() in ('S', 'W'):
            decimal = -decimal
        return decimal
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        return None


def extract_gps_coordinates(path: Path) -> Optional[Tuple[float, float]]:
    """
    Извлекает GPS-координаты из EXIF.

    Возвращает (широта, долгота) в десятичных градусах или None.
    """
    ext = path.suffix.lower()

    if ext in RAW_EXTENSIONS:
        data = _read_raw_exif(str(path))
        if not data:
            return None
        tags = data['tags']
        lat = _gps_ratio_to_decimal(tags.get('GPS GPSLatitude'), tags.get('GPS GPSLatitudeRef'))
        lon = _gps_ratio_to_decimal(tags.get('GPS GPSLongitude'), tags.get('GPS GPSLongitudeRef'))
        if lat is not None and lon is not None:
            return lat, lon
        return None

    if ext in IMAGE_EXTENSIONS:
        data = _read_pillow_exif(str(path))
        if not data:
            return None
        gps = data.get('gps', {})
        lat = _gps_to_decimal(gps.get('GPSLatitude'), gps.get('GPSLatitudeRef'))
        lon = _gps_to_decimal(gps.get('GPSLongitude'), gps.get('GPSLongitudeRef'))
        if lat is not None and lon is not None:
            return lat, lon

    return None


# --- Метаданные видео (ffprobe) ---


def _probe_video(path: Path) -> Optional[Dict[str, Any]]:
    """
    Получает метаданные видео через ffprobe.

    Сначала пробует ffmpeg-python, при его отсутствии — subprocess с ffprobe.
    """
    try:
        import ffmpeg

        try:
            return ffmpeg.probe(str(path))
        except Exception as exc:
            logger.debug('ffmpeg.probe не сработал для %s: %s', path, exc)
    except ImportError:
        logger.debug('ffmpeg-python не установлен, использую ffprobe через subprocess')

    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json',
             '-show_format', '-show_streams', str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            import json
            return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        logger.debug('ffprobe не доступен для %s: %s', path, exc)
    return None


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    """Разбирает ISO-строку даты из метаданных видео."""
    value = value.strip().strip('\x00')
    if value.endswith(('Z', 'z')):
        value = value[:-1] + '+00:00'
    formats = (
        '%Y-%m-%dT%H:%M:%S.%f%z',
        '%Y-%m-%dT%H:%M:%S%z',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M:%S%z',
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _to_local_time(dt: datetime) -> datetime:
    """Конвертирует aware-datetime в локальное время системы."""
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def extract_date_from_video(path: Path) -> Optional[datetime]:
    """
    Извлекает дату из метаданных видео через ffprobe.

    Приоритет полей:
    format.tags.creation_time -> com.apple.quicktime.creationdate (iPhone) ->
    stream.tags.creation_time -> format.tags.date.

    creation_time в UTC конвертируется в локальное время системы.
    """
    probe = _probe_video(path)
    if not probe:
        return None

    candidates: list[Optional[str]] = []

    try:
        fmt_tags = probe.get('format', {}).get('tags', {}) or {}
        candidates.append(fmt_tags.get('creation_time'))
        candidates.append(fmt_tags.get('com.apple.quicktime.creationdate'))
    except (AttributeError, TypeError):
        pass

    try:
        for stream in probe.get('streams', []) or []:
            stream_tags = stream.get('tags', {}) or {}
            candidates.append(stream_tags.get('creation_time'))
            candidates.append(stream_tags.get('com.apple.quicktime.creationdate'))
    except (AttributeError, TypeError):
        pass

    try:
        fmt_tags = probe.get('format', {}).get('tags', {}) or {}
        candidates.append(fmt_tags.get('date'))
    except (AttributeError, TypeError):
        pass

    for value in candidates:
        if not value:
            continue
        dt = _parse_iso_datetime(str(value))
        if dt:
            return _to_local_time(dt)
    return None


# --- Главная функция определения даты ---


def get_creation_date(path: Path) -> Tuple[Optional[datetime], str, bool]:
    """
    Определяет дату создания медиафайла.

    Приоритет для фото: EXIF -> имя файла -> mtime.
    Приоритет для видео: имя файла -> метаданные контейнера -> метаданные потока -> mtime.

    Возвращает кортеж (дата, источник, is_approximate):
    - источник: 'exif' | 'video_metadata' | 'filename' | 'mtime' | None
    - is_approximate: True для mtime (дата приблизительная)
    """
    ext = path.suffix.lower()
    is_video = ext in VIDEO_EXTENSIONS

    if is_video:
        dt = extract_date_from_filename(path)
        if dt:
            return dt, 'filename', False
        dt = extract_date_from_video(path)
        if dt:
            return dt, 'video_metadata', False
    else:
        dt, offset = extract_date_from_exif(path)
        if dt:
            return _apply_offset(dt, offset), 'exif', False
        dt = extract_date_from_filename(path)
        if dt:
            return dt, 'filename', False

    # Крайний случай — дата изменения файла
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return mtime, 'mtime', True
    except OSError as exc:
        logger.warning('Не удалось получить mtime для %s: %s', path, exc)
        return None, None, False