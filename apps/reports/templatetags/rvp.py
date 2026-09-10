# -*- coding: utf-8 -*-
"""Форматирование чисел для страниц.

Числа в докладе читают вслух, поэтому запись русская: разряды через
неразрывный пробел, дробная часть через запятую. Отсутствующее значение
показывается прочерком, а не нулём и не пустотой: «нет данных»
и «ноль» — разные вещи, и путать их нельзя.
"""
from __future__ import annotations

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

#: Чем показывается отсутствующее значение.
DASH = "—"

#: Неразрывный пробел: разряды числа не должны переноситься по строкам.
NBSP = " "


@register.filter
def num(value, digits: int = 0) -> str:
    """Число в русской записи.

    Args:
        value: Значение показателя.
        digits: Знаков после запятой.

    Returns:
        Строку вида ``1 092,19`` или прочерк, если значения нет.
    """
    if value is None or value == "":
        return DASH
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{number:,.{int(digits)}f}"
    return text.replace(",", NBSP).replace(".", ",")


@register.filter
def signed(value, digits: int = 0) -> str:
    """Отклонение со знаком: ``+38`` или ``−201``.

    Минус выводится типографским знаком, а не дефисом: в столбце цифр
    дефис теряется.

    Args:
        value: Отклонение.
        digits: Знаков после запятой.

    Returns:
        Строку со знаком или прочерк, если значения нет.
    """
    if value is None or value == "":
        return DASH
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return ("+" if number >= 0 else "−") + num(abs(number), digits)


@register.filter
def deviation_class(value) -> str:
    """Класс оформления по знаку отклонения.

    Args:
        value: Отклонение.

    Returns:
        ``good``, ``bad`` или ``muted``.
    """
    if value is None or value == "":
        return "muted"
    try:
        return "good" if float(value) >= 0 else "bad"
    except (TypeError, ValueError):
        return "muted"


@register.filter
def share(value, total) -> str:
    """Доля величины в итоге, в процентах.

    Args:
        value: Часть.
        total: Целое.

    Returns:
        Строку вида ``51,3 %`` или прочерк.
    """
    try:
        part, whole = float(value), float(total)
    except (TypeError, ValueError):
        return DASH
    if not whole:
        return DASH
    return num(part / whole * 100, 1) + NBSP + "%"


@register.filter
def bar(value, total) -> str:
    """Ширина полосы в процентах для простых диаграмм в таблице.

    Args:
        value: Значение показателя.
        total: Значение, принимаемое за полную ширину.

    Returns:
        Строку вида ``73.4`` для подстановки в ``style="width:…%"``.
    """
    try:
        part, whole = float(value), float(total)
    except (TypeError, ValueError):
        return "0"
    if not whole:
        return "0"
    return mark_safe(f"{max(0.0, min(100.0, part / whole * 100)):.1f}")
