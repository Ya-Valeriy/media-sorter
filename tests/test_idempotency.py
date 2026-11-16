"""
Повторный прогон не должен пересортировывать уже разложенные файлы
из служебных папок (Мусор, Дубликаты, Негативы, Дата_не_определена).
"""

from __future__ import annotations

from media_sorter.date_extractor import SUPPORTED_EXTENSIONS
from media_sorter.main import collect_media_files, main
from media_sorter.mover import (
    FOLDER_DUPLICATES,
    FOLDER_JUNK,
    FOLDER_NEGATIVES,
    FOLDER_UNDEFINED,
    SERVICE_FOLDER_NAMES,
)


def test_service_folder_set_is_complete():
    assert {FOLDER_JUNK, FOLDER_DUPLICATES, FOLDER_NEGATIVES, FOLDER_UNDEFINED} <= SERVICE_FOLDER_NAMES


def test_collect_skips_service_folders(tmp_path):
    (tmp_path / '2024_media' / '05.2024_media' / '05.2024_photo').mkdir(parents=True)
    (tmp_path / '2024_media' / '05.2024_media' / '05.2024_photo' / 'a.jpg').write_bytes(b'x')
    for folder, name in ((FOLDER_JUNK, 'tiny.jpg'), (FOLDER_DUPLICATES, 'dup.jpg'),
                         (FOLDER_NEGATIVES, 'scan.nef')):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / name).write_bytes(b'y')

    found = collect_media_files(tmp_path, set(SUPPORTED_EXTENSIONS))
    assert {p.name for p in found} == {'a.jpg'}


def test_skip_can_be_disabled(tmp_path):
    (tmp_path / FOLDER_JUNK).mkdir()
    (tmp_path / FOLDER_JUNK / 'tiny.jpg').write_bytes(b'y')
    found = collect_media_files(tmp_path, set(SUPPORTED_EXTENSIONS), skip_service_folders=False)
    assert {p.name for p in found} == {'tiny.jpg'}


def test_nested_service_folder_skipped(tmp_path):
    deep = tmp_path / '2024_media' / '05.2024_media' / '05.2024_raw' / FOLDER_JUNK
    deep.mkdir(parents=True)
    (deep / 'x.nef').write_bytes(b'x')
    (tmp_path / '2024_media' / '05.2024_media' / '05.2024_raw' / 'ok.nef').write_bytes(b'o')
    found = collect_media_files(tmp_path, set(SUPPORTED_EXTENSIONS))
    assert {p.name for p in found} == {'ok.nef'}


def _argv(src, dst, tmp_path, *extra):
    return ['--source', str(src), '--destination', str(dst),
            '--log-file', str(tmp_path / 'sort.log'),
            '--report-file', str(tmp_path / 'report.csv'),
            '--duplicates-log', str(tmp_path / 'dup.log'),
            '--errors-log', str(tmp_path / 'err.log'), *extra]


def test_second_run_is_stable(tmp_path):
    src, dst = tmp_path / 'src', tmp_path / 'dst'
    src.mkdir()
    (src / 'IMG_20240513_142035.jpg').write_bytes(b'first-run')
    argv = _argv(src, dst, tmp_path, '--yes', '--no-junk')
    assert main(argv) == 0
    first = sorted(str(p.relative_to(dst)) for p in dst.rglob('*') if p.is_file())
    assert main(argv) == 0
    second = sorted(str(p.relative_to(dst)) for p in dst.rglob('*') if p.is_file())
    assert first == second and len(first) == 1


def test_destination_inside_source_not_resorted(tmp_path):
    src = tmp_path / 'src'
    dst = src / 'sorted'
    src.mkdir()
    (src / 'IMG_20240513_142035.jpg').write_bytes(b'content')
    argv = _argv(src, dst, tmp_path, '--yes', '--no-junk')
    assert main(argv) == 0
    count_first = len([p for p in dst.rglob('*') if p.is_file()])
    assert main(argv) == 0
    assert len([p for p in dst.rglob('*') if p.is_file()]) == count_first
