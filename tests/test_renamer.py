"""
Unit-тесты для модуля renamer: имена папок и разрешение коллизий.
"""

from pathlib import Path

from renamer.renamer import (
    image_folder_name,
    month_folder_name,
    resolve_collision,
    video_folder_name,
    year_folder_name,
)


def test_year_folder_name():
    assert year_folder_name(2024) == '2024_media'
    assert year_folder_name(2006) == '2006_media'


def test_month_folder_name():
    assert month_folder_name(5, 2024) == '05.2024_media'
    assert month_folder_name(12, 2016) == '12.2016_media'


def test_image_folder_name():
    assert image_folder_name(5, 2024) == '05.2024_photo'


def test_video_folder_name():
    assert video_folder_name(5, 2024) == '05.2024_video'


def test_resolve_collision_file(tmp_path):
    target = tmp_path / 'file.jpg'
    target.write_bytes(b'x')
    resolved = resolve_collision(target)
    assert resolved.name == 'file_1.jpg'
    # Создаём и первый суффиксный файл — теперь коллизия должна дать _2
    resolved.write_bytes(b'x')
    resolved2 = resolve_collision(target)
    assert resolved2.name == 'file_2.jpg'


def test_resolve_collision_no_collision(tmp_path):
    target = tmp_path / 'file.jpg'
    assert resolve_collision(target) == target


def test_resolve_collision_dir(tmp_path):
    d = tmp_path / '2024_media'
    d.mkdir()
    resolved = resolve_collision(d)
    assert resolved.name == '2024_media_1'