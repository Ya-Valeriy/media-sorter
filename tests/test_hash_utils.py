"""
Тесты для модуля вычисления хэшей (media_sorter.hash_utils).
"""

from pathlib import Path

from media_sorter.hash_utils import build_hash_index, find_duplicates, get_file_hash


def test_get_file_hash(tmp_path: Path) -> None:
    """MD5 известной строки вычисляется корректно."""
    file_path = tmp_path / 'test.bin'
    file_path.write_bytes(b'hello world')
    assert get_file_hash(file_path) == '5eb63bbbe01eeed093cb22bb8f5acdc3'


def test_get_file_hash_large_file(tmp_path: Path) -> None:
    """Хэш файла больше буфера (8 КБ) вычисляется корректно."""
    file_path = tmp_path / 'large.bin'
    file_path.write_bytes(b'x' * 100_000)
    digest = get_file_hash(file_path)
    assert len(digest) == 32
    assert digest == get_file_hash(file_path)  # детерминированность


def test_build_hash_index_and_find_duplicates(tmp_path: Path) -> None:
    """Дубликаты находятся по совпадению MD5."""
    a = tmp_path / 'a.jpg'
    b = tmp_path / 'b.jpg'
    c = tmp_path / 'c.jpg'
    a.write_bytes(b'same content')
    b.write_bytes(b'same content')
    c.write_bytes(b'different content')

    index = build_hash_index([a])
    duplicates = find_duplicates([b, c], index)

    assert get_file_hash(b) in duplicates
    assert get_file_hash(c) not in duplicates
    assert duplicates[get_file_hash(b)] == (b, a)