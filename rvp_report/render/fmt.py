# -*- coding: utf-8 -*-
"""Форматирование чисел по русским правилам: 8 351,8 — пробел разряды, запятая дробь."""
from __future__ import annotations

NBSP = " "
DASH = "—"


def num(value: float | None, digits: int = 0, dash: str = DASH) -> str:
    """Число в русской записи: пробел между разрядами, запятая в дроби.

    Args:
        value: Форматируемое число; None даёт прочерк.
        digits: Знаков после запятой.
        dash: Чем заменять отсутствующее значение.

    Returns:
        Строку вида ``8 351,8``.
    """
    if value is None:
        return dash
    text = f"{value:,.{digits}f}".replace(",", NBSP).replace(".", ",")
    return text


def signed(value: float | None, digits: int = 0, dash: str = DASH) -> str:
    """Отклонение со знаком: +38, −1 707."""
    if value is None:
        return dash
    rounded = round(value, digits)
    sign = "+" if rounded >= 0 else "−"
    return sign + num(abs(rounded), digits, dash)


def pct(value: float | None, digits: int = 1, dash: str = DASH) -> str:
    """Значение с процентом: ``95,5 %``."""
    return dash if value is None else f"{num(value, digits)} %"


def ratio_pct(fact: float | None, plan: float | None, digits: int = 1) -> str:
    """Доля факта от плана в процентах.

    Args:
        fact: Фактическое значение.
        plan: Плановое значение; ноль или None дают прочерк.
        digits: Знаков после запятой.

    Returns:
        Строку вида ``96,3 %`` либо прочерк.
    """
    if not plan:
        return DASH
    return f"{num((fact or 0) / plan * 100, digits)} %"


def date_ru(value, dash: str = DASH) -> str:
    """Дата в виде ``дд.мм.гггг``."""
    return dash if value is None else value.strftime("%d.%m.%Y")


def short(text: str, limit: int) -> str:
    """Укоротить текст до предела, заменив хвост многоточием."""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
