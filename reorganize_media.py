#!/usr/bin/env python3
"""
Точка входа для реорганизации структуры медиаархива.

Пример:
    python reorganize_media.py --root "D:\\Photos\\YamankinArchive" --dry-run
    python reorganize_media.py --root "D:\\Photos\\YamankinArchive"
"""

from renamer.main import main

if __name__ == '__main__':
    raise SystemExit(main())