"""
Тесты для модуля определения даты (media_sorter.date_extractor).
"""

from datetime import datetime
from pathlib import Path

import pytest

from media_sorter.date_extractor import extract_date_from_filename, get_creation_date


@pytest.mark.parametrize(
    'filename, expected',
    [
        # Камеры: IMG_YYYYMMDD_HHMMSS
        ('IMG_20240513_142035.jpg', datetime(2024, 5, 13, 14, 20, 35)),
        ('VID_20240513_142035.mp4', datetime(2024, 5, 13, 14, 20, 35)),
        # Чистая дата-время без префикса
        ('20240513_142035.mp4', datetime(2024, 5, 13, 14, 20, 35)),
        # ISO-подобные шаблоны
        ('2024-05-13 14.20.35.jpg', datetime(2024, 5, 13, 14, 20, 35)),
        ('2024-05-13_14-20-35.jpg', datetime(2024, 5, 13, 14, 20, 35)),
        # Скриншоты
        ('Screenshot_20240513-142035.png', datetime(2024, 5, 13, 14, 20, 35)),
        ('Screen Shot 2024-05-13 at 14.20.35.png', datetime(2024, 5, 13, 14, 20, 35)),
        # WhatsApp: IMG-YYYYMMDD-WA####
        ('IMG-20240513-WA0001.jpg', datetime(2024, 5, 13)),
        # Telegram: photo_YYYY-MM-DD_HH-MM-SS
        ('photo_2024-05-13_14-20-35.jpg', datetime(2024, 5, 13, 14, 20, 35)),
        ('video_2024-05-13_14-20-35.mp4', datetime(2024, 5, 13, 14, 20, 35)),
        # Только дата
        ('20240513.jpg', datetime(2024, 5, 13)),
        ('2024_05_13.jpg', datetime(2024, 5, 13)),
        ('2024-05-13.jpg', datetime(2024, 5, 13)),
    ],
)
def test_extract_date_from_filename(filename: str, expected: datetime) -> None:
    """Дата корректно извлекается из разных шаблонов имён."""
    assert extract_date_from_filename(Path(filename)) == expected


@pytest.mark.parametrize(
    'filename',
    [
        'no_date_here.jpg',
        'random_file.txt',
        '1234567890.jpg',  # невалидная дата (месяц 56)
        'IMG_20241340_999999.jpg',  # месяц 13, час 99
        '2024-13-40.jpg',  # месяц 13, день 40
    ],
)
def test_extract_date_from_filename_invalid(filename: str) -> None:
    """Некорректные или отсутствующие даты возвращают None."""
    assert extract_date_from_filename(Path(filename)) is None


def test_get_creation_date_from_filename(tmp_path: Path) -> None:
    """Для файла с датой в имени источник — 'filename', дата не приблизительная."""
    file_path = tmp_path / 'IMG_20240513_142035.jpg'
    file_path.write_bytes(b'not a real jpeg')
    date, source, is_approximate = get_creation_date(file_path)
    assert source == 'filename'
    assert is_approximate is False
    assert date == datetime(2024, 5, 13, 14, 20, 35)


def test_get_creation_date_from_mtime(tmp_path: Path) -> None:
    """Если дата не извлекается — используется mtime (приблизительно)."""
    file_path = tmp_path / 'no_date.jpg'
    file_path.write_bytes(b'data')
    date, source, is_approximate = get_creation_date(file_path)
    assert source == 'mtime'
    assert is_approximate is True
    assert date is not None