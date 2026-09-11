# -*- coding: utf-8 -*-
"""Периоды сводок: неделя, месяц, квартал, полугодие, год.

Периоды считаются по календарю, а не по числу дней: «месяц» — это
август целиком, а не тридцать суток назад. Иначе сводка не сойдётся
с нарастающими итогами самого рапорта, которые тоже календарные.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

#: Названия месяцев в родительном падеже — для дат вида «5 августа».
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря")

#: Названия месяцев в именительном падеже — для заголовка «Август 2026».
MONTH_NAMES = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
               "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")


@dataclass(frozen=True)
class Period:
    """Отрезок календаря, за который считается сводка."""

    kind: str
    start: date
    end: date

    @property
    def days(self) -> int:
        """Сколько календарных суток в периоде."""
        return (self.end - self.start).days + 1

    @property
    def title(self) -> str:
        """Название периода для заголовка страницы."""
        if self.kind == "month":
            return f"{MONTH_NAMES[self.start.month - 1]} {self.start.year}"
        if self.kind == "year":
            return f"{self.start.year} год"
        if self.kind == "quarter":
            return f"{(self.start.month - 1) // 3 + 1} квартал " \
                   f"{self.start.year}"
        if self.kind == "half":
            return f"{'Первое' if self.start.month == 1 else 'Второе'} " \
                   f"полугодие {self.start.year}"
        return (f"{self.start.day} {MONTHS[self.start.month - 1]} — "
                f"{self.end.day} {MONTHS[self.end.month - 1]} {self.end.year}")


#: Виды периодов и их названия для переключателя.
KINDS = (("week", "Неделя"), ("month", "Месяц"), ("quarter", "Квартал"),
         ("half", "Полугодие"), ("year", "Год"))


def _month_end(day: date) -> date:
    """Последний день месяца, в который попадает дата."""
    if day.month == 12:
        return date(day.year, 12, 31)
    return date(day.year, day.month + 1, 1) - timedelta(days=1)


def period_of(kind: str, anchor: date) -> Period:
    """Период указанного вида, в который попадает дата.

    Args:
        kind: ``week``, ``month``, ``quarter``, ``half`` или ``year``.
        anchor: Любая дата внутри искомого периода.

    Returns:
        Границы периода.

    Raises:
        ValueError: Если вид периода неизвестен.
    """
    if kind == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return Period(kind, start, start + timedelta(days=6))
    if kind == "month":
        return Period(kind, anchor.replace(day=1), _month_end(anchor))
    if kind == "quarter":
        first = (anchor.month - 1) // 3 * 3 + 1
        start = date(anchor.year, first, 1)
        return Period(kind, start, _month_end(date(anchor.year, first + 2, 1)))
    if kind == "half":
        first = 1 if anchor.month <= 6 else 7
        start = date(anchor.year, first, 1)
        return Period(kind, start, _month_end(date(anchor.year, first + 5, 1)))
    if kind == "year":
        return Period(kind, date(anchor.year, 1, 1), date(anchor.year, 12, 31))
    raise ValueError(f"неизвестный период: {kind}")


def shift(period: Period, step: int) -> Period:
    """Соседний период того же вида.

    Args:
        period: Исходный период.
        step: ``-1`` — предыдущий, ``+1`` — следующий.

    Returns:
        Период того же вида, сдвинутый на шаг.
    """
    if period.kind == "week":
        return period_of("week", period.start + timedelta(days=7 * step))
    if step < 0:
        return period_of(period.kind, period.start - timedelta(days=1))
    return period_of(period.kind, period.end + timedelta(days=1))


def custom(start: date, end: date) -> Period:
    """Произвольный период по двум датам.

    Args:
        start: Начало периода.
        end: Конец периода.

    Returns:
        Период вида ``custom`` с упорядоченными границами.
    """
    if end < start:
        start, end = end, start
    return Period("custom", start, end)
