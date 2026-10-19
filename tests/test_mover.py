"""
Unit-тесты для media_sorter/mover.py:
- build_destination_path (все ветки: обычная, дубликаты, мусор, без данных)
- build_renamed_filename
- is_junk_file (фото по размеру, видео по длительности и размеру)
- detect_messenger
- resolve_collision
"""

from datetime import datetime
from pathlib import Path

import pytest

from media_sorter.mover import (
    FOLDER_DUPLICATES,
    FOLDER_JUNK,
    FOLDER_NO_DATA,
    build_destination_path,
    build_renamed_filename,
    detect_messenger,
    is_junk_file,
    resolve_collision,
)


# ======================== build_renamed_filename ========================


class TestBuildRenamedFilename:
    def test_renames_with_date(self):
        dt = datetime(2024, 5, 13, 14, 20, 35)
        result = build_renamed_filename("IMG_20240513_142035.jpg", dt)
        assert result == "2024-05-13_14-20-35.jpg"

    def test_preserves_extension_case(self):
        dt = datetime(2020, 3, 25, 11, 40, 14)
        assert build_renamed_filename("photo.JPG", dt) == "2020-03-25_11-40-14.JPG"

    def test_no_date_returns_original(self):
        assert build_renamed_filename("random_file.xyz", None) == "random_file.xyz"

    def test_video_renamed(self):
        dt = datetime(2023, 12, 1, 9, 0, 0)
        result = build_renamed_filename("VID_001.mp4", dt)
        assert result == "2023-12-01_09-00-00.mp4"


# ======================== build_destination_path ========================


class TestBuildDestinationPath:
    def test_normal_photo(self, tmp_path):
        dt = datetime(2024, 5, 13, 14, 20, 35)
        result = build_destination_path(tmp_path, "IMG_001.jpg", dt, None, False)
        assert result == tmp_path / "2024_media" / "05.2024_media" / "05.2024_photo" / "IMG_001.jpg"

    def test_normal_video(self, tmp_path):
        dt = datetime(2024, 5, 13, 14, 20, 35)
        result = build_destination_path(tmp_path, "VID_001.mp4", dt, None, False)
        assert result == tmp_path / "2024_media" / "05.2024_media" / "05.2024_video" / "VID_001.mp4"

    def test_renamed_photo(self, tmp_path):
        dt = datetime(2024, 5, 13, 14, 20, 35)
        result = build_destination_path(tmp_path, "IMG_001.jpg", dt, None, True)
        assert result == tmp_path / "2024_media" / "05.2024_media" / "05.2024_photo" / "2024-05-13_14-20-35.jpg"

    def test_renamed_video(self, tmp_path):
        dt = datetime(2023, 12, 1, 9, 0, 0)
        result = build_destination_path(tmp_path, "VID_001.mp4", dt, None, True)
        assert result == tmp_path / "2023_media" / "12.2023_media" / "12.2023_video" / "2023-12-01_09-00-00.mp4"

    def test_no_date_photo(self, tmp_path):
        result = build_destination_path(tmp_path, "IMG_001.jpg", None, None, False)
        assert result == tmp_path / FOLDER_NO_DATA / "photo" / "IMG_001.jpg"

    def test_no_date_video(self, tmp_path):
        result = build_destination_path(tmp_path, "VID_001.mp4", None, None, False)
        assert result == tmp_path / FOLDER_NO_DATA / "video" / "VID_001.mp4"

    def test_no_date_unknown_extension(self, tmp_path):
        result = build_destination_path(tmp_path, "notes.txt", None, None, False)
        assert result == tmp_path / FOLDER_NO_DATA / "notes.txt"

    def test_duplicates_folder(self, tmp_path):
        result = build_destination_path(tmp_path, "IMG_001.jpg", None, FOLDER_DUPLICATES)
        assert result == tmp_path / FOLDER_DUPLICATES / "IMG_001.jpg"

    def test_junk_folder(self, tmp_path):
        result = build_destination_path(tmp_path, "tiny.jpg", None, FOLDER_JUNK)
        assert result == tmp_path / FOLDER_JUNK / "tiny.jpg"

    def test_raw_photo(self, tmp_path):
        dt = datetime(2022, 8, 15, 10, 30, 0)
        result = build_destination_path(tmp_path, "DSC_001.NEF", dt, None, False)
        assert result == tmp_path / "2022_media" / "08.2022_media" / "08.2022_photo" / "DSC_001.NEF"

    def test_heic_photo(self, tmp_path):
        dt = datetime(2024, 1, 1, 12, 0, 0)
        result = build_destination_path(tmp_path, "IMG_1234.HEIC", dt, None, False)
        assert result == tmp_path / "2024_media" / "01.2024_media" / "01.2024_photo" / "IMG_1234.HEIC"

    def test_year_boundary(self, tmp_path):
        dt = datetime(2020, 1, 1, 0, 0, 1)
        result = build_destination_path(tmp_path, "IMG_001.jpg", dt, None, False)
        assert result == tmp_path / "2020_media" / "01.2020_media" / "01.2020_photo" / "IMG_001.jpg"

    def test_december(self, tmp_path):
        dt = datetime(2024, 12, 31, 23, 59, 59)
        result = build_destination_path(tmp_path, "IMG_999.jpg", dt, None, False)
        assert result == tmp_path / "2024_media" / "12.2024_media" / "12.2024_photo" / "IMG_999.jpg"


# ======================== is_junk_file ========================


