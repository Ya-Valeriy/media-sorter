"""
Unit-тесты для media_sorter/hash_utils.py:
- get_file_hash (проверка MD5)
- build_hash_index
- find_duplicates
"""

from pathlib import Path

from media_sorter.hash_utils import build_hash_index, find_duplicates, get_file_hash


class TestGetFileHash:
    def test_known_content(self, tmp_path):
        """Файл с известным содержимым должен иметь известный MD5."""
        f = tmp_path / "test.txt"
        f.write_bytes(b"Hello, World!")
        h = get_file_hash(f)
        # MD5("Hello, World!") = 65a8e27d8879283831b664bd8b7f0ad4
        assert h == "65a8e27d8879283831b664bd8b7f0ad4"

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        h = get_file_hash(f)
        # MD5("") = d41d8cd98f00b204e9800998ecf8427e
        assert h == "d41d8cd98f00b204e9800998ecf8427e"

    def test_same_content_same_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"identical")
        f2.write_bytes(b"identical")
        assert get_file_hash(f1) == get_file_hash(f2)

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"aaa")
        f2.write_bytes(b"bbb")
        assert get_file_hash(f1) != get_file_hash(f2)

    def test_large_file(self, tmp_path):
        """Файл > 8 КБ (размер буфера) должен хэшироваться корректно."""
        f = tmp_path / "large.bin"
        data = b"x" * (100 * 1024)  # 100 КБ
        f.write_bytes(data)
        h = get_file_hash(f)
        assert len(h) == 32  # MD5 всегда 32 символа

    def test_binary_file(self, tmp_path):
        f = tmp_path / "binary.jpg"
        f.write_bytes(bytes(range(256)))
        h = get_file_hash(f)
        assert len(h) == 32


class TestBuildHashIndex:
    def test_unique_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"aaa")
        f2.write_bytes(b"bbb")
        index = build_hash_index([f1, f2])
        assert len(index) == 2

    def test_duplicate_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"same")
        f2.write_bytes(b"same")
        index = build_hash_index([f1, f2])
        assert len(index) == 1
        assert len(index[list(index.keys())[0]]) == 2

    def test_empty_list(self):
        index = build_hash_index([])
        assert index == {}

    def test_mixed_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f3 = tmp_path / "c.txt"
        f1.write_bytes(b"aaa")
        f2.write_bytes(b"aaa")  # дубликат f1
        f3.write_bytes(b"bbb")
        index = build_hash_index([f1, f2, f3])
        assert len(index) == 2
        for paths in index.values():
            assert len(paths) >= 1


class TestFindDuplicates:
    def test_no_duplicates(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_bytes(b"aaa")
        (src / "b.txt").write_bytes(b"bbb")
        dest_index = {}
        dups = find_duplicates([src / "a.txt", src / "b.txt"], dest_index)
        assert dups == {}

    def test_one_duplicate(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        src.mkdir()
        dest.mkdir()
        (dest / "existing.jpg").write_bytes(b"same content")
        (src / "copy.jpg").write_bytes(b"same content")
        dest_index = build_hash_index([dest / "existing.jpg"])
        dups = find_duplicates([src / "copy.jpg"], dest_index)
        assert len(dups) == 1

    def test_multiple_duplicates(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        src.mkdir()
        dest.mkdir()
        (dest / "a.jpg").write_bytes(b"content_a")
        (dest / "b.jpg").write_bytes(b"content_b")
        (src / "a_copy.jpg").write_bytes(b"content_a")
        (src / "b_copy.jpg").write_bytes(b"content_b")
        (src / "c_new.jpg").write_bytes(b"content_c")
        dest_index = build_hash_index([dest / "a.jpg", dest / "b.jpg"])
        dups = find_duplicates([src / "a_copy.jpg", src / "b_copy.jpg", src / "c_new.jpg"], dest_index)
        assert len(dups) == 2

    def test_empty_source(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "a.jpg").write_bytes(b"content")
        dest_index = build_hash_index([dest / "a.jpg"])
        dups = find_duplicates([], dest_index)
        assert dups == {}
