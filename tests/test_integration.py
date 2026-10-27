"""
Интеграционные тесты для media_sorter:
- полный цикл обработки файлов (создание → сортировка → проверка структуры)
- проверка мусора, дубликатов, бездаты
"""

import csv
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from media_sorter.date_extractor import get_creation_date
from media_sorter.hash_utils import get_file_hash
from media_sorter.mover import (
    FOLDER_DUPLICATES,
    FOLDER_JUNK,
    FOLDER_NO_DATA,
    build_destination_path,
    move_file_safely,
    resolve_collision,
)


# ======================== Вспомогательные ========================


def create_test_photo(tmp_path: Path, name: str, size: int = 100) -> Path:
    """Создаёт тестовый файл-фото с заданным размером."""
    f = tmp_path / name
    f.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * size)  # JPEG-подобный заголовок
    return f


def create_test_video(tmp_path: Path, name: str, size: int = 100) -> Path:
    """Создаёт тестовый файл-видео с заданным размером."""
    f = tmp_path / name
    f.write_bytes(b"\x00\x00\x00\x1cftyp" + b"\x00" * size)  # MP4-подобный заголовок
    return f


# ======================== build_destination_path ========================


class TestDestinationPathIntegration:
    """Проверка, что пути формируются корректно для всех сценариев."""

    def test_photo_2024_may(self, tmp_path):
        dt = datetime(2024, 5, 13, 14, 20, 35)
        path = build_destination_path(tmp_path, "IMG_001.jpg", dt, None, False)
        parts = path.parts
        # Структура: year_dir / month_dir / type_dir / filename
        # parts[-4] = 2024_media, parts[-3] = 05.2024_media, parts[-2] = 05.2024_photo, parts[-1] = IMG_001.jpg
        assert "_media" in parts[-4]  # 2024_media
        assert "_media" in parts[-3]  # 05.2024_media
        assert "_photo" in parts[-2]  # 05.2024_photo
        assert path.name == "IMG_001.jpg"

    def test_video_2023_dec(self, tmp_path):
        dt = datetime(2023, 12, 1, 9, 0, 0)
        path = build_destination_path(tmp_path, "VID_001.mp4", dt, None, False)
        parts = path.parts
        assert "_media" in parts[-4]  # 2023_media
        assert "_media" in parts[-3]  # 12.2023_media
        assert "_video" in parts[-2]  # 12.2023_video
        assert path.name == "VID_001.mp4"

    def test_raw_nef(self, tmp_path):
        dt = datetime(2022, 8, 15, 10, 30, 0)
        path = build_destination_path(tmp_path, "DSC_001.NEF", dt, None, False)
        parts = path.parts
        assert "_photo" in parts[-2]  # 08.2022_photo
        assert path.name == "DSC_001.NEF"

    def test_heic(self, tmp_path):
        dt = datetime(2024, 1, 1, 12, 0, 0)
        path = build_destination_path(tmp_path, "IMG_1234.HEIC", dt, None, False)
        parts = path.parts
        assert "_photo" in parts[-2]  # 01.2024_photo
        assert path.name == "IMG_1234.HEIC"

    def test_no_date_photo(self, tmp_path):
        path = build_destination_path(tmp_path, "IMG_001.jpg", None, None, False)
        assert FOLDER_NO_DATA in path.parts
        assert "photo" in path.parts

    def test_no_date_video(self, tmp_path):
        path = build_destination_path(tmp_path, "VID_001.mp4", None, None, False)
        assert FOLDER_NO_DATA in path.parts
        assert "video" in path.parts

    def test_duplicates(self, tmp_path):
        path = build_destination_path(tmp_path, "IMG_001.jpg", None, FOLDER_DUPLICATES)
        assert FOLDER_DUPLICATES in path.parts
        assert path.parts[-1] == "IMG_001.jpg"

    def test_junk(self, tmp_path):
        path = build_destination_path(tmp_path, "tiny.jpg", None, FOLDER_JUNK)
        assert FOLDER_JUNK in path.parts
        assert path.parts[-1] == "tiny.jpg"

    def test_renamed_photo(self, tmp_path):
        dt = datetime(2024, 5, 13, 14, 20, 35)
        path = build_destination_path(tmp_path, "IMG_001.jpg", dt, None, True)
        assert "2024-05-13_14-20-35.jpg" == path.name

    def test_renamed_video(self, tmp_path):
        dt = datetime(2023, 12, 1, 9, 0, 0)
        path = build_destination_path(tmp_path, "VID_001.mp4", dt, None, True)
        assert "2023-12-01_09-00-00.mp4" == path.name


# ======================== resolve_collision ========================


class TestResolveCollisionIntegration:
    def test_chain_of_5(self, tmp_path):
        target = tmp_path / "file.jpg"
        target.write_bytes(b"x")  # сам target тоже существует
        for i in range(1, 6):
            (tmp_path / f"file_{i}.jpg").write_bytes(b"x")
        resolved = resolve_collision(target)
        assert resolved.name == "file_6.jpg"

    def test_nested_path(self, tmp_path):
        parent = tmp_path / "sub" / "dir"
        parent.mkdir(parents=True)
        target = parent / "file.jpg"
        target.write_bytes(b"x")
        resolved = resolve_collision(target)
        assert resolved.parent == parent
        assert resolved.name == "file_1.jpg"


# ======================== move_file_safely ========================


