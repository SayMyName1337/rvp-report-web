# -*- coding: utf-8 -*-
"""Правила связности суточного рапорта.

Рапорт содержит величины, посчитанные в нём дважды разными способами:
например, суммарные потери простоя стоят и в таблице фонда скважин,
и складываются из списка скважин. Расхождение между ними означает ошибку
в исходных данных, поэтому все такие сверки собраны здесь.

Слой не знает ни про Excel, ни про PowerPoint: на вход подаётся готовая
модель, на выходе — список замечаний.
"""
from __future__ import annotations

from .model import DailyReport

#: Допустимое расхождение сверяемых величин, доли от значения.
RELATIVE_TOLERANCE = 0.02
#: Минимальное абсолютное расхождение, ниже которого сверка не срабатывает.
ABSOLUTE_TOLERANCE = 1.0

#: Порог расхождения закрытия добычи и факта ЦОМ, доли от закрытия.
PRODUCTION_GAP = 0.05
#: Во сколько раз факт закачки должен превысить режим, чтобы это заметили.
INJECTION_EXCESS = 1.5
#: Во сколько раз сдача должна превысить добычу, чтобы это заметили.
DELIVERY_EXCESS = 1.3


def ru(value: float, digits: int = 0) -> str:
    """Число в русской записи: пробел между разрядами, запятая в дроби.

    Args:
        value: Форматируемое число.
        digits: Знаков после запятой.

    Returns:
        Строку вида ``1 092,19``.
    """
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def validate(report: DailyReport) -> None:
    """Сверить величины рапорта между собой и записать замечания.

    Замечания добавляются прямо в ``report.issues``: они попадают
    в консоль, в окно программы и на служебный слайд презентации.

    Args:
        report: Прочитанный суточный рапорт.
    """
    _check_production(report)
    _check_stock(report)
    _check_breakdown(report)
    _check_injection(report)
    _check_delivery(report)


def _check_production(report: DailyReport) -> None:
    """Закрытие добычи по сводке против фактической добычи ЦОМ."""
    closed = report.production.closed_day
    fact = report.production.fact_com_day
    if not closed or fact is None:
        return
    gap = abs(closed - fact)
    if gap > PRODUCTION_GAP * closed:
        report.add_issue("warning", "Добыча",
                         f"закрытие и факт ЦОМ расходятся на {ru(gap)} т")


def _check_stock(report: DailyReport) -> None:
    """Состав эксплуатационного фонда и потери по спискам скважин."""
    stock = report.stock_total
    if stock is None:
        return

    parts = sum(value or 0 for value in (stock.in_work, stock.in_downtime,
                                         stock.in_idle, stock.awaiting))
    operating = stock.operating_stock or 0
    if operating and abs(parts - operating) > 0.5:
        report.add_issue(
            "warning", "Фонд скважин",
            f"эксплуатационный фонд {ru(operating)} ≠ "
            f"в работе + простой + БД + освоение = {ru(parts)}")

    compare(report, "Текущий простой", stock.downtime_rate,
            report.downtime_total.qo, "т/сут")
    compare(report, "Бездействие", stock.idle_rate,
            report.idle_total.qo, "т/сут")


def _check_breakdown(report: DailyReport) -> None:
    """Разбивка простоя по причинам должна складываться в общий простой."""
    if not report.downtime_breakdown:
        return
    parts = sum(qo for _name, _count, qo in report.downtime_breakdown)
    compare(report, "Текущий простой: разбивка по причинам",
            report.downtime_total.qo, parts, "т/сут")


def _check_injection(report: DailyReport) -> None:
    """Факт закачки, кратно превышающий режим, — признак устаревшего режима."""
    for item in report.injection:
        if not item.plan_day or item.fact_day is None or item.plan_day <= 0:
            continue
        if item.fact_day > INJECTION_EXCESS * item.plan_day:
            report.add_issue(
                "warning", f"ППД, {item.name}",
                f"факт {ru(item.fact_day)} м³ превышает режим "
                f"{ru(item.plan_day)} м³ более чем "
                f"в {ru(INJECTION_EXCESS, 1)} раза")


def _check_delivery(report: DailyReport) -> None:
    """Сдача, заметно превышающая добычу, требует объяснения."""
    fact = report.delivery.fact_day
    closed = report.production.closed_day
    if fact and closed and fact > DELIVERY_EXCESS * closed:
        report.add_issue("warning", "Сдача",
                         "сдача существенно превышает добычу за сутки")


def compare(report: DailyReport, where: str, declared: float | None,
            computed: float | None, unit: str) -> None:
    """Сверить величину из таблицы с посчитанной по списку.

    Args:
        report: Рапорт, в который добавляется замечание.
        where: Блок рапорта — попадёт в текст замечания.
        declared: Значение, объявленное в рапорте.
        computed: Значение, посчитанное программой.
        unit: Единица измерения для текста замечания.
    """
    if declared is None or computed is None or declared == 0:
        return
    limit = max(ABSOLUTE_TOLERANCE, RELATIVE_TOLERANCE * abs(declared))
    if abs(declared - computed) > limit:
        report.add_issue(
            "warning", where,
            f"в рапорте {ru(declared, 1)} {unit}, "
            f"по списку {ru(computed, 1)} {unit}")
