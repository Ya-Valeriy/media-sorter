"""
Общие функции для launcher.py и install_shortcut.py:
конфигурация, логирование, работа с рабочим столом.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

# --- Константы ---

APP_TITLE: str = 'Сортировка медиафайлов'
CONFIG_FILE: str = 'config.json'
LOG_FILE: str = 'launcher.log'

DEFAULT_CONFIG: Dict[str, Any] = {
    'python_path': '',
    'script_path': '',
    'default_destination': '',
    'last_source': '',
    'default_flags': {
        'check_duplicates': True,
        'junk_folder': True,
        'dry_run_default': False,
    },
    'keep_console_open': True,
}

logger = logging.getLogger(__name__)


def get_base_dir() -> Path:
    """
    Возвращает корневую директорию проекта.

    В portable-режиме (config.json лежит в родительской папке src/)
    возвращает корень portable-папки, иначе — директорию скриптов.
    """
    script_dir = Path(__file__).resolve().parent
    for candidate in (script_dir, script_dir.parent):
        if (candidate / CONFIG_FILE).exists():
            return candidate
    return script_dir


def get_src_dir() -> Path:
    """Возвращает директорию с исходными скриптами (src/ или корень)."""
    base = get_base_dir()
    src = base / 'src'
    return src if src.is_dir() else base


def get_logs_dir() -> Path:
    """Возвращает директорию для логов (logs/ в portable-режиме, иначе корень)."""
    base = get_base_dir()
    logs = base / 'logs'
    return logs if logs.is_dir() else base


def get_reports_dir() -> Path:
    """Возвращает директорию для отчётов (reports/ в portable-режиме, иначе корень)."""
    base = get_base_dir()
    reports = base / 'reports'
    return reports if reports.is_dir() else base


def build_default_config() -> Dict[str, Any]:
    """Формирует конфигурацию по умолчанию с автодетектом путей."""
    base = get_base_dir()
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # глубокая копия
    config['script_path'] = str(base / 'sort_media.py')
    # Для sort_media.py нужен консольный python.exe (вывод в stdout),
    # а не pythonw.exe — иначе прогресс-бар и логи не будут работать.
    exe = Path(sys.executable)
    if exe.name.lower() == 'pythonw.exe':
        exe = exe.with_name('python.exe')
    config['python_path'] = str(exe)
    return config


def load_config() -> Dict[str, Any]:
    """
    Загружает config.json.

    Если файла нет — создаёт его с настройками по умолчанию.
    Недостающие ключи дополняются значениями по умолчанию.
    """
    config_path = get_base_dir() / CONFIG_FILE
    if not config_path.exists():
        config = build_default_config()
        save_config(config)
        return config
    try:
        with open(config_path, encoding='utf-8') as fh:
            config = json.load(fh)
        merged = {**DEFAULT_CONFIG, **config}
        merged['default_flags'] = {
            **DEFAULT_CONFIG['default_flags'],
            **config.get('default_flags', {}),
        }
        return merged
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            'Не удалось прочитать %s: %s. Использую настройки по умолчанию.',
            config_path, exc,
        )
        return build_default_config()


def save_config(config: Dict[str, Any]) -> None:
    """Сохраняет конфигурацию в config.json."""
    config_path = get_base_dir() / CONFIG_FILE
    with open(config_path, 'w', encoding='utf-8') as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)


def setup_logging() -> None:
    """Настраивает логирование: консоль + файл launcher.log."""
    logs_dir = get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / LOG_FILE
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
    )


def get_desktop_dir() -> Path:
    """Возвращает путь к рабочему столу пользователя (кроссплатформенно)."""
    system = platform.system()
    if system == 'Windows':
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(260)
            # CSIDL_DESKTOPDIRECTORY = 0x0010
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0:
                return Path(buf.value)
        except (ImportError, OSError):
            pass
        return Path(os.environ.get('USERPROFILE', str(Path.home()))) / 'Desktop'
    return Path.home() / 'Desktop'


def open_path(path: Path) -> None:
    """Открывает файл или папку в приложении по умолчанию (кроссплатформенно)."""
    system = platform.system()
    try:
        if system == 'Windows':
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif system == 'Darwin':
            subprocess.Popen(['open', str(path)])
        else:
            subprocess.Popen(['xdg-open', str(path)])
    except OSError as exc:
        logger.warning('Не удалось открыть %s: %s', path, exc)