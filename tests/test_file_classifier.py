"""
Unit-тесты для модуля file_classifier: классификация файлов по расширению.
"""

from pathlib import Path

from renamer.file_classifier import (
    TYPE_IMAGE,
    TYPE_OTHER,
    TYPE_VIDEO,
    classify_file,
    parse_extensions,
)


def test_classify_image():
    assert classify_file(Path('IMG_001.jpg')) == TYPE_IMAGE
    assert classify_file(Path('IMG_001.JPEG')) == TYPE_IMAGE
    assert classify_file(Path('IMG_001.CR2')) == TYPE_IMAGE
    assert classify_file(Path('photo.heic')) == TYPE_IMAGE
    assert classify_file(Path('scan.png')) == TYPE_IMAGE
    assert classify_file(Path('pic.webp')) == TYPE_IMAGE


def test_classify_video():
    assert classify_file(Path('VID_001.mp4')) == TYPE_VIDEO
    assert classify_file(Path('clip.MOV')) == TYPE_VIDEO
    assert classify_file(Path('video.m2ts')) == TYPE_VIDEO
    assert classify_file(Path('film.avi')) == TYPE_VIDEO
    assert classify_file(Path('movie.webm')) == TYPE_VIDEO


def test_classify_other():
    assert classify_file(Path('notes.txt')) == TYPE_OTHER
    assert classify_file(Path('photo.xmp')) == TYPE_OTHER
    assert classify_file(Path('archive.json')) == TYPE_OTHER
    assert classify_file(Path('doc.pdf')) == TYPE_OTHER
    assert classify_file(Path('no_extension')) == TYPE_OTHER


def test_parse_extensions():
    exts = parse_extensions('jpg, png, .mp4')
    assert exts == frozenset({'.jpg', '.png', '.mp4'})


def test_parse_extensions_empty():
    assert parse_extensions('') == frozenset()