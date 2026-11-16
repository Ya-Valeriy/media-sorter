"""
Unit-тесты для модуля detector: определение уровня архива по содержимому папки.
"""

from renamer.detector import (
    LEVEL_ARCHIVE_ROOT,
    LEVEL_MONTH,
    LEVEL_UNKNOWN,
    LEVEL_YEAR,
    detect_level,
)


def test_detect_archive_root(tmp_path):
    """Корень архива: внутри годовые папки."""
    (tmp_path / '2024').mkdir()
    (tmp_path / '2025').mkdir()
    assert detect_level(tmp_path) == LEVEL_ARCHIVE_ROOT


def test_detect_archive_root_with_other_dirs(tmp_path):
    """Корень архива с посторонними папками (природа, фото)."""
    (tmp_path / '2024').mkdir()
    (tmp_path / 'природа').mkdir()
    (tmp_path / 'рома раз в месяц').mkdir()
    assert detect_level(tmp_path) == LEVEL_ARCHIVE_ROOT


def test_detect_archive_root_renamed(tmp_path):
    """Корень архива с уже переименованными годовыми папками."""
    (tmp_path / '2024_media').mkdir()
    (tmp_path / '2006_media').mkdir()
    assert detect_level(tmp_path) == LEVEL_ARCHIVE_ROOT


def test_detect_year(tmp_path):
    """Годовая папка: внутри месячные папки."""
    (tmp_path / '05.2024').mkdir()
    (tmp_path / '2024-11').mkdir()
    assert detect_level(tmp_path) == LEVEL_YEAR


def test_detect_year_renamed(tmp_path):
    """Годовая папка с уже переименованными месячными папками."""
    (tmp_path / '05.2024_media').mkdir()
    (tmp_path / '12.2024_media').mkdir()
    assert detect_level(tmp_path) == LEVEL_YEAR


def test_detect_year_with_files(tmp_path):
    """Годовая папка: месячные папки + файлы."""
    (tmp_path / '05.2024').mkdir()
    (tmp_path / 'readme.txt').touch()
    assert detect_level(tmp_path) == LEVEL_YEAR


def test_detect_month(tmp_path):
    """Месячная папка: только файлы."""
    (tmp_path / 'IMG_001.jpg').touch()
    (tmp_path / 'VID_001.mp4').touch()
    assert detect_level(tmp_path) == LEVEL_MONTH


def test_detect_unknown(tmp_path):
    """Не распознанная структура: подпапка без дат."""
    (tmp_path / 'фото').mkdir()
    assert detect_level(tmp_path) == LEVEL_UNKNOWN


def test_detect_empty(tmp_path):
    """Пустая папка."""
    assert detect_level(tmp_path) == LEVEL_UNKNOWN