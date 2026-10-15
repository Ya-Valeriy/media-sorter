"""
Unit-тесты для модуля date_parser: определение года и месяца из имени папки.
"""

from renamer.date_parser import (
    get_month_year_from_exif,
    is_year_range,
    parse_month_year,
    parse_year,
)


# --- parse_year ---


def test_parse_year_simple():
    assert parse_year('2024') == 2024
    assert parse_year('2024_Яманкины') == 2024
    assert parse_year('Photos_2024') == 2024
    assert parse_year('2024_yamankin_media') == 2024
    assert parse_year('2024_media') == 2024
    assert parse_year('2006 Ч') == 2006
    assert parse_year('2023Ч') == 2023


def test_parse_year_none():
    assert parse_year('_unknown_yamankin_media') is None
    assert parse_year('Фото') is None
    assert parse_year('рома раз в месяц') is None
    assert parse_year('') is None


# --- is_year_range ---


def test_is_year_range():
    assert is_year_range('2003-2005 Ч') is True
    assert is_year_range('2003–2005') is True
    assert is_year_range('2024') is False
    assert is_year_range('2024_yamankin_media') is False


# --- parse_month_year ---


def test_parse_month_year_dot():
    assert parse_month_year('05.2024') == (5, 2024)
    assert parse_month_year('12.2016') == (12, 2016)
    assert parse_month_year('10.2017 Ч') == (10, 2017)
    assert parse_month_year('05.2024_media') == (5, 2024)
    assert parse_month_year('12.2016_photo') == (12, 2016)


def test_parse_month_year_dash():
    assert parse_month_year('05-2024') == (5, 2024)
    assert parse_month_year('2024-05') == (5, 2024)
    assert parse_month_year('05-2024_yamankin_media') == (5, 2024)


def test_parse_month_year_name():
    assert parse_month_year('Май 2024') == (5, 2024)
    assert parse_month_year('May_2024') == (5, 2024)
    assert parse_month_year('Декабрь 2023') == (12, 2023)
    assert parse_month_year('январь 2020') == (1, 2020)


def test_parse_month_year_none():
    assert parse_month_year('2024') is None
    assert parse_month_year('фото') is None
    assert parse_month_year('_unknown_yamankin_media') is None
    assert parse_month_year('_unknown_media') is None


# --- EXIF-фолбэк ---


def test_get_month_year_from_exif_empty(tmp_path):
    """В пустой папке без фото EXIF-фолбэк возвращает None."""
    assert get_month_year_from_exif(tmp_path, frozenset({'.jpg'})) is None