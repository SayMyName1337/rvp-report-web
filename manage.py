#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Точка входа для команд управления Django."""
import os
import sys


def main() -> None:
    """Выполнить команду управления.

    Raises:
        ImportError: Если Django недоступен — как правило, не активировано
            виртуальное окружение.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as error:
        raise ImportError(
            "Django не найден. Проверьте, что виртуальное окружение "
            "активировано и зависимости установлены."
        ) from error
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
