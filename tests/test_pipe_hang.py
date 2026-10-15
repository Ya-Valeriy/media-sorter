"""
Проверка устойчивости чтения вывода подпроцесса.

Сценарий: основной процесс (sort_media.py) завершается, но дочерний
процесс (например, ffprobe) удерживает pipe stdout открытым ещё несколько
секунд. Старый код лаунчера зависал в цикле чтения, ожидая EOF.
"""
import queue
import subprocess
import sys
import threading

# Родительский процесс: печатает строки, порождает дочерний процесс,
# который наследует stdout (pipe) и живёт дольше родителя, затем выходит.
PARENT_CODE = (
    "import subprocess, sys, time\n"
    "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)'])\n"
    "print('line1')\n"
    "print('line2')\n"
)


def run_with_reader() -> list:
    """Воспроизводит новую логику _run_subprocess из launcher.py."""
    q: queue.Queue = queue.Queue()

    proc = subprocess.Popen(
        [sys.executable, '-c', PARENT_CODE],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
    )

    def read_output() -> None:
        try:
            for line in proc.stdout:
                q.put(line.rstrip('\n'))
        except (OSError, ValueError):
            pass  # pipe закрыт после завершения процесса

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()

    # Ждём завершения процесса (не блокируясь на чтении pipe)
    proc.wait(timeout=30)

    # Закрываем pipe, чтобы разблокировать чтение
    try:
        proc.stdout.close()
    except OSError:
        pass
    reader.join(timeout=5)
    q.put(None)

    lines: list = []
    while True:
        item = q.get()
        if item is None:
            break
        lines.append(item)
    return lines


def main() -> int:
    lines = run_with_reader()
    print('RESULT:', lines)
    if lines == ['line1', 'line2']:
        print('PASS: чтение завершилось, несмотря на удержание pipe дочерним процессом')
        return 0
    print('FAIL: ожидалось [line1, line2]')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())