"""
Создание ярлыка MS_helper на рабочем столе (только Windows).

Запуск:
    python create_shortcut.py

Скрипт определяет портативный Python в папке проекта и создаёт ярлык,
который запускает launcher.py через pythonw.exe — без окна консоли.
Ярлык хранит относительный путь, поэтому папку с программой можно
переносить на другой компьютер или флешку.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

APP_NAME = 'MS_helper'
ICON_NAME = 'icon.ico'
LAUNCHER = 'launcher.py'


def find_python(base: Path) -> Path | None:
    """
    Ищет интерпретатор в папке проекта.

    Приоритет: pythonw.exe (без консоли), затем python.exe.
    """
    for folder in ('python', 'runtime', ''):
        root = base / folder if folder else base
        for name in ('pythonw.exe', 'python.exe'):
            candidate = root / name
            if candidate.exists():
                return candidate
    return None


def find_icon(base: Path) -> Path | None:
    """Ищет иконку для ярлыка."""
    for candidate in (base / ICON_NAME, base / 'assets' / ICON_NAME):
        if candidate.exists():
            return candidate
    return None


def create_shortcut(desktop: bool = True) -> int:
    """Создаёт ярлык через COM-объект WScript.Shell."""
    if sys.platform != 'win32':
        print('Ярлыки создаются только в Windows.')
        return 1

    base = Path(__file__).resolve().parent
    python_exe = find_python(base)
    if python_exe is None:
        print('Не найден Python в папке проекта.')
        print(f'Положите python.exe или pythonw.exe в {base / "python"}')
        return 1

    launcher = base / LAUNCHER
    if not launcher.exists():
        print(f'Не найден {LAUNCHER} в {base}')
        return 1

    icon = find_icon(base)

    # Куда класть ярлык: рабочий стол или корень проекта
    if desktop:
        target_dir = Path.home() / 'Desktop'
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0:
                target_dir = Path(buf.value)
        except (ImportError, OSError, AttributeError):
            pass
    else:
        target_dir = base

    shortcut_path = target_dir / f'{APP_NAME}.lnk'

    # Экранируем кавычки в путях для PowerShell
    ps_python = str(python_exe).replace("'", "''")
    ps_launcher = str(launcher).replace("'", "''")
    ps_shortcut = str(shortcut_path).replace("'", "''")
    ps_workdir = str(base).replace("'", "''")

    ps_icon = ''
    if icon:
        ps_icon = f"$s.IconLocation = '{str(icon).replace(chr(39), chr(39) * 2)}'"

    script = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{ps_shortcut}')
$s.TargetPath = '{ps_python}'
$s.Arguments = '"{ps_launcher}"'
$s.WorkingDirectory = '{ps_workdir}'
$s.Description = 'MS_helper - сортировка медиаархива'
{ps_icon}
$s.Save()
"""

    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f'Не удалось создать ярлык: {exc}')
        return 1

    if result.returncode != 0:
        print('Ошибка PowerShell:')
        print(result.stderr.strip() or result.stdout.strip())
        return 1

    if shortcut_path.exists():
        print(f'Ярлык создан: {shortcut_path}')
        print(f'  Интерпретатор: {python_exe}')
        print(f'  Скрипт:        {launcher}')
        return 0

    print('Ярлык не появился. Проверьте права на запись на рабочий стол.')
    return 1


def main() -> int:
    """Точка входа: создаёт ярлык на рабочем столе."""
    desktop = '--project' not in sys.argv
    return create_shortcut(desktop=desktop)


if __name__ == '__main__':
    raise SystemExit(main())
