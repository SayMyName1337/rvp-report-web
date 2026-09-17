# -*- coding: utf-8 -*-
"""Форматирование чисел для страниц.

Числа в докладе читают вслух, поэтому запись русская: разряды через
неразрывный пробел, дробная часть через запятую. Отсутствующее значение
показывается прочерком, а не нулём и не пустотой: «нет данных»
и «ноль» — разные вещи, и путать их нельзя.
"""
from __future__ import annotations

from math import isfinite

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
    # NaN и бесконечность — не числа, а след испорченного значения.
    # Показывать «nan» там, где ожидают тонны, нельзя: это выглядит
    # как показатель, а не как его отсутствие.
    if not isfinite(number):
        return DASH
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
    if not isfinite(number):
        return DASH
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
    if not whole or not isfinite(part) or not isfinite(whole):
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
    # Сравнения с NaN всегда ложны, и ограничение диапазона его
    # пропускает: полоса выходила во всю ширину, то есть показывала
    # долю там, где доли нет.
    if not whole or not isfinite(part) or not isfinite(whole):
        return "0"
    return mark_safe(f"{max(0.0, min(100.0, part / whole * 100)):.1f}")


@register.filter
def plural(value, forms: str) -> str:
    """Слово в форме, согласованной с числом.

    Встроенный фильтр ``pluralize`` рассчитан на два варианта: русскому
    существительному нужно три, и при трёх вариантах через запятую он
    молча возвращает пустую строку. На страницах это выглядело так:
    «Всего в базе 33 .» — существительное со счётом просто пропадало.

    В отличие от ``pluralize`` возвращается слово целиком, а не
    окончание: у русских форм различается не только хвост.

    Args:
        value: Число, с которым согласуется слово.
        forms: Три формы через запятую — для одного, для двух-четырёх
            и для пяти и более. Например ``"сутки,суток,суток"``.

    Returns:
        Нужную форму слова; пустую строку, если форм не три.
    """
    variants = [item.strip() for item in str(forms).split(",")]
    if len(variants) != 3:
        return ""
    try:
        count = abs(int(value))
    except (TypeError, ValueError):
        return variants[2]

    # Одиннадцать-четырнадцать идут по общему правилу, несмотря
    # на последнюю цифру: «одиннадцать суток», а не «одиннадцать сутки».
    if 11 <= count % 100 <= 14:
        return variants[2]
    tail = count % 10
    if tail == 1:
        return variants[0]
    if tail in (2, 3, 4):
        return variants[1]
    return variants[2]