class TestIsJunkFile:
    def test_small_photo_junk(self, tmp_path):
        f = tmp_path / "tiny.jpg"
        f.write_bytes(b"x" * 1000)  # 1 КБ < 2048 КБ
        result = is_junk_file(f, photo_max_bytes=2 * 1024 * 1024, video_max_seconds=None, video_max_bytes=None)
        assert result is not None
        assert "мелкий файл" in result

    def test_large_photo_not_junk(self, tmp_path):
        f = tmp_path / "big.jpg"
        f.write_bytes(b"x" * (3 * 1024 * 1024))  # 3 МБ > 2 МБ
        result = is_junk_file(f, photo_max_bytes=2 * 1024 * 1024, video_max_seconds=None, video_max_bytes=None)
        assert result is None

    def test_exact_threshold_photo(self, tmp_path):
        f = tmp_path / "exact.jpg"
        f.write_bytes(b"x" * (2 * 1024 * 1024))  # ровно 2 МБ
        result = is_junk_file(f, photo_max_bytes=2 * 1024 * 1024, video_max_seconds=None, video_max_bytes=None)
        assert result is not None

    def test_no_photo_threshold_means_not_junk(self, tmp_path):
        f = tmp_path / "tiny.jpg"
        f.write_bytes(b"x" * 10)
        result = is_junk_file(f, photo_max_bytes=None, video_max_seconds=None, video_max_bytes=None)
        assert result is None

    def test_small_video_by_size_junk(self, tmp_path):
        f = tmp_path / "tiny.mp4"
        f.write_bytes(b"x" * 1000)
        result = is_junk_file(f, photo_max_bytes=None, video_max_seconds=None, video_max_bytes=5 * 1024)
        assert result is not None
        assert "мелкое видео" in result

    def test_heic_not_junk_by_size(self, tmp_path):
        f = tmp_path / "big.heic"
        f.write_bytes(b"x" * (5 * 1024 * 1024))
        result = is_junk_file(f, photo_max_bytes=2 * 1024 * 1024, video_max_seconds=None, video_max_bytes=None)
        assert result is None

    def test_raw_not_junk_by_size(self, tmp_path):
        f = tmp_path / "big.CR2"
        f.write_bytes(b"x" * (10 * 1024 * 1024))
        result = is_junk_file(f, photo_max_bytes=2 * 1024 * 1024, video_max_seconds=None, video_max_bytes=None)
        assert result is None

    def test_png_not_junk_by_size(self, tmp_path):
        f = tmp_path / "big.png"
        f.write_bytes(b"x" * (5 * 1024 * 1024))
        result = is_junk_file(f, photo_max_bytes=2 * 1024 * 1024, video_max_seconds=None, video_max_bytes=None)
        assert result is None

    def test_tiff_not_junk_by_size(self, tmp_path):
        f = tmp_path / "big.TIFF"
        f.write_bytes(b"x" * (5 * 1024 * 1024))
        result = is_junk_file(f, photo_max_bytes=2 * 1024 * 1024, video_max_seconds=None, video_max_bytes=None)
        assert result is None

    def test_non_media_not_junk(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_bytes(b"x" * 10)
        result = is_junk_file(f, photo_max_bytes=2 * 1024 * 1024, video_max_seconds=None, video_max_bytes=None)
        assert result is None


# ======================== detect_messenger ========================


class TestDetectMessenger:
    def test_whatsapp_img(self):
        assert detect_messenger("IMG-20240513-WA0001.jpg") == "whatsapp"

    def test_whatsapp_vid(self):
        assert detect_messenger("VID-20240513-WA0002.mp4") == "whatsapp"

    def test_telegram_photo(self):
        assert detect_messenger("photo_2024-05-13_14-20-35.jpg") == "telegram"

    def test_telegram_video(self):
        assert detect_messenger("video_2024-05-13_14-20-35.mp4") == "telegram"

    def test_viber(self):
        assert detect_messenger("IMG_20240513_142035.jpg") == "viber"

    def test_not_messenger(self):
        assert detect_messenger("IMG_001.jpg") is None

    def test_regular_filename(self):
        assert detect_messenger("2024-05-13_14-20-35.jpg") is None

    def test_case_insensitive_whatsapp(self):
        assert detect_messenger("img-20240513-wa0001.jpg") == "whatsapp"

    def test_case_insensitive_telegram(self):
        assert detect_messenger("PHOTO_2024-05-13_14-20-35.JPG") == "telegram"


# ======================== resolve_collision ========================


class TestResolveCollision:
    def test_no_collision(self, tmp_path):
        target = tmp_path / "file.jpg"
        assert resolve_collision(target) == target

    def test_single_collision(self, tmp_path):
        target = tmp_path / "file.jpg"
        target.write_bytes(b"x")
        resolved = resolve_collision(target)
        assert resolved.name == "file_1.jpg"

    def test_double_collision(self, tmp_path):
        target = tmp_path / "file.jpg"
        target.write_bytes(b"x")
        dup1 = tmp_path / "file_1.jpg"
        dup1.write_bytes(b"x")
        resolved = resolve_collision(target)
        assert resolved.name == "file_2.jpg"

    def test_dir_collision(self, tmp_path):
        d = tmp_path / "2024_media"
        d.mkdir()
        resolved = resolve_collision(d)
        assert resolved.name == "2024_media_1"

    def test_chain_resolution(self, tmp_path):
        target = tmp_path / "file.jpg"
        target.write_bytes(b"x")
        (tmp_path / "file_1.jpg").write_bytes(b"x")
        (tmp_path / "file_2.jpg").write_bytes(b"x")
        resolved = resolve_collision(target)
        assert resolved.name == "file_3.jpg"
