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

try:
    from PIL import Image, ImageTk  # масштабирование фона под размер окна
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

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

# Базовые размеры окна (увеличены на 50% по ширине и 30% по высоте от 560x510)
BASE_WIDTH: int = 840
BASE_HEIGHT: int = 663


class LauncherApp:
    """Главное окно приложения-лаунчера."""

    def __init__(self, root: tk.Tk, config: Dict[str, Any]) -> None:
        self.root = root
        self.config = config
        self.output_queue: queue.Queue[Optional[str]] = queue.Queue()
        self.process: Optional[subprocess.Popen] = None
        self.last_report: Optional[Path] = None
        self.last_dest: Optional[Path] = None
        self.scale: float = 1.0
        self.off_x: float = 0.0
        self.off_y: float = 0.0
        self.win_w: int = BASE_WIDTH
        self.win_h: int = BASE_HEIGHT
        self._fullscreen: bool = False
        self._resize_job: Optional[str] = None
        self._bg_item: Optional[int] = None
        self._placed: List[tuple] = []       # (widget, base_x, base_y, base_w, base_h)
        self._texts: List[tuple] = []        # (item_id, base_x, base_y, pt, bold)
        self._win_ids: Dict[tk.Widget, int] = {}
        self._boxes: List[tuple] = []        # (item_id, base_x, base_y, w, h) — квадраты чек-боксов
        self._checks: List[tuple] = []       # (item_id, base_x, base_y, pt) — галки чек-боксов
        self._check_vars: Dict[int, int] = {}  # id(var) -> item галки

        self._build_ui()
        self._center_window(self.win_w, self.win_h)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.bind('<Configure>', self._on_configure)
        self.root.after(100, self._poll_output)

    # --- Масштабирование ---

    def _s(self, value: float) -> int:
        """Масштабирует размер под размер окна."""
        return int(value * self.scale)

    def _sx(self, x: float) -> int:
        """Масштабирует X-координату с учётом центрирования."""
        return int(self.off_x + x * self.scale)

    def _sy(self, y: float) -> int:
        """Масштабирует Y-координату с учётом центрирования."""
        return int(self.off_y + y * self.scale)

    def _font(self, pt: float, bold: bool = False) -> tuple:
        """Шрифт Segoe UI с учётом масштаба окна."""
        return ('Segoe UI', max(9, int(pt * self.scale)), 'bold' if bold else 'normal')

    def _font_mono(self, pt: float) -> tuple:
        """Моноширинный шрифт с учётом масштаба окна."""
        return ('Consolas', max(9, int(pt * self.scale)))

    # --- Построение интерфейса ---

    def _build_ui(self) -> None:
        """Создаёт элементы интерфейса (чёрно-белая фото-тема)."""
        self.root.title(APP_TITLE)
        self.root.resizable(True, True)

        # Иконка окна (из фонового фото)
        icon_path = get_base_dir() / 'icon.ico'
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except tk.TclError:
                pass

        # --- Адаптация окна под экран монитора ---
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.scale = min(screen_w * 0.95 / BASE_WIDTH, screen_h * 0.9 / BASE_HEIGHT)
        self.scale = max(0.85, min(self.scale, 2.2))
        W = self.win_w = int(BASE_WIDTH * self.scale)
        H = self.win_h = int(BASE_HEIGHT * self.scale)
        self.off_x = (W - BASE_WIDTH * self.scale) / 2
        self.off_y = (H - BASE_HEIGHT * self.scale) / 2

        # --- Фон: холст с чёрно-белым изображением ---
        canvas = tk.Canvas(self.root, width=W, height=H, highlightthickness=0, bd=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas = canvas
        self._load_background(W, H)

        # --- Стили (тёмная тема) ---
        self._setup_styles()

        # --- Заголовок ---
        self._text(420, 20, APP_TITLE, '#ffffff', 18, bold=True, anchor=tk.CENTER)
        self._text(420, 42, 'ПОМОЩНИК СОРТИРОВКИ МЕДИА', '#9a9a9a', 10, anchor=tk.CENTER)

        # --- Папка с медиафайлами ---
        self._text(34, 80, 'ПАПКА С МЕДИАФАЙЛАМИ', '#b0b0b0', 9, bold=True)
        self.source_var = tk.StringVar(value=self.config.get('last_source', ''))
        source_entry = tk.Entry(
            canvas, textvariable=self.source_var, state='readonly',
            bg='#d4d4d4', fg='#1a1a1a', readonlybackground='#d4d4d4',
            insertbackground='#1a1a1a', relief=tk.FLAT,
            highlightthickness=1, highlightbackground='#9a9a9a', highlightcolor='#6a6a6a',
            font=self._font_mono(10),
        )
        self._place(source_entry, 34, 88, 605, 30)
        self._place(ttk.Button(canvas, text='Обзор...', command=self._browse_source), 655, 87, 151, 32)

        # --- Папка назначения ---
        self._text(34, 140, 'ПАПКА НАЗНАЧЕНИЯ', '#b0b0b0', 9, bold=True)
        self.dest_var = tk.StringVar(value=self.config.get('default_destination', ''))
        dest_entry = tk.Entry(
            canvas, textvariable=self.dest_var,
            bg='#d4d4d4', fg='#1a1a1a',
            insertbackground='#1a1a1a', relief=tk.FLAT,
            highlightthickness=1, highlightbackground='#9a9a9a', highlightcolor='#6a6a6a',
            font=self._font_mono(10),
        )
        self._place(dest_entry, 34, 148, 605, 30)
        self._place(ttk.Button(canvas, text='Обзор...', command=self._browse_dest), 655, 147, 151, 32)

        # --- Флаги (столбик под папкой назначения, по левому краю) ---
        flags = self.config.get('default_flags', {})
        self.dry_run_var = tk.BooleanVar(value=bool(flags.get('dry_run_default', False)))
        self.duplicates_var = tk.BooleanVar(value=bool(flags.get('check_duplicates', True)))
        self.junk_var = tk.BooleanVar(value=bool(flags.get('junk_folder', True)))
        self.rename_var = tk.BooleanVar(value=bool(flags.get('rename_by_date', True)))
        self._checkbox(34, 195, 'Пробный прогон (ничего не удалим и не создадим, только проверка)', self.dry_run_var)
        self._checkbox(34, 215, 'Отсортировать дубликаты (создадим папку Дубликаты)', self.duplicates_var)
        self._checkbox(34, 235, 'Переименовать по дате съёмки (переименуем по метаданным / дате съёмки)', self.rename_var)
        self.negative_var = tk.BooleanVar(value=bool(flags.get('negative_folder', True)))
        self._checkbox(34, 255, 'Отсортировать негативы (создадим папку Негативы и поместим в нее файлы RAW)', self.negative_var)
        self._checkbox(34, 275, 'Отсортировать мусор (создадим папку Мусор)', self.junk_var)

        # --- Пороги «Мусора» ---
        self._text(34, 305,
                   'ЗАДАТЬ ПОРОГИ МУСОРА (предложенные значения выставлены по умолчанию)',
                   '#b0b0b0', 9, bold=True)
        self.photo_kb_var = tk.StringVar(value='2048')
        self.video_sec_var = tk.StringVar(value='10')
        self.video_kb_var = tk.StringVar(value='0')
        self._junk_field(canvas, 34, 325, 'Фото ≤', self.photo_kb_var, 'КБ')
        self._junk_field(canvas, 320, 325, 'Видео ≤', self.video_sec_var, 'сек.')
        self._junk_field(canvas, 606, 325, 'Видео ≤', self.video_kb_var, 'КБ')

        # --- Кнопки ---
        self.run_button = ttk.Button(canvas, text='Запустить', style='Accent.TButton',
                                     command=self._start_sorting)
        self._place(self.run_button, 34, 375, 134, 36)
        self._place(ttk.Button(canvas, text='Отмена', command=self._on_close), 185, 375, 109, 36)
        self.report_button = ttk.Button(canvas, text='Открыть отчёт', command=self._open_report,
                                        state=tk.DISABLED)
        self._place(self.report_button, 311, 375, 134, 36)
        self.dest_button = ttk.Button(canvas, text='Открыть папку', command=self._open_dest,
                                      state=tk.DISABLED)
        self._place(self.dest_button, 462, 375, 134, 36)
        self._place(ttk.Button(canvas, text='⛶ На весь экран', command=self._toggle_fullscreen),
                    610, 375, 196, 36)

        # --- Прогресс ---
        self.progress = ttk.Progressbar(canvas, mode='indeterminate')
        self._place(self.progress, 34, 418, 773, 14)

        # --- Лог (30% окна) ---
        self.log_text = scrolledtext.ScrolledText(
            canvas, state=tk.DISABLED,
            bg='#101010', fg='#c8c8c8', insertbackground='#c8c8c8',
            relief=tk.FLAT, highlightthickness=1, highlightbackground='#3a3a3a',
            highlightcolor='#6a6a6a', font=self._font_mono(10), padx=6, pady=4,
        )
        self._place(self.log_text, 34, 444, 773, 176)

    def _setup_styles(self) -> None:
        """Настраивает тёмную тему ttk с учётом масштаба."""
        S = self._s
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure(
            'TButton',
            background='#2b2b2b', foreground='#e8e8e8',
            bordercolor='#5a5a5a', lightcolor='#2b2b2b', darkcolor='#2b2b2b',
            padding=(S(12), S(5)), font=self._font(10),
        )
        style.map(
            'TButton',
            background=[('active', '#c0c0c0'), ('pressed', '#9a9a9a'), ('disabled', '#222222')],
            foreground=[('active', '#1a1a1a'), ('pressed', '#1a1a1a'), ('disabled', '#777777')],
        )
        style.configure(
            'Accent.TButton',
            background='#3a3a3a', foreground='#ffffff',
            bordercolor='#9a9a9a', lightcolor='#3a3a3a', darkcolor='#3a3a3a',
            font=self._font(11, bold=True),
        )
        style.map(
            'Accent.TButton',
            background=[('active', '#c0c0c0'), ('pressed', '#9a9a9a'), ('disabled', '#222222')],
            foreground=[('active', '#1a1a1a'), ('pressed', '#1a1a1a'), ('disabled', '#777777')],
        )
        style.configure('TCheckbutton', background='#141414', foreground='#d0d0d0', font=self._font(10))
        style.map('TCheckbutton', background=[('active', '#141414')])
        style.configure(
            'TProgressbar',
            background='#9a9a9a', troughcolor='#1e1e1e',
            bordercolor='#333333', lightcolor='#9a9a9a', darkcolor='#9a9a9a',
        )

    def _load_background(self, W: int, H: int) -> None:
        """Загружает и растягивает фоновое изображение под размер окна."""
        bg_path = get_base_dir() / 'assets' / 'background.png'
        if not bg_path.exists():
            self.canvas.configure(bg='#141414')
            return
        try:
            if _HAS_PIL:
                img = Image.open(bg_path).resize((W, H), Image.LANCZOS)
                self.bg_photo = ImageTk.PhotoImage(img)
            else:
                self.bg_photo = tk.PhotoImage(file=str(bg_path))
            if self._bg_item is not None:
                self.canvas.delete(self._bg_item)
            self._bg_item = self.canvas.create_image(0, 0, image=self.bg_photo, anchor=tk.NW)
            self.canvas.tag_lower(self._bg_item)
        except Exception:  # noqa: BLE001
            self.canvas.configure(bg='#141414')

    def _place(self, widget: tk.Widget, x: int, y: int,
               w: Optional[int] = None, h: Optional[int] = None) -> None:
        """Размещает виджет (координаты в базовом дизайне 840x663)."""
        opts: Dict[str, Any] = {'window': widget, 'anchor': tk.NW}
        if w is not None:
            opts['width'] = self._s(w)
        if h is not None:
            opts['height'] = self._s(h)
        item = self.canvas.create_window(self._sx(x), self._sy(y), **opts)
        self._win_ids[widget] = item
        self._placed.append((widget, x, y, w or 0, h or 0))

    def _text(self, x: int, y: int, text: str, fill: str, pt: float,
              bold: bool = False, anchor: str = tk.W) -> int:
        """Создаёт текст на холсте (координаты в базовом дизайне)."""
        item = self.canvas.create_text(self._sx(x), self._sy(y), text=text, fill=fill,
                                       anchor=anchor, font=self._font(pt, bold))
        self._texts.append((item, x, y, pt, bold))
        return item

    def _junk_field(self, canvas: tk.Canvas, x: int, y: int, label: str,
                    var: tk.StringVar, unit: str) -> None:
        """Создаёт поле ввода порога «Мусора»: подпись + поле + единица."""
        self._text(x, y + 22, label, '#c0c0c0', 10, anchor=tk.SW)
        entry = tk.Entry(
            canvas, textvariable=var, width=6, justify=tk.CENTER,
            bg='#d4d4d4', fg='#1a1a1a', insertbackground='#1a1a1a',
            relief=tk.FLAT, highlightthickness=1,
            highlightbackground='#9a9a9a', highlightcolor='#6a6a6a',
            font=self._font_mono(10),
        )
        self._place(entry, x + 70, y, 68, 22)
        self._text(x + 145, y + 22, unit, '#c0c0c0', 10, anchor=tk.SW)

    def _checkbox(self, x: int, y: int, text: str, var: tk.BooleanVar) -> None:
        """Создаёт чек-бокс: тёмный квадрат + зелёная галка (canvas)."""
        size = 18
        box = self.canvas.create_rectangle(
            self._sx(x), self._sy(y), self._sx(x + size), self._sy(y + size),
            fill='#1c1c1c', outline='#5a5a5a', width=1,
        )
        self._boxes.append((box, x, y, size, size))
        check = self.canvas.create_text(
            self._sx(x + size / 2), self._sy(y + size / 2), text='✓',
            fill='#2ecc40', font=self._font(11, bold=True),
        )
        self._checks.append((check, x + size / 2, y + size / 2, 11))
        self._check_vars[id(var)] = check
        label = self._text(x + size + 8, y + size / 2, text, '#d0d0d0', 10)
        for item in (box, check, label):
            self.canvas.tag_bind(item, '<Button-1>', lambda e, v=var: self._toggle_check(v))
            self.canvas.tag_bind(item, '<Enter>', lambda e: self.canvas.config(cursor='hand2'))
            self.canvas.tag_bind(item, '<Leave>', lambda e: self.canvas.config(cursor=''))
        self.canvas.itemconfig(check, state=tk.NORMAL if var.get() else tk.HIDDEN)

    def _toggle_check(self, var: tk.BooleanVar) -> None:
        """Переключает значение чек-бокса и обновляет галку."""
        var.set(not var.get())
        item = self._check_vars.get(id(var))
        if item is not None:
            self.canvas.itemconfig(item, state=tk.NORMAL if var.get() else tk.HIDDEN)

    def _on_configure(self, event: tk.Event) -> None:
        """Пересчитывает компоновку при изменении размера окна."""
        if event.widget is not self.root:
            return
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(120, self._relayout)

    def _relayout(self) -> None:
        """Пересчитывает масштаб и переразмещает элементы под текущий размер."""
        self._resize_job = None
        W = self.root.winfo_width()
        H = self.root.winfo_height()
        if W < 200 or H < 200:
            return
        self.scale = min(W / BASE_WIDTH, H / BASE_HEIGHT)
        self.scale = max(0.5, min(self.scale, 3.0))
        self.off_x = (W - BASE_WIDTH * self.scale) / 2
        self.off_y = (H - BASE_HEIGHT * self.scale) / 2
        self._load_background(W, H)
        for widget, x, y, w, h in self._placed:
            item = self._win_ids.get(widget)
            if item is None:
                continue
            self.canvas.coords(item, self._sx(x), self._sy(y))
            opts: Dict[str, Any] = {}
            if w:
                opts['width'] = self._s(w)
            if h:
                opts['height'] = self._s(h)
            if opts:
                self.canvas.itemconfig(item, **opts)
        for item, x, y, pt, bold in self._texts:
            self.canvas.coords(item, self._sx(x), self._sy(y))
            self.canvas.itemconfig(item, font=self._font(pt, bold))
        for item, x, y, w, h in self._boxes:
            self.canvas.coords(item, self._sx(x), self._sy(y), self._sx(x + w), self._sy(y + h))
        for item, x, y, pt in self._checks:
            self.canvas.coords(item, self._sx(x), self._sy(y))
            self.canvas.itemconfig(item, font=self._font(pt, bold=True))
        self._setup_styles()

    def _toggle_fullscreen(self) -> None:
        """Разворачивает окно на весь экран / возвращает исходный размер."""
        self._fullscreen = not self._fullscreen
        try:
            if self._fullscreen:
                self.root.state('zoomed')  # Windows: развернуть на весь экран
            else:
                self.root.state('normal')
                self._center_window(self.win_w, self.win_h)
        except tk.TclError:
            self.root.attributes('-fullscreen', self._fullscreen)

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
            # Если папка назначения не задана — предлагаем родительскую папку
            # (результаты будут помещены в подпапку MS_helper)
            if not self.dest_var.get().strip():
                self.dest_var.set(str(Path(folder).parent))
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
        dest_root = Path(self.dest_var.get().strip())
        # Результаты сортировки помещаются в подпапку MS_helper внутри папки назначения
        dest = dest_root / 'MS_helper'

        # Валидация
        if not source.exists() or not source.is_dir():
            messagebox.showerror('Ошибка', f'Папка-источник не существует:\n{source}')
            return
        if not any(source.iterdir()):
            messagebox.showerror('Ошибка', f'Папка-источник пуста:\n{source}')
            return
        if not str(dest_root):
            messagebox.showerror('Ошибка', 'Укажите папку назначения.')
            return

        # Создаём папку MS_helper в папке назначения
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror('Ошибка', f'Не удалось создать папку {dest}:\n{exc}')
            return

        script_path = self._resolve_script_path()
        if script_path is None:
            return
        python_path = self._resolve_python_path()
        if python_path is None:
            return

        # Сохраняем последние пути в конфиг
        self.config['last_source'] = str(source)
        self.config['default_destination'] = str(dest_root)
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
        else:
            # Пороги «Мусора» (0 — не задано, используется значение по умолчанию)
            for flag, var in (
                ('--photo-junk-max-kb', self.photo_kb_var),
                ('--video-junk-max-sec', self.video_sec_var),
                ('--video-junk-max-kb', self.video_kb_var),
            ):
                value = var.get().strip().replace(',', '.')
                if not value:
                    continue
                try:
                    float(value)
                except ValueError:
                    continue
                cmd += [flag, value]
        if not self.negative_var.get():
            cmd.append('--no-negative')
        if not self.rename_var.get():
            cmd.append('--no-rename')

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


def main() -> int:
    """Точка входа GUI-обёртки."""
    from launcher_common import setup_logging

    setup_logging()
    config = load_config()
    logger.info('Запуск %s (ОС: %s)', APP_TITLE, platform.system())

    root = tk.Tk()
    LauncherApp(root, config)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())