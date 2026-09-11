# -*- coding: utf-8 -*-
"""Сбор данных для дашборда руководства.

Дашборд отвечает на три вопроса, которые задают в первую очередь:
что было за последние сутки, как идёт месяц и можно ли этим цифрам
верить. Последнее — не украшение: руководство не обязано помнить,
что за какие-то сутки данных нет, а без этого сравнение месяцев
вводит в заблуждение.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Sum

from apps.reports.models import (DowntimeBreakdownDaily, Report, WellTotals)

from . import periods, summary
from .models import CrossCheck

#: Сколько суток показывать на графиках динамики.
TREND_DAYS = 30

#: Сколько причин простоя показывать на дашборде.
TOP_REASONS = 6


def latest() -> Report | None:
    """Последние загруженные сутки со всеми связанными показателями."""
    return (Report.objects
            .select_related("production", "delivery", "power", "hse")
            .prefetch_related("well_totals", "stock")
            .order_by("-date").first())


def trend(end: date, days: int = TREND_DAYS) -> dict:
    """Добыча и план по суткам за последние дни.

    Пропущенные сутки остаются пустыми: разрыв на графике честнее
    ровной линии через дыру в данных.

    Args:
        end: Последние сутки ряда.
        days: Длина ряда.

    Returns:
        Подписи и три ряда: факт, план БП и потери.
    """
    start = end - timedelta(days=days - 1)
    rows = {row["date"]: row for row in Report.objects
            .filter(date__range=(start, end))
            .values("date", "production__closed_day",
                    "production__plan_bp_day")}
    losses = _losses_by_day(start, end)

    labels, fact, plan = [], [], []
    downtime, idle, vsp = [], [], []
    day = start
    while day <= end:
        row = rows.get(day)
        parts = losses.get(day, {})
        labels.append(day.strftime("%d.%m"))
        fact.append(row["production__closed_day"] if row else None)
        plan.append(row["production__plan_bp_day"] if row else None)
        downtime.append(parts.get("downtime"))
        idle.append(parts.get("idle"))
        vsp.append(parts.get("vsp"))
        day += timedelta(days=1)

    return {"labels": labels, "fact": fact, "plan": plan,
            "downtime": downtime, "idle": idle, "vsp": vsp}


def _losses_by_day(start: date, end: date) -> dict[date, dict]:
    """Потери по составляющим, разложенные по суткам."""
    found: dict[date, dict] = {}
    rows = (WellTotals.objects
            .filter(report__date__range=(start, end),
                    category__in=Report.LOSS_CATEGORIES)
            .values("report__date", "category", "qo"))
    for row in rows:
        found.setdefault(row["report__date"], {})[row["category"]] = row["qo"]
    return found


def plan_progress(day: date) -> dict:
    """Выполнение бизнес-плана нарастающим итогом с начала месяца.

    Показывает не только отставание на сегодня, но и то, куда идёт
    месяц: если отрыв растёт изо дня в день, это видно по расхождению
    двух линий задолго до конца месяца.

    Args:
        day: Сутки, по которые считать.

    Returns:
        Подписи, нарастающий факт и нарастающий план.
    """
    month = periods.period_of("month", day)
    rows = (Report.objects
            .filter(date__range=(month.start, day))
            .order_by("date")
            .values("date", "production__closed_day",
                    "production__plan_bp_day"))

    labels, fact, plan = [], [], []
    sum_fact = sum_plan = 0.0
    for row in rows:
        sum_fact += row["production__closed_day"] or 0.0
        sum_plan += row["production__plan_bp_day"] or 0.0
        labels.append(row["date"].strftime("%d.%m"))
        fact.append(round(sum_fact, 1))
        plan.append(round(sum_plan, 1))

    # В словаре только то, что переживает превращение в JSON: он уходит
    # в шаблон через json_script и дальше в график.
    return {"labels": labels, "fact": fact, "plan": plan,
            "gap": round(sum_fact - sum_plan, 1) if labels else None}


def reasons(period: periods.Period) -> dict:
    """Причины простоя за период — для круговой диаграммы."""
    rows = (DowntimeBreakdownDaily.objects
            .filter(report__date__range=(period.start, period.end))
            .values("reason__name").annotate(qo=Sum("qo"))
            .order_by("-qo")[:TOP_REASONS])
    return {"labels": [row["reason__name"] for row in rows],
            "values": [round(row["qo"] or 0.0, 1) for row in rows]}


def trust(period: periods.Period) -> dict:
    """Можно ли верить цифрам за период.

    Собрано в одно место намеренно: руководство смотрит на итог,
    а не на страницу качества данных, и должно видеть оговорки рядом
    с цифрами, а не отдельно от них.

    Args:
        period: Период, о котором идёт речь.

    Returns:
        Полнота данных, число неподтверждённых суток и межсуточных
        замечаний, и признак того, что всё в порядке.
    """
    complete = summary.completeness(period)
    cross = CrossCheck.objects.filter(
        report__date__range=(period.start, period.end),
        reviewed=False).count()
    issues = summary.quality(period)

    return {
        "completeness": complete,
        "cross": cross,
        "warnings": issues["warnings"],
        "errors": issues["errors"],
        "clean": (complete["complete"] and not complete["needs_review"]
                  and not cross and not issues["errors"]),
    }


def build() -> dict:
    """Собрать дашборд целиком.

    Returns:
        Данные для страницы или ``{"latest": None}``, если рапортов нет.
    """
    report = latest()
    if report is None:
        return {"latest": None, "total": 0}

    month = periods.period_of("month", report.date)
    return {
        "latest": report,
        "total": Report.objects.count(),
        "month": month,
        "month_summary": summary.production(month),
        "losses": summary.losses(month),
        "trust": trust(month),
        "trend": trend(report.date),
        "progress": plan_progress(report.date),
        "reasons": reasons(month),
    }
