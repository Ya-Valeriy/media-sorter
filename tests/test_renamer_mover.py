"""
Unit-тесты для renamer/mover.py:
- move_file_safely (перемещение, коллизии, dry_run, создание родительских папок)
- move_dir_safely (переименование папок, dry_run, ошибка при существующем назначении)
"""

from pathlib import Path

from renamer.mover import move_dir_safely, move_file_safely


# ======================== move_file_safely ========================


class TestMoveFileSafely:
    def test_move_to_new_dir(self, tmp_path):
        src = tmp_path / "src" / "a.jpg"
        src.parent.mkdir()
        src.write_bytes(b"content")
        dest_dir = tmp_path / "dst"
        final, status = move_file_safely(src, dest_dir)
        assert status == "moved"
        assert final == dest_dir / "a.jpg"
        assert final.read_bytes() == b"content"
        assert not src.exists()

    def test_collision_gets_suffix(self, tmp_path):
        src = tmp_path / "a.jpg"
        src.write_bytes(b"new")
        dest_dir = tmp_path / "dst"
        dest_dir.mkdir()
        (dest_dir / "a.jpg").write_bytes(b"existing")
        final, status = move_file_safely(src, dest_dir)
        assert status == "moved"
        assert final.name == "a_1.jpg"
        assert (dest_dir / "a.jpg").read_bytes() == b"existing"  # не перезаписан
        assert final.read_bytes() == b"new"

    def test_chain_of_collisions(self, tmp_path):
        src = tmp_path / "a.jpg"
        src.write_bytes(b"new")
        dest_dir = tmp_path / "dst"
        dest_dir.mkdir()
        (dest_dir / "a.jpg").write_bytes(b"x")
        (dest_dir / "a_1.jpg").write_bytes(b"x")
        final, status = move_file_safely(src, dest_dir)
        assert final.name == "a_2.jpg"

    def test_dry_run_does_not_touch_disk(self, tmp_path):
        src = tmp_path / "a.jpg"
        src.write_bytes(b"content")
        dest_dir = tmp_path / "dst"
        final, status = move_file_safely(src, dest_dir, dry_run=True)
        assert status == "planned"
        assert src.exists()  # файл на месте
        assert not dest_dir.exists()  # папка не создана

    def test_creates_dest_dir(self, tmp_path):
        src = tmp_path / "a.jpg"
        src.write_bytes(b"content")
        dest_dir = tmp_path / "2024_media" / "05.2024_media" / "05.2024_photo"
        final, status = move_file_safely(src, dest_dir)
        assert status == "moved"
        assert final.exists()

    def test_error_returns_error_status(self, tmp_path):
        src = tmp_path / "missing" / "a.jpg"  # файла нет → shutil.move упадёт
        dest_dir = tmp_path / "dst"
        final, status = move_file_safely(src, dest_dir)
        assert status == "error"
        assert final == dest_dir / "a.jpg"
        # файл в назначении не появился
        assert not (dest_dir / "a.jpg").exists()


# ======================== move_dir_safely ========================


class TestMoveDirSafely:
    def test_rename_dir(self, tmp_path):
        src = tmp_path / "2024"
        (src / "a.jpg").parent.mkdir(parents=True)
        (src / "a.jpg").write_bytes(b"x")
        dest = tmp_path / "2024_media"
        final, status = move_dir_safely(src, dest)
        assert status == "moved"
        assert final == dest
        assert (dest / "a.jpg").exists()
        assert not src.exists()

    def test_dry_run(self, tmp_path):
        src = tmp_path / "2024"
        src.mkdir()
        dest = tmp_path / "2024_media"
        final, status = move_dir_safely(src, dest, dry_run=True)
        assert status == "planned"
        assert src.exists()
        assert not dest.exists()

    def test_error_when_dest_dir_exists(self, tmp_path):
        """При существующем назначении shutil.move унесёт src внутрь dest —
        это ошибка логики вызывающего кода, но функция обязана не терять данные.
        Здесь проверяем, что статус и результат согласованы."""
        src = tmp_path / "2024"
        src.mkdir()
        (src / "a.jpg").write_bytes(b"x")
        dest = tmp_path / "2024_media"
        dest.mkdir()
        final, status = move_dir_safely(src, dest)
        # Либо 'moved' (перемещено внутрь/переименовано), либо 'error' — но src-контент не теряется
        if status == "moved":
            content = list(dest.rglob("a.jpg"))
            assert content, "Содержимое папки не должно теряться"
        else:
            assert src.exists()

    def test_creates_parent_dirs(self, tmp_path):
        src = tmp_path / "2024"
        src.mkdir()
        dest = tmp_path / "deep" / "nested" / "2024_media"
        final, status = move_dir_safely(src, dest)
        assert status == "moved"
        assert dest.exists()
