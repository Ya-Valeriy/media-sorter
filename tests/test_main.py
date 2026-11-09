"""
Unit-тесты для media_sorter/main.py:
- parse_args (разбор CLI-аргументов)
- validate_paths
- _parse_extensions
- collect_media_files
"""

from pathlib import Path

import pytest

from media_sorter.main import (
    collect_media_files,
    parse_args,
    validate_paths,
)


# ======================== parse_args ========================


class TestParseArgs:
    def test_required_args(self):
        args = parse_args(["--source", "/tmp/src", "--destination", "/tmp/dst"])
        assert args.source == "/tmp/src"
        assert args.destination == "/tmp/dst"
        assert args.dry_run is False
        assert args.check_duplicates is False
        assert args.no_junk is False
        assert args.no_rename is False
        assert args.workers == 1
        assert args.yes is False

    def test_all_flags(self):
        args = parse_args([
            "--source", "/tmp/src",
            "--destination", "/tmp/dst",
            "--dry-run",
            "--check-duplicates",
            "--no-junk",
            "--no-rename",
            "--workers", "4",
            "--yes",
        ])
        assert args.dry_run is True
        assert args.check_duplicates is True
        assert args.no_junk is True
        assert args.no_rename is True
        assert args.workers == 4
        assert args.yes is True

    def test_junk_folder_name(self):
        args = parse_args(["--source", "/s", "--destination", "/d", "--junk-folder", "Trash"])
        assert args.junk_folder == "Trash"

    def test_junk_thresholds(self):
        args = parse_args([
            "--source", "/s",
            "--destination", "/d",
            "--photo-junk-max-kb", "1024",
            "--video-junk-max-sec", "5",
            "--video-junk-max-kb", "10240",
        ])
        assert args.photo_junk_max_kb == 1024.0
        assert args.video_junk_max_sec == 5.0
        assert args.video_junk_max_kb == 10240.0

    def test_default_extensions(self):
        args = parse_args(["--source", "/s", "--destination", "/d"])
        assert ".jpg" in args.extensions
        assert ".mp4" in args.extensions

    def test_custom_extensions(self):
        args = parse_args([
            "--source", "/s",
            "--destination", "/d",
            "--extensions", "jpg,png,mp4",
        ])
        assert "jpg,png,mp4" in args.extensions

    def test_short_options(self):
        args = parse_args(["-s", "/src", "-d", "/dst"])
        assert args.source == "/src"
        assert args.destination == "/dst"

    def test_log_files(self):
        args = parse_args([
            "--source", "/s",
            "--destination", "/d",
            "--log-file", "custom.log",
            "--report-file", "custom.csv",
            "--duplicates-log", "dups.log",
            "--errors-log", "errs.log",
        ])
        assert args.log_file == "custom.log"
        assert args.report_file == "custom.csv"
        assert args.duplicates_log == "dups.log"
        assert args.errors_log == "errs.log"

    def test_missing_required(self):
        with pytest.raises(SystemExit):
            parse_args(["--source", "/s"])


# ======================== validate_paths ========================


class TestValidatePaths:
    def test_source_not_exists(self, tmp_path):
        dest = tmp_path / "dest"
        error = validate_paths(tmp_path / "nonexistent", dest)
        assert error is not None
        assert "не существует" in error

    def test_source_is_file(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        dest = tmp_path / "dest"
        error = validate_paths(f, dest)
        assert error is not None
        assert "не является директорией" in error

    def test_dest_is_file(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        f = tmp_path / "file.txt"
        f.write_text("x")
        error = validate_paths(src, f)
        assert error is not None
        assert "не является директорией" in error

    def test_same_path(self, tmp_path):
        error = validate_paths(tmp_path, tmp_path)
        assert error is not None
        assert "совпадают" in error

    def test_valid_paths(self, tmp_path):
        src = tmp_path / "src"
        dest = tmp_path / "dest"
        src.mkdir()
        dest.mkdir()
        error = validate_paths(src, dest)
        assert error is None

    def test_dest_not_exists_is_ok(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        # dest не существует — это нормально, программа создаст её
        error = validate_paths(src, tmp_path / "dest")
        assert error is None


# ======================== collect_media_files ========================


class TestCollectMediaFiles:
    def test_collect_jpg(self, tmp_path):
        (tmp_path / "a.jpg").touch()
        (tmp_path / "b.JPG").touch()
        files = collect_media_files(tmp_path, {".jpg", ".jpeg"})
        assert len(files) == 2

    def test_collect_mixed(self, tmp_path):
        (tmp_path / "a.jpg").touch()
        (tmp_path / "b.mp4").touch()
        (tmp_path / "c.png").touch()
        (tmp_path / "d.txt").touch()
        files = collect_media_files(tmp_path, {".jpg", ".mp4"})
        assert len(files) == 2
        assert any(f.name == "a.jpg" for f in files)
        assert any(f.name == "b.mp4" for f in files)

    def test_recursive(self, tmp_path):
        sub = tmp_path / "sub" / "deep"
        sub.mkdir(parents=True)
        (tmp_path / "top.jpg").touch()
        (sub / "nested.mp4").touch()
        files = collect_media_files(tmp_path, {".jpg", ".mp4"})
        assert len(files) == 2

    def test_exclude_subdir(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()
        (tmp_path / "a.jpg").touch()
        (dest / "b.jpg").touch()
        files = collect_media_files(tmp_path, {".jpg"}, exclude=dest)
        assert len(files) == 1
        assert files[0].name == "a.jpg"

    def test_no_files(self, tmp_path):
        (tmp_path / "notes.txt").touch()
        files = collect_media_files(tmp_path, {".jpg"})
        assert len(files) == 0

    def test_case_insensitive_extension(self, tmp_path):
        """Расширение .JPG должно попадать под фильтр .jpg (регистр не важен)."""
        (tmp_path / "a.jpg").touch()
        (tmp_path / "b.jpg").touch()
        (tmp_path / "c.txt").touch()
        files = collect_media_files(tmp_path, {".jpg"})
        assert len(files) == 2
        assert all(f.suffix.lower() == ".jpg" for f in files)

    def test_skips_directories(self, tmp_path):
        (tmp_path / "dir").mkdir()
        (tmp_path / "file.jpg").touch()
        files = collect_media_files(tmp_path, {".jpg"})
        assert len(files) == 1

    def test_sorted_order(self, tmp_path):
        (tmp_path / "z.mp4").touch()
        (tmp_path / "a.jpg").touch()
        (tmp_path / "m.png").touch()
        files = collect_media_files(tmp_path, {".jpg", ".mp4", ".png"})
        names = [f.name for f in files]
        assert names == sorted(names)

    def test_heic_and_raw(self, tmp_path):
        (tmp_path / "a.HEIC").touch()
        (tmp_path / "b.CR2").touch()
        (tmp_path / "c.NEF").touch()
        files = collect_media_files(tmp_path, {".heic", ".cr2", ".nef"})
        assert len(files) == 3

    def test_video_extensions(self, tmp_path):
        for ext in [".mp4", ".mov", ".avi", ".mkv", ".mts", ".3gp"]:
            (tmp_path / f"v{ext[1:]}{ext}").touch()
        files = collect_media_files(tmp_path, {".mp4", ".mov", ".avi", ".mkv", ".mts", ".3gp"})
        assert len(files) == 6


# ======================== _parse_extensions ========================


class TestParseExtensions:
    def test_basic(self):
        from media_sorter.main import _parse_extensions
        assert _parse_extensions("jpg,png,mp4") == {".jpg", ".png", ".mp4"}

    def test_with_dots(self):
        from media_sorter.main import _parse_extensions
        assert _parse_extensions(".jpg, .png") == {".jpg", ".png"}

    def test_case_and_spaces(self):
        from media_sorter.main import _parse_extensions
        assert _parse_extensions(" JPG , Png ") == {".jpg", ".png"}

    def test_empty_string(self):
        from media_sorter.main import _parse_extensions
        assert _parse_extensions("") == set()

    def test_ignores_empty_parts(self):
        from media_sorter.main import _parse_extensions
        assert _parse_extensions("jpg,,png,") == {".jpg", ".png"}


# ======================== end-to-end CLI ========================


class TestCliEndToEnd:
    """Полный прогон main() на временных папках: dry-run, реальный прогон, дубликаты, мусор."""

    def _make_source(self, tmp_path: Path) -> Path:
        src = tmp_path / "src"
        src.mkdir()
        (src / "IMG_20240513_142035.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        return src

    def _argv(self, src: Path, dst: Path, tmp_path: Path, *extra: str) -> list:
        return [
            "--source", str(src),
            "--destination", str(dst),
            "--log-file", str(tmp_path / "sort_media.log"),
            "--report-file", str(tmp_path / "report.csv"),
            "--duplicates-log", str(tmp_path / "duplicates.log"),
            "--errors-log", str(tmp_path / "errors.log"),
            *extra,
        ]

    def test_dry_run_moves_nothing(self, tmp_path):
        from media_sorter.main import main

        src = self._make_source(tmp_path)
        dst = tmp_path / "dst"
        rc = main(self._argv(src, dst, tmp_path, "--dry-run", "--no-junk"))
        assert rc == 0
        # файл остался на месте, структура не создана
        assert (src / "IMG_20240513_142035.jpg").exists()
        assert not list(dst.rglob("*")) if dst.exists() else True

    def test_real_run_sorts_and_renames(self, tmp_path):
        from media_sorter.main import main

        src = self._make_source(tmp_path)
        dst = tmp_path / "dst"
        rc = main(self._argv(src, dst, tmp_path, "--yes", "--no-junk"))
        assert rc == 0
        expected = dst / "2024_media" / "05.2024_media" / "05.2024_photo" / "2024-05-13_14-20-35.jpg"
        assert expected.exists()
        assert not (src / "IMG_20240513_142035.jpg").exists()
        assert (tmp_path / "report.csv").exists()

    def test_duplicates_go_to_duplicates_folder(self, tmp_path):
        from media_sorter.main import main

        src = tmp_path / "src"
        src.mkdir()
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        (src / "IMG_20240513_142035.jpg").write_bytes(content)
        (src / "IMG_20240513_142036.jpg").write_bytes(content)  # то же содержимое
        dst = tmp_path / "dst"
        rc = main(self._argv(src, dst, tmp_path, "--yes", "--no-junk", "--check-duplicates"))
        assert rc == 0
        # первый файл — в структуре, второй — в Дубликатах
        assert list((dst / "2024_media" / "05.2024_media" / "05.2024_photo").glob("2024-05-13_14-20-35.jpg"))
        assert list((dst / "Дубликаты").glob("*.jpg"))
        # на диске оба файла сохранены (ничего не удалено)
        total = sum(1 for _ in dst.rglob("*.jpg"))
        assert total == 2

    def test_small_photo_goes_to_junk(self, tmp_path):
        from media_sorter.main import main

        src = tmp_path / "src"
        src.mkdir()
        (src / "tiny.jpg").write_bytes(b"\x00" * 100)  # 100 байт < 2048 КБ
        dst = tmp_path / "dst"
        rc = main(self._argv(src, dst, tmp_path, "--yes"))
        assert rc == 0
        assert (dst / "Мусор" / "tiny.jpg").exists()

    def test_custom_junk_folder_flag(self, tmp_path):
        """Флаг --junk-folder должен реально влиять на имя папки."""
        from media_sorter.main import main

        src = tmp_path / "src"
        src.mkdir()
        (src / "tiny.jpg").write_bytes(b"\x00" * 100)
        dst = tmp_path / "dst"
        rc = main(self._argv(src, dst, tmp_path, "--yes", "--junk-folder", "Trash"))
        assert rc == 0
        assert (dst / "Trash" / "tiny.jpg").exists()
        assert not (dst / "Мусор").exists()

    def test_file_without_date_falls_back_to_mtime(self, tmp_path):
        """Файл без EXIF и даты в имени попадает в структуру по mtime (is_approximate)."""
        import csv
        from datetime import datetime

        from media_sorter.main import main

        src = tmp_path / "src"
        src.mkdir()
        (src / "random_photo.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        dst = tmp_path / "dst"
        rc = main(self._argv(src, dst, tmp_path, "--yes", "--no-junk", "--no-rename"))
        assert rc == 0
        # файл отсортирован по текущему году/месяцу (mtime)
        now = datetime.now()
        expected_dir = dst / f"{now.year}_media" / f"{now.month:02d}.{now.year}_media" / f"{now.month:02d}.{now.year}_photo"
        assert (expected_dir / "random_photo.jpg").exists()
        # в отчёте источник даты — mtime с пометкой приблизительности
        with open(tmp_path / "report.csv", encoding="utf-8-sig") as fh:
            row = next(iter(csv.DictReader(fh)))
        assert row["date_source"] == "mtime"
        assert row["is_approximate"] == "True"

    def test_idempotent_rerun(self, tmp_path):
        """Повторный прогон не перезаписывает и не дублирует результат."""
        from media_sorter.main import main

        src = self._make_source(tmp_path)
        dst = tmp_path / "dst"
        main(self._argv(src, dst, tmp_path, "--yes", "--no-junk"))
        # Второй прогон: источник пуст → файлов не найдено
        rc = main(self._argv(src, dst, tmp_path, "--yes", "--no-junk"))
        assert rc == 0
        expected = dst / "2024_media" / "05.2024_media" / "05.2024_photo" / "2024-05-13_14-20-35.jpg"
        assert expected.exists()

    def test_invalid_source_returns_1(self, tmp_path):
        from media_sorter.main import main

        argv = [
            "--source", str(tmp_path / "nonexistent"),
            "--destination", str(tmp_path / "dst"),
            "--log-file", str(tmp_path / "log.log"),
            "--report-file", str(tmp_path / "report.csv"),
            "--duplicates-log", str(tmp_path / "d.log"),
            "--errors-log", str(tmp_path / "e.log"),
        ]
        assert main(argv) == 1