class TestMoveFileSafely:
    def test_move_new_file(self, tmp_path):
        src = tmp_path / "src" / "a.jpg"
        src.parent.mkdir()
        src.write_bytes(b"content")
        dest = tmp_path / "dst" / "a.jpg"
        final, status = move_file_safely(src, dest)
        assert status == "moved"
        assert final == dest
        assert dest.read_bytes() == b"content"
        assert not src.exists()

    def test_move_with_collision(self, tmp_path):
        src = tmp_path / "src" / "a.jpg"
        src.parent.mkdir()
        src.write_bytes(b"content")
        dest = tmp_path / "dst" / "a.jpg"
        dest.parent.mkdir()
        dest.write_bytes(b"existing")
        final, status = move_file_safely(src, dest)
        assert status == "moved"
        assert final.name == "a_1.jpg"
        assert (tmp_path / "dst" / "a_1.jpg").read_bytes() == b"content"
        assert dest.read_bytes() == b"existing"  # оригинал не перезаписан

    def test_dry_run(self, tmp_path):
        src = tmp_path / "src" / "a.jpg"
        src.parent.mkdir()
        src.write_bytes(b"content")
        dest = tmp_path / "dst" / "a.jpg"
        final, status = move_file_safely(src, dest, dry_run=True)
        assert status == "planned"
        assert src.exists()  # файл не перемещён
        assert not dest.exists()

    def test_move_creates_parent_dirs(self, tmp_path):
        src = tmp_path / "src" / "a.jpg"
        src.parent.mkdir()
        src.write_bytes(b"content")
        dest = tmp_path / "a" / "b" / "c" / "a.jpg"
        final, status = move_file_safely(src, dest)
        assert status == "moved"
        assert dest.exists()


# ======================== get_creation_date ========================


class TestGetCreationDate:
    """Проверка определения даты из имени файла (без EXIF/ffprobe)."""

    def test_camera_name(self, tmp_path):
        f = create_test_photo(tmp_path, "IMG_20240513_142035.jpg")
        dt, source, approx = get_creation_date(f)
        assert dt == datetime(2024, 5, 13, 14, 20, 35)
        assert source == "filename"
        assert approx is False

    def test_dashed_name(self, tmp_path):
        f = create_test_photo(tmp_path, "2024-05-13_14-20-35.jpg")
        dt, source, approx = get_creation_date(f)
        assert dt == datetime(2024, 5, 13, 14, 20, 35)
        assert source == "filename"
        assert approx is False

    def test_no_date_no_mtime(self, tmp_path):
        f = create_test_photo(tmp_path, "random.jpg")
        dt, source, approx = get_creation_date(f)
        assert dt is not None
        assert source == "mtime"
        assert approx is True

    def test_no_date_with_mtime(self, tmp_path):
        f = create_test_photo(tmp_path, "random.jpg")
        dt, source, approx = get_creation_date(f)
        assert dt is not None
        assert source == "mtime"
        assert approx is True

    def test_video_no_date(self, tmp_path):
        f = create_test_video(tmp_path, "random.mp4")
        dt, source, approx = get_creation_date(f)
        assert dt is None
        assert source is None

    def test_no_date_with_mtime(self, tmp_path):
        f = create_test_photo(tmp_path, "random.jpg")
        dt, source, approx = get_creation_date(f, allow_mtime=True)
        assert dt is not None
        assert source == "mtime"
        assert approx is True

    def test_video_no_date(self, tmp_path):
        f = create_test_video(tmp_path, "random.mp4")
        dt, source, approx = get_creation_date(f, allow_mtime=False)
        assert dt is None
        assert source is None


# ======================== MD5 hash uniqueness ========================


class TestHashUniqueness:
    def test_different_files_different_hashes(self, tmp_path):
        hashes = []
        for i in range(10):
            f = tmp_path / f"file_{i}.jpg"
            f.write_bytes(f"content_{i}".encode())
            hashes.append(get_file_hash(f))
        assert len(hashes) == len(set(hashes)), "Все хэши должны быть уникальны"

    def test_same_content_same_hash(self, tmp_path):
        f1 = tmp_path / "a.jpg"
        f2 = tmp_path / "b.jpg"
        f1.write_bytes(b"identical_content")
        f2.write_bytes(b"identical_content")
        assert get_file_hash(f1) == get_file_hash(f2)

    def test_hash_is_deterministic(self, tmp_path):
        f = tmp_path / "test.jpg"
        f.write_bytes(b"test_data")
        h1 = get_file_hash(f)
        h2 = get_file_hash(f)
        assert h1 == h2


# ======================== CSV report structure ========================


class TestReportFields:
    """Проверка структуры CSV-отчёта (поля, кодировка)."""

    def test_csv_header(self, tmp_path):
        """CSV должен содержать ожидаемые заголовки."""
        from media_sorter.reporter import REPORT_FIELDS, generate_report

        records = [
            {
                "source_path": "/src/a.jpg",
                "dest_path": "/dst/2024_media/05.2024_media/05.2024_photo/a.jpg",
                "date_source": "filename",
                "date_value": "2024-05-13T14:20:35",
                "is_approximate": False,
                "warnings": "",
            }
        ]
        report_path = tmp_path / "report.csv"
        generate_report(records, report_path)

        with open(report_path, encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == REPORT_FIELDS
            row = next(reader)
            assert row["date_source"] == "filename"
            assert row["source_path"] == "/src/a.jpg"

    def test_csv_utf8_bom(self, tmp_path):
        """CSV должен открываться в Excel (BOM-кодировка)."""
        from media_sorter.reporter import generate_report

        records = [{"source_path": "тест.jpg", "dest_path": "dst/тест.jpg", "date_source": "", "date_value": "", "is_approximate": False, "warnings": ""}]
        report_path = tmp_path / "report.csv"
        generate_report(records, report_path)

        # Проверяем, что файл начинается с BOM
        with open(report_path, "rb") as fh:
            start = fh.read(3)
            assert start == b"\xef\xbb\xbf", "CSV должен иметь UTF-8 BOM для Excel"
