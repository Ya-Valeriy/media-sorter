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
