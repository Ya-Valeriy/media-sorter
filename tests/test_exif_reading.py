"""
Тесты чтения даты съёмки из EXIF на реальных файлах.

DateTimeOriginal у камер лежит в Exif SubIFD (0x8769), а не в корневом IFD.
Раньше читался только корневой IFD, дата терялась и файлы уходили на mtime.
Файлы создаются через Pillow — это настоящие JPEG/PNG с EXIF.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest

PIL = pytest.importorskip('PIL')
from PIL import Image  # noqa: E402

from media_sorter.date_extractor import (  # noqa: E402
    _apply_offset,
    _read_pillow_exif,
    extract_date_from_exif,
    get_creation_date,
    is_scanned_negative,
)
from media_sorter.mover import build_destination_path  # noqa: E402

DATE_ORIGINAL = 0x9003
DATE_DIGITIZED = 0x9004
DATE_BASE = 0x0132
OFFSET_TIME_ORIGINAL = 0x9011
EXIF_IFD = 0x8769
MAKE = 0x010F
MODEL = 0x0110


def make_jpeg(path: Path, date_original=None, date_digitized=None, date_base=None,
              offset=None, make=None, model=None) -> Path:
    img = Image.new('RGB', (16, 16), 'gray')
    exif = img.getexif()
    if date_base:
        exif[DATE_BASE] = date_base
    if make:
        exif[MAKE] = make
    if model:
        exif[MODEL] = model
    if date_original or date_digitized or offset:
        sub = exif.get_ifd(EXIF_IFD)
        if date_original:
            sub[DATE_ORIGINAL] = date_original
        if date_digitized:
            sub[DATE_DIGITIZED] = date_digitized
        if offset:
            sub[OFFSET_TIME_ORIGINAL] = offset
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, exif=exif, format='JPEG')
    return path


class TestSubIfdReading:
    def test_reads_datetime_original_from_sub_ifd(self, tmp_path):
        f = make_jpeg(tmp_path / 'c.jpg', date_original='2019:08:14 17:45:12')
        data = _read_pillow_exif(str(f))
        assert data is not None
        assert data['tags']['DateTimeOriginal'] == '2019:08:14 17:45:12'

    def test_extract_date_returns_shooting_date(self, tmp_path):
        f = make_jpeg(tmp_path / 'c.jpg', date_original='2019:08:14 17:45:12')
        dt, _ = extract_date_from_exif(f)
        assert dt == datetime(2019, 8, 14, 17, 45, 12)

    def test_get_creation_date_source_is_exif(self, tmp_path):
        """Главная регрессия: раньше источником был mtime."""
        f = make_jpeg(tmp_path / 'c.jpg', date_original='2016:03:17 08:18:33')
        dt, source, approx = get_creation_date(f)
        assert dt == datetime(2016, 3, 17, 8, 18, 33)
        assert source == 'exif'
        assert approx is False

    def test_datetime_digitized_fallback(self, tmp_path):
        f = make_jpeg(tmp_path / 's.jpg', date_digitized='2005:01:02 03:04:05')
        dt, _ = extract_date_from_exif(f)
        assert dt == datetime(2005, 1, 2, 3, 4, 5)

    def test_datetime_original_wins_over_digitized(self, tmp_path):
        f = make_jpeg(tmp_path / 'b.jpg', date_original='2019:08:14 17:45:12',
                      date_digitized='2020:01:01 00:00:00')
        dt, _ = extract_date_from_exif(f)
        assert dt == datetime(2019, 8, 14, 17, 45, 12)

    def test_base_ifd_datetime_still_works(self, tmp_path):
        f = make_jpeg(tmp_path / 'p.jpg', date_base='2018:06:01 09:30:00')
        dt, _ = extract_date_from_exif(f)
        assert dt == datetime(2018, 6, 1, 9, 30, 0)

    def test_exif_wins_over_filename(self, tmp_path):
        f = make_jpeg(tmp_path / 'IMG_20240513_142035.jpg', date_original='2019:08:14 17:45:12')
        dt, source, _ = get_creation_date(f)
        assert dt == datetime(2019, 8, 14, 17, 45, 12)
        assert source == 'exif'

    def test_file_without_exif_falls_back_to_mtime(self, tmp_path):
        f = tmp_path / 'plain.jpg'
        Image.new('RGB', (16, 16), 'gray').save(f, format='JPEG')
        os.utime(f, (datetime(2015, 2, 3, 12, 38, 21).timestamp(),) * 2)
        dt, source, approx = get_creation_date(f)
        assert source == 'mtime'
        assert approx is True
        assert dt.year == 2015


class TestOffsetTime:
    def test_night_shot_keeps_its_day(self, tmp_path):
        """Снимок 00:30 по Москве не должен уехать на 16 марта."""
        f = make_jpeg(tmp_path / 'n.jpg', date_original='2016:03:17 00:30:00', offset='+03:00')
        dt, _ = extract_date_from_exif(f)
        assert dt == datetime(2016, 3, 17, 0, 30, 0)

    def test_new_year_stays_in_year(self, tmp_path):
        f = make_jpeg(tmp_path / 'ny.jpg', date_original='2023:01:01 00:20:00', offset='+03:00')
        dt, _ = extract_date_from_exif(f)
        assert (dt.year, dt.month, dt.day) == (2023, 1, 1)

    def test_apply_offset_is_identity(self):
        dt = datetime(2016, 3, 17, 0, 30)
        assert _apply_offset(dt, '+03:00') == dt
        assert _apply_offset(dt, '-08:00') == dt
        assert _apply_offset(dt, None) == dt


class TestEndToEnd:
    def _argv(self, src, dst, tmp_path, *extra):
        return ['--source', str(src), '--destination', str(dst),
                '--log-file', str(tmp_path / 'sort.log'),
                '--report-file', str(tmp_path / 'report.csv'),
                '--duplicates-log', str(tmp_path / 'dup.log'),
                '--errors-log', str(tmp_path / 'err.log'), *extra]

    def test_photo_lands_in_shooting_month(self, tmp_path):
        src, dst = tmp_path / 'src', tmp_path / 'dst'
        make_jpeg(src / 'IMG_0001.jpg', date_original='2016:03:17 08:18:33')
        from media_sorter.main import main
        assert main(self._argv(src, dst, tmp_path, '--yes', '--no-junk')) == 0
        assert (dst / '2016_media' / '03.2016_media' / '03.2016_photo'
                / '2016-03-17_08-18-33.jpg').exists()

    def test_three_dates_three_months(self, tmp_path):
        src, dst = tmp_path / 'src', tmp_path / 'dst'
        make_jpeg(src / 'a.jpg', date_original='2016:03:17 08:18:33')
        make_jpeg(src / 'b.jpg', date_original='2019:08:14 17:45:12')
        make_jpeg(src / 'c.jpg', date_original='2023:12:31 23:59:59')
        from media_sorter.main import main
        main(self._argv(src, dst, tmp_path, '--yes', '--no-junk'))
        assert (dst / '2016_media' / '03.2016_media' / '03.2016_photo').is_dir()
        assert (dst / '2019_media' / '08.2019_media' / '08.2019_photo').is_dir()
        assert (dst / '2023_media' / '12.2023_media' / '12.2023_photo').is_dir()

    def test_destination_path_matches_date(self, tmp_path):
        path = build_destination_path(tmp_path, 'photo.jpg',
                                      datetime(2016, 3, 17, 8, 18, 33), None, rename_by_date=True)
        assert path.parent.name == '03.2016_photo'
        assert path.name == '2016-03-17_08-18-33.jpg'


class TestScannedNegative:
    @pytest.mark.parametrize('make,model', [
        ('Canon', 'CanoScan 9000F'),
        ('Nikon', 'COOLSCAN V ED'),
        ('EPSON', 'Perfection V800'),
        ('Plustek', 'OpticFilm 8200i'),
    ])
    def test_scanner_detected(self, tmp_path, make, model):
        assert is_scanned_negative(make_jpeg(tmp_path / 's.dng', make=make, model=model)) is True

    @pytest.mark.parametrize('make,model', [
        ('Canon', 'Canon EOS 5D Mark IV'),
        ('NIKON CORPORATION', 'NIKON D850'),
        ('SONY', 'ILCE-7M3'),
        ('FUJIFILM', 'X-T5'),
    ])
    def test_camera_not_negative(self, tmp_path, make, model):
        assert is_scanned_negative(make_jpeg(tmp_path / 'c.dng', make=make, model=model)) is False

    def test_no_exif_not_negative(self, tmp_path):
        f = tmp_path / 'e.dng'
        f.write_bytes(b'not a real dng')
        assert is_scanned_negative(f) is False
