# -*- coding: utf-8 -*-
"""Преобразователи частей адреса, общие для всех разделов."""
from __future__ import annotations


class DayConverter:
    """Отчётная дата в адресе в виде ``2026-08-21``."""

    regex = r"\d{4}-\d{2}-\d{2}"

    def to_python(self, value: str) -> str:
        """Оставить дату строкой: выборка по ней работает как есть."""
        return value

    def to_url(self, value) -> str:
        """Дата в адресе всегда в виде «год-месяц-день»."""
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        return str(value)
