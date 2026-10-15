"""
GUI-обёртка для запуска sort_media.py.

Позволяет выбрать папку с медиафайлами, настроить флаги сортировки
и запустить sort_media.py, не используя командную строку.

Запуск:
    python launcher.py
"""

from __future__ import annotations

import logging
import os
import platform
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any, Dict, List, Optional

from launcher_common import (
    APP_TITLE,
    CONFIG_FILE,
    LOG_FILE,
    get_base_dir,
    get_logs_dir,
    get_reports_dir,
    get_src_dir,
    load_config,
    open_path,
    save_config,
)

logger = logging.getLogger(__name__)

# Размеры окна
WINDOW_WIDTH: int = 500
WINDOW_HEIGHT: int = 330


class LauncherApp:
    """Главное окно приложения-лаунчера."""

    def __init__(self, root: tk.Tk, config: Dict[str, Any]) -> None:
        self.root = root
        self.config = config
        self.output_queue: queue.Queue[Optional[str]] = queue.Queue()
        self.process: Optional[subprocess.Popen] = None
        self.last_report: Optional[Path] = None
        self.last_dest: Optional[Path] = None

        self._build_ui()
        self._center_window(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.after(100, self._poll_output)

    # --- Построение интерфейса ---

    def _build_ui(self) -> None:
        """Создаёт элементы интерфейса."""
        self.root.title(APP_TITLE)
        self.root.resizable(False, False)

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # Папка с медиафайлами
        ttk.Label(main, text='Папка с медиафайлами:').grid(row=0, column=0, sticky=tk.W)
        self.source_var = tk.StringVar(value=self.config.get('last_source', ''))
        ttk.Entry(main, textvariable=self.source_var, state='readonly', width=38).grid(
            row=1, column=0, sticky=tk.EW, padx=(0, 5),
        )
        ttk.Button(main, text='Обзор...', command=self._browse_source).grid(row=1, column=1)

        # Папка назначения
        ttk.Label(main, text='Папка назначения:').grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        self.dest_var = tk.StringVar(value=self.config.get('default_destination', ''))
        ttk.Entry(main, textvariable=self.dest_var, width=38).grid(
            row=3, column=0, sticky=tk.EW, padx=(0, 5),
        )
        ttk.Button(main, text='Обзор...', command=self._browse_dest).grid(row=3, column=1)

        # Флаги
        flags = self.config.get('default_flags', {})
        self.dry_run_var = tk.BooleanVar(value=bool(flags.get('dry_run_default', False)))
        self.duplicates_var = tk.BooleanVar(value=bool(flags.get('check_duplicates', True)))
        self.junk_var = tk.BooleanVar(value=bool(flags.get('junk_folder', True)))
        ttk.Checkbutton(main, text='Пробный прогон (dry-run)', variable=self.dry_run_var).grid(
            row=4, column=0, columnspan=2, sticky=tk.W, pady=(8, 0),
        )
        ttk.Checkbutton(main, text='Проверять дубликаты', variable=self.duplicates_var).grid(
            row=5, column=0, columnspan=2, sticky=tk.W,
        )
        ttk.Checkbutton(main, text='Мелкие файлы в Мусор', variable=self.junk_var).grid(
            row=6, column=0, columnspan=2, sticky=tk.W,
        )

        # Кнопки
        buttons = ttk.Frame(main)
        buttons.grid(row=7, column=0, columnspan=2, sticky=tk.EW, pady=(10, 0))
        self.run_button = ttk.Button(buttons, text='Запустить', command=self._start_sorting)
        self.run_button.pack(side=tk.LEFT)
        ttk.Button(buttons, text='Отмена', command=self._on_close).pack(side=tk.LEFT, padx=(5, 0))
        self.report_button = ttk.Button(buttons, text='Открыть отчёт', command=self._open_report, state=tk.DISABLED)
        self.report_button.pack(side=tk.LEFT, padx=(5, 0))
        self.dest_button = ttk.Button(buttons, text='Открыть папку', command=self._open_dest, state=tk.DISABLED)
        self.dest_button.pack(side=tk.LEFT, padx=(5, 0))

        # Прогресс
        self.progress = ttk.Progressbar(main, mode='indeterminate')
        self.progress.grid(row=8, column=0, columnspan=2, sticky=tk.EW, pady=(10, 0))

        # Лог
        self.log_text = scrolledtext.ScrolledText(
            main, height=5, state=tk.DISABLED, font=('Consolas', 9),
        )
        self.log_text.grid(row=9, column=0, columnspan=2, sticky=tk.NSEW, pady=(8, 0))

        main.columnconfigure(0, weight=1)
        main.rowconfigure(9, weight=1)

    def _center_window(self, width: int, height: int) -> None:
        """Размещает окно по центру экрана."""
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    # --- Обработчики выбора папок ---

    def _browse_source(self) -> None:
        """Открывает диалог выбора папки-источника."""
        initial = self.source_var.get() or str(Path.home())
        folder = filedialog.askdirectory(
            title='Выберите папку с медиафайлами для сортировки',
            initialdir=initial,
        )
        if folder:
            self.source_var.set(folder)
            # Если папка назначения не задана — предлагаем соседнюю «Sorted»
            if not self.dest_var.get().strip():
                self.dest_var.set(str(Path(folder).parent / 'Sorted'))
            logger.info('Выбрана папка-источник: %s', folder)

    def _browse_dest(self) -> None:
        """Открывает диалог выбора папки-назначения."""
        initial = self.dest_var.get() or str(Path.home())
        folder = filedialog.askdirectory(title='Выберите папку назначения', initialdir=initial)
        if folder:
            self.dest_var.set(folder)
            logger.info('Выбрана папка-назначения: %s', folder)

    # --- Запуск сортировки ---

    def _start_sorting(self) -> None:
        """Проверяет ввод и запускает sort_media.py в фоновом потоке."""
        source = Path(self.source_var.get().strip())
        dest = Path(self.dest_var.get().strip())

        # Валидация
        if not source.exists() or not source.is_dir():
            messagebox.showerror('Ошибка', f'Папка-источник не существует:\n{source}')
            return
        if not any(source.iterdir()):
            messagebox.showerror('Ошибка', f'Папка-источник пуста:\n{source}')
            return
        if not str(dest):
            messagebox.showerror('Ошибка', 'Укажите папку назначения.')
            return

        script_path = self._resolve_script_path()
        if script_path is None:
            return
        python_path = self._resolve_python_path()
        if python_path is None:
            return

        # Сохраняем последние пути в конфиг
        self.config['last_source'] = str(source)
        self.config['default_destination'] = str(dest)
        save_config(self.config)

        # Папки для отчётов и логов (в portable-режиме — reports/ и logs/)
        reports_dir = get_reports_dir()
        logs_dir = get_logs_dir()
        reports_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Собираем команду
        cmd = [
            str(python_path), str(script_path),
            '--source', str(source),
            '--destination', str(dest),
            '--report-file', str(reports_dir / 'report.csv'),
            '--log-file', str(logs_dir / 'sort_media.log'),
            '--duplicates-log', str(logs_dir / 'duplicates.log'),
            '--errors-log', str(logs_dir / 'errors.log'),
            '--yes',
        ]
        if self.dry_run_var.get():
            cmd.append('--dry-run')
        if self.duplicates_var.get():
            cmd.append('--check-duplicates')
        if not self.junk_var.get():
            cmd.append('--no-junk')

        self._append_log(f'>>> Запуск: {" ".join(cmd)}\n')
        logger.info('Запуск: %s', ' '.join(cmd))

        self.run_button.config(state=tk.DISABLED)
        self.report_button.config(state=tk.DISABLED)
        self.dest_button.config(state=tk.DISABLED)
        self.progress.start(12)

        self.last_report = reports_dir / 'report.csv'
        self.last_dest = dest

        thread = threading.Thread(target=self._run_subprocess, args=(cmd,), daemon=True)
        thread.start()

    def _resolve_script_path(self) -> Optional[Path]:
        """Определяет путь к sort_media.py (из конфига, src/ или рядом с launcher)."""
        configured = self.config.get('script_path', '')
        candidates: List[Path] = []
        if configured:
            path = Path(configured)
            candidates.append(path if path.is_absolute() else get_base_dir() / path)
        candidates.append(get_src_dir() / 'sort_media.py')
        candidates.append(get_base_dir() / 'sort_media.py')
        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate
        answer = messagebox.askyesno(
            'sort_media.py не найден',
            'Скрипт sort_media.py не найден. Указать путь вручную?',
        )
        if answer:
            selected = filedialog.askopenfilename(
                title='Укажите sort_media.py',
                filetypes=[('Python-скрипт', '*.py')],
                initialdir=str(get_base_dir()),
            )
            if selected:
                self.config['script_path'] = selected
                save_config(self.config)
                return Path(selected)
        return None

    def _resolve_python_path(self) -> Optional[Path]:
        """
        Определяет путь к интерпретатору Python.

        Пустое значение python_path в конфиге пропускается
        (Path('') == Path('.') — текущая директория, её нельзя запускать).
        """
        configured = self.config.get('python_path', '')
        candidates: List[Path] = []
        if configured:
            path = Path(configured)
            candidates.append(path if path.is_absolute() else get_base_dir() / path)
        # Для sort_media.py нужен консольный python.exe (вывод в stdout),
        # а не pythonw.exe — иначе прогресс-бар и логи не будут работать.
        exe = Path(sys.executable)
        if exe.name.lower() == 'pythonw.exe':
            exe = exe.with_name('python.exe')
        candidates.append(exe)
        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate
        messagebox.showerror('Ошибка', 'Интерпретатор Python не найден.')
        return None

    def _run_subprocess(self, cmd: List[str]) -> None:
        """Запускает sort_media.py и читает его вывод (в фоновом потоке)."""
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=env,
                cwd=str(get_base_dir()),
                # Не показывать окно консоли для sort_media.py (Windows)
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
            )
            self.process = proc
            assert proc.stdout is not None

            # Читаем вывод в отдельном потоке: если дочерние процессы
            # удерживают pipe открытым, чтение не должно блокировать
            # ожидание завершения процесса.
            def _read_output() -> None:
                try:
                    for line in proc.stdout:
                        self.output_queue.put(line.rstrip('\n'))
                except (OSError, ValueError):
                    pass  # pipe закрыт после завершения процесса

            reader = threading.Thread(target=_read_output, daemon=True)
            reader.start()

            # Ждём завершения процесса (с запасом на большие архивы)
            try:
                proc.wait(timeout=3600)
            except subprocess.TimeoutExpired:
                logger.warning('sort_media.py не завершился за 1 час — принудительное завершение.')
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()

            # Процесс завершён: закрываем pipe, чтобы разблокировать чтение
            try:
                proc.stdout.close()
            except OSError:
                pass
            reader.join(timeout=5)
            self.output_queue.put(None)  # сигнал завершения
        except Exception as exc:  # noqa: BLE001 — поток не должен умирать молча
            logger.exception('Ошибка запуска sort_media.py')
            self.output_queue.put(f'ОШИБКА: {exc}')
            self.output_queue.put(None)

    def _poll_output(self) -> None:
        """Периодически читает очередь вывода и обновляет UI."""
        try:
            while True:
                line = self.output_queue.get_nowait()
                if line is None:
                    self._on_process_finished()
                    return
                self._append_log(line + '\n')
        except queue.Empty:
            pass
        self.root.after(100, self._poll_output)

    def _on_process_finished(self) -> None:
        """Обрабатывает завершение процесса сортировки."""
        self.progress.stop()
        self.run_button.config(state=tk.NORMAL)
        self.report_button.config(state=tk.NORMAL)
        self.dest_button.config(state=tk.NORMAL)

        returncode = self.process.returncode if self.process else -1
        logger.info('sort_media.py завершился с кодом %d', returncode)

        if returncode == 0:
            messagebox.showinfo(
                'Готово',
                f'Сортировка завершена успешно.\n\n'
                f'Отчёт: {self.last_report}\n'
                f'Папка назначения: {self.last_dest}',
            )
        else:
            messagebox.showerror(
                'Ошибка',
                f'sort_media.py завершился с кодом {returncode}.\n'
                f'Подробности — в логе ниже и в файле {get_base_dir() / LOG_FILE}.',
            )

    # --- Вспомогательные методы ---

    def _append_log(self, text: str) -> None:
        """Добавляет текст в лог-область."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _open_report(self) -> None:
        """Открывает report.csv в приложении по умолчанию."""
        if self.last_report and self.last_report.exists():
            open_path(self.last_report)
        else:
            messagebox.showwarning('Внимание', 'Отчёт не найден.')

    def _open_dest(self) -> None:
        """Открывает папку назначения в проводнике."""
        if self.last_dest and self.last_dest.exists():
            open_path(self.last_dest)
        else:
            messagebox.showwarning('Внимание', 'Папка назначения не найдена.')

    def _on_close(self) -> None:
        """Обрабатывает закрытие окна: завершает запущенный процесс."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            logger.info('Процесс sort_media.py завершён пользователем.')
        self.root.destroy()


def _relaunch_with_pythonw() -> None:
    """
    Перезапускает GUI через pythonw.exe, чтобы не открывалось окно консоли.

    Если скрипт запущен консольным python.exe, а рядом есть pythonw.exe
    (безконсольная версия) — перезапускаемся через него и завершаем
    текущий процесс. Окно консоли при этом не появляется.
    """
    if sys.platform != 'win32':
        return
    exe = Path(sys.executable)
    if exe.name.lower() != 'python.exe':
        return
    pythonw = exe.with_name('pythonw.exe')
    if not pythonw.exists():
        return
    try:
        subprocess.Popen(
            [str(pythonw), *sys.argv],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except OSError:
        return  # не удалось перезапуститься — продолжаем в консоли
    sys.exit(0)


def main() -> int:
    """Точка входа GUI-обёртки."""
    from launcher_common import setup_logging

    _relaunch_with_pythonw()
    setup_logging()
    config = load_config()
    logger.info('Запуск %s (ОС: %s)', APP_TITLE, platform.system())

    root = tk.Tk()
    LauncherApp(root, config)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())