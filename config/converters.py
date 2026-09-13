# -*- coding: utf-8 -*-
"""Преобразователи частей адреса, общие для всех разделов."""
from __future__ import annotations

from datetime import date


class DayConverter:
    """Отчётная дата в адресе в виде ``2026-08-21``."""

    regex = r"\d{4}-\d{2}-\d{2}"

    def to_python(self, value: str) -> date:
        """Разобрать дату из адреса.

        Выражение пропускает и несуществующие даты вроде ``2026-13-40``:
        оно считает цифры, а не месяцы. Разбор здесь превращает такой
        адрес в «страницу не найдено» — Django понимает ``ValueError``
        как «часть адреса не подошла». Без разбора строка доходила
        до запроса к базе и оборачивалась ошибкой приложения.

        Args:
            value: Часть адреса, совпавшая с выражением.

        Returns:
            Отчётную дату.

        Raises:
            ValueError: Если такой даты не существует.
        """
        return date.fromisoformat(value)

    def to_url(self, value) -> str:
        """Дата в адресе всегда в виде «год-месяц-день»."""
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        return str(value)
