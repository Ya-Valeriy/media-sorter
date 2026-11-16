"""
Тесты портативного запуска и безопасности кнопки «Сбросить всё».

Проверяется главное:
1. Сброс НИКОГДА не удаляет каталоги — в python/ лежит интерпретатор.
2. Лаунчер находит портативный Python в папке проекта.
3. Служебные временные файлы всё-таки удаляются.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# launcher импортирует tkinter — пропускаем тесты только если его нет вообще
pytest.importorskip('tkinter')

from launcher import (  # noqa: E402
    PROTECTED_DIRS,
    TEMP_FILE_NAMES,
    LauncherApp,
)


class TestCleanDirSafety:
    """Сброс не должен уничтожать портативный Python и исходники."""

    def test_does_not_delete_directories(self, tmp_path):
        (tmp_path / 'python').mkdir()
        (tmp_path / 'python' / 'python.exe').write_bytes(b'MZ')
        (tmp_path / 'media_sorter').mkdir()
        (tmp_path / 'media_sorter' / 'main.py').write_text('code')
        (tmp_path / 'assets').mkdir()
        (tmp_path / 'assets' / 'background.png').write_bytes(b'PNG')

        LauncherApp._clean_dir(tmp_path, only=TEMP_FILE_NAMES)

        assert (tmp_path / 'python' / 'python.exe').exists(), 'интерпретатор удалён!'
        assert (tmp_path / 'media_sorter' / 'main.py').exists()
        assert (tmp_path / 'assets' / 'background.png').exists()

    def test_removes_only_known_temp_files(self, tmp_path):
        (tmp_path / 'report.csv').write_text('x')
        (tmp_path / 'sort_media.log').write_text('x')
        (tmp_path / 'important.txt').write_text('не трогать')
        (tmp_path / 'launcher.py').write_text('код')

        removed = LauncherApp._clean_dir(tmp_path, only=TEMP_FILE_NAMES)

        assert removed == 2
        assert not (tmp_path / 'report.csv').exists()
        assert not (tmp_path / 'sort_media.log').exists()
        assert (tmp_path / 'important.txt').exists()
        assert (tmp_path / 'launcher.py').exists()

    def test_keep_list_respected(self, tmp_path):
        (tmp_path / 'launcher.log').write_text('лог')
        (tmp_path / 'errors.log').write_text('ошибки')

        LauncherApp._clean_dir(tmp_path, only=TEMP_FILE_NAMES, keep={'launcher.log'})

        assert (tmp_path / 'launcher.log').exists()
        assert not (tmp_path / 'errors.log').exists()

    def test_nonexistent_dir_is_safe(self, tmp_path):
        assert LauncherApp._clean_dir(tmp_path / 'нет_такой') == 0

    def test_protected_names_cover_python(self):
        assert 'python' in PROTECTED_DIRS
        assert 'assets' in PROTECTED_DIRS
        assert 'media_sorter' in PROTECTED_DIRS


class TestPortablePythonDetection:
    """Лаунчер находит python\\python.exe до системного интерпретатора."""

    def _make_app(self, tmp_path, monkeypatch):
        import launcher as launcher_module

        config = {'python_path': '', 'script_path': str(tmp_path / 'sort_media.py')}
        app = LauncherApp.__new__(LauncherApp)
        app.config = config
        monkeypatch.setattr(launcher_module, 'get_base_dir', lambda: tmp_path)
        return app

    def test_finds_portable_python(self, tmp_path, monkeypatch):
        portable = tmp_path / 'python' / 'python.exe'
        portable.parent.mkdir()
        portable.write_bytes(b'MZ')

        app = self._make_app(tmp_path, monkeypatch)
        found = app._resolve_python_path()

        assert found == portable, f'ожидался портативный, получен {found}'

    def test_config_wins_over_portable(self, tmp_path, monkeypatch):
        portable = tmp_path / 'python' / 'python.exe'
        portable.parent.mkdir()
        portable.write_bytes(b'MZ')
        custom = tmp_path / 'my_python' / 'python.exe'
        custom.parent.mkdir()
        custom.write_bytes(b'MZ')

        app = self._make_app(tmp_path, monkeypatch)
        app.config['python_path'] = str(custom)

        assert app._resolve_python_path() == custom

    def test_falls_back_to_current_interpreter(self, tmp_path, monkeypatch):
        """Без портативного Python берётся текущий интерпретатор."""
        app = self._make_app(tmp_path, monkeypatch)
        found = app._resolve_python_path()

        assert found is not None
        assert found.name.lower() in ('python.exe', 'python', 'python3')
