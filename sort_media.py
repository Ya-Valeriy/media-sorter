#!/usr/bin/env python3
"""
Точка входа для запуска сортировки медиафайлов.

Пример:
    python sort_media.py --source "D:\\Photos\\Unsorted" --destination "D:\\Photos\\Sorted" --dry-run
"""

from media_sorter.main import main

if __name__ == '__main__':
    raise SystemExit(main())