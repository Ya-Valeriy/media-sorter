"""
Тесты обновления окна после сортировки и скрытия консоли.

Проверяется:
1. «Обновить» чистит поля и лог, но НЕ удаляет отчёт и логи с диска.
2. «Обновить» не срабатывает, пока идёт сортировка.
3. Кнопки последнего прогона включаются/выключаются по наличию файлов.
4. hide_console_window безопасно работает вне Windows.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip('tkinter')

import launcher as launcher_module  # noqa: E402
from launcher import LauncherApp, hide_console_window  # noqa: E402


class FakeLog:
    """Минимальная замена ScrolledText: запоминает содержимое."""

    def __init__(self):
        self.content = ''
        self.state_value = 'normal'

    def config(self, **kwargs):
        if 'state' in kwargs:
            self.state_value = kwargs['state']

    def delete(self, *args):
        self.content = ''

    def insert(self, index, text):
        self.content += text

    def see(self, index):
        pass


def make_app(process=None):
    """Создаёт LauncherApp без реального Tk-окна."""
    app = LauncherApp.__new__(LauncherApp)
    app.process = process
    app.source_var = MagicMock()
    app.dest_var = MagicMock()
    app.log_text = FakeLog()
    app.progress = MagicMock()
    app.run_button = MagicMock()
    app.refresh_button = MagicMock()
    app.report_button = MagicMock()
    app.dest_button = MagicMock()
    app.last_report = None
    app.last_dest = None
    app.config = {}
    return app


class TestRefreshAfterSort:
    def test_clears_paths_and_log(self, tmp_path):
        app = make_app()
        app.log_text.content = 'старый вывод сортировки'

        app._refresh_after_sort()

        app.source_var.set.assert_called_with('')
        app.dest_var.set.assert_called_with('')
        assert 'Окно обновлено' in app.log_text.content

    def test_does_not_delete_files_on_disk(self, tmp_path):
        """Ключевое отличие от «Сбросить всё»: отчёт остаётся."""
        report = tmp_path / 'report.csv'
        report.write_text('данные', encoding='utf-8')
        log = tmp_path / 'sort_media.log'
        log.write_text('лог', encoding='utf-8')

        app = make_app()
        app.last_report = report

        app._refresh_after_sort()

        assert report.exists(), 'отчёт удалён — так быть не должно'
        assert log.exists()

    def test_enables_report_button_when_report_exists(self, tmp_path):
        report = tmp_path / 'report.csv'
        report.write_text('x', encoding='utf-8')

        app = make_app()
        app.last_report = report
        app.report_button.reset_mock()

        app._refresh_after_sort()

        app.report_button.config.assert_called_with(state='normal')

    def test_disables_report_button_when_missing(self):
        app = make_app()
        app.last_report = None
        app.report_button.reset_mock()

        app._refresh_after_sort()

        app.report_button.config.assert_called_with(state='disabled')

    def test_refuses_while_sorting(self):
        """Во время сортировки обновление блокируется."""
        running = MagicMock()
        running.poll.return_value = None  # процесс жив

        app = make_app(process=running)

        with patch.object(launcher_module.messagebox, 'showinfo') as info:
            app._refresh_after_sort()

        info.assert_called_once()
        app.source_var.set.assert_not_called()
        assert 'Окно обновлено' not in app.log_text.content

    def test_works_after_process_finished(self, tmp_path):
        finished = MagicMock()
        finished.poll.return_value = 0  # процесс завершён

        app = make_app(process=finished)
        app._refresh_after_sort()

        assert app.process is None
        app.source_var.set.assert_called_with('')

    def test_resets_progress(self):
        app = make_app()
        app._refresh_after_sort()

        app.progress.stop.assert_called_once()
        app.progress.__setitem__.assert_called_with('value', 0)

    def test_run_button_enabled(self):
        app = make_app()
        app.run_button.reset_mock()
        app._refresh_after_sort()
        app.run_button.config.assert_called_with(state='normal')


class TestHideConsole:
    def test_safe_on_non_windows(self):
        """Вне Windows функция просто возвращает False."""
        with patch.object(launcher_module.sys, 'platform', 'linux'):
            assert hide_console_window() is False

    def test_no_console_no_crash(self):
        """Отсутствие консоли не должно ломать запуск."""
        result = hide_console_window()
        assert isinstance(result, bool)

    def test_function_exists_in_main(self):
        """main() обязан прятать консоль до создания окна."""
        import inspect

        source = inspect.getsource(launcher_module.main)
        assert 'hide_console_window()' in source
        # именно до tk.Tk(), иначе окно успеет появиться с консолью
        assert source.index('hide_console_window()') < source.index('tk.Tk()')
