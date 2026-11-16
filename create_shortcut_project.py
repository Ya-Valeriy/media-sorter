"""
Создание ярлыка MS_helper в корневой папке проекта.

Использует run.bat для запуска launcher.py с видимой консолью.
"""

import subprocess
import sys
from pathlib import Path

APP_NAME = 'MS_helper'
ICON_NAME = 'icon.ico'


def find_icon(base: Path) -> Path | None:
    """Ищет иконку для ярлыка."""
    for candidate in (base / ICON_NAME, base / 'assets' / ICON_NAME):
        if candidate.exists():
            return candidate
    return None


def create_shortcut() -> int:
    """Создаёт ярлык через COM-объект WScript.Shell."""
    if sys.platform != 'win32':
        print('Ярлыки создаются только в Windows.')
        return 1

    base = Path(__file__).resolve().parent
    launcher = base / 'run.bat'
    if not launcher.exists():
        print(f'Не найден run.bat в {base}')
        return 1

    icon = find_icon(base)

    shortcut_path = base / f'{APP_NAME}.lnk'

    # Экранируем кавычки для PowerShell
    ps_shortcut = str(shortcut_path).replace("'", "''")
    ps_launcher = str(launcher).replace("'", "''")
    ps_workdir = str(base).replace("'", "''")

    ps_icon = ''
    if icon:
        ps_icon = f"$s.IconLocation = '{str(icon).replace(chr(39), chr(39) * 2)}'"

    script = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{ps_shortcut}')
$s.TargetPath = '{ps_launcher}'
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
        print(f'  Скрипт:        run.bat')
        return 0

    print('Ярлык не появился.')
    return 1


def main() -> int:
    return create_shortcut()


if __name__ == '__main__':
    raise SystemExit(main())
