"""
Unit-тесты для media_sorter/date_extractor.py:
- extract_date_from_filename (все шаблоны)
- _validate_date
- SUPPORTED_EXTENSIONS / IMAGE_EXTENSIONS / VIDEO_EXTENSIONS
"""

from datetime import datetime
from pathlib import Path

from media_sorter.date_extractor import (
    FILENAME_DATE_PATTERNS,
    IMAGE_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    VIDEO_EXTENSIONS,
    extract_date_from_filename,
)


# ======================== SUPPORTED_EXTENSIONS ========================


class TestExtensions:
    def test_all_image_extensions_supported(self):
        for ext in [".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif"]:
            assert ext in SUPPORTED_EXTENSIONS

    def test_all_raw_extensions_supported(self):
        for ext in [".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng"]:
            assert ext in SUPPORTED_EXTENSIONS

    def test_all_video_extensions_supported(self):
        for ext in [".mp4", ".mov", ".avi", ".mkv", ".mts", ".3gp"]:
            assert ext in SUPPORTED_EXTENSIONS

    def test_image_extensions_subset(self):
        for ext in SUPPORTED_EXTENSIONS:
            if ext in VIDEO_EXTENSIONS:
                continue  # видео-расширения не входят в IMAGE_EXTENSIONS
            assert ext in IMAGE_EXTENSIONS or ext not in SUPPORTED_EXTENSIONS

    def test_no_overlap_image_video(self):
        assert IMAGE_EXTENSIONS.isdisjoint(VIDEO_EXTENSIONS)


# ======================== extract_date_from_filename ========================


class TestExtractDateFromFilename:
    """Тестирование 5 шаблонов из FILENAME_DATE_PATTERNS."""

    # --- Шаблон 1: IMG_20240513_142035 / VID_20240513_142035 ---

    def test_camera_img_full(self):
        dt = extract_date_from_filename(Path("IMG_20240513_142035.jpg"))
        assert dt == datetime(2024, 5, 13, 14, 20, 35)

    def test_camera_vid_full(self):
        dt = extract_date_from_filename(Path("VID_20240513_142035.mp4"))
        assert dt == datetime(2024, 5, 13, 14, 20, 35)

    def test_screenshot_full(self):
        dt = extract_date_from_filename(Path("Screenshot_20240513-142035.png"))
        assert dt == datetime(2024, 5, 13, 14, 20, 35)

    def test_numeric_full(self):
        dt = extract_date_from_filename(Path("20240513_142035.mp4"))
        assert dt == datetime(2024, 5, 13, 14, 20, 35)

    # --- Шаблон 2: 2024-05-13 14.20.35 / 2024-05-13_14-20-35 ---

    def test_dashed_with_space(self):
        dt = extract_date_from_filename(Path("2024-05-13 14.20.35.jpg"))
        assert dt == datetime(2024, 5, 13, 14, 20, 35)

    def test_dashed_with_underscore(self):
        dt = extract_date_from_filename(Path("2024-05-13_14-20-35.jpg"))
        assert dt == datetime(2024, 5, 13, 14, 20, 35)

    def test_screen_shot_with_at(self):
        dt = extract_date_from_filename(Path("Screen Shot 2024-05-13 at 14.20.35.png"))
        assert dt == datetime(2024, 5, 13, 14, 20, 35)

    def test_telegram_pattern(self):
        dt = extract_date_from_filename(Path("photo_2024-05-13_14-20-35.jpg"))
        assert dt == datetime(2024, 5, 13, 14, 20, 35)

    # --- Шаблон 3: IMG-20240513-WA / PXL_20240513 ---

    def test_whatsapp_img(self):
        dt = extract_date_from_filename(Path("IMG-20240513-WA0001.jpg"))
        assert dt == datetime(2024, 5, 13)

    def test_pxl(self):
        dt = extract_date_from_filename(Path("PXL_20240513_123456.jpg"))
        # PXL_20240513_123456 содержит и дату, и время
        assert dt == datetime(2024, 5, 13, 12, 34, 56)

    def test_vid_prefix(self):
        dt = extract_date_from_filename(Path("VID-20240513-WA0001.mp4"))
        assert dt == datetime(2024, 5, 13)

    # --- Шаблон 4: 2024-05-13 (только дата) ---

    def test_date_only_dashed(self):
        dt = extract_date_from_filename(Path("2024-05-13.jpg"))
        assert dt == datetime(2024, 5, 13)

    def test_date_only_underscore(self):
        dt = extract_date_from_filename(Path("2024_05_13.jpg"))
        assert dt == datetime(2024, 5, 13)

    # --- Шаблон 5: 20240513 (только дата, без разделителей) ---

    def test_date_only_numeric(self):
        dt = extract_date_from_filename(Path("20240513.jpg"))
        assert dt == datetime(2024, 5, 13)

    def test_date_only_numeric_with_underscore(self):
        dt = extract_date_from_filename(Path("2024_05_13.jpg"))
        assert dt == datetime(2024, 5, 13)

    # --- Крайние случаи ---

    def test_no_date_in_name(self):
        assert extract_date_from_filename(Path("random_file.jpg")) is None

    def test_empty_name(self):
        assert extract_date_from_filename(Path("")) is None

    def test_invalid_date(self):
        # 2024-13-45 — невалидная дата
        assert extract_date_from_filename(Path("2024-13-45.jpg")) is None

    def test_leap_year(self):
        dt = extract_date_from_filename(Path("2024-02-29.jpg"))
        assert dt == datetime(2024, 2, 29)

    def test_non_leap_year(self):
        # 2023-02-29 — невалидная дата
        assert extract_date_from_filename(Path("2023-02-29.jpg")) is None

    def test_path_with_directory(self):
        dt = extract_date_from_filename(Path("/some/path/IMG_20240513_142035.jpg"))
        assert dt == datetime(2024, 5, 13, 14, 20, 35)

    def test_uppercase_extension(self):
        dt = extract_date_from_filename(Path("IMG_20240513_142035.JPG"))
        assert dt == datetime(2024, 5, 13, 14, 20, 35)

    def test_heic_extension(self):
        dt = extract_date_from_filename(Path("IMG_20240513_142035.HEIC"))
        assert dt == datetime(2024, 5, 13, 14, 20, 35)

    def test_raw_extension(self):
        dt = extract_date_from_filename(Path("DSC_001.NEF"))
        assert dt is None  # NEF не содержит дату в имени

    def test_mp4_extension(self):
        dt = extract_date_from_filename(Path("VID_20240513_142035.mp4"))
        assert dt == datetime(2024, 5, 13, 14, 20, 35)
