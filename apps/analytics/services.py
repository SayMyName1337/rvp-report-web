# -*- coding: utf-8 -*-
"""Запуск межсуточных проверок и запись их итогов."""
from __future__ import annotations

from datetime import date

from django.db import transaction

from apps.reports.models import Report

from .crosschecks import analyse
from .models import CrossCheck


@transaction.atomic
def recheck(report: Report) -> int:
    """Пересчитать межсуточные замечания за одни сутки.

    Прежние замечания за эти сутки заменяются: история могла
    измениться — например, догрузили пропущенный день.

    Args:
        report: Сутки, которые проверяются.

    Returns:
        Сколько замечаний найдено.
    """
    reviewed = set(
        CrossCheck.objects.filter(report=report, reviewed=True)
        .values_list("kind", "metric"))
    CrossCheck.objects.filter(report=report).delete()

    found = analyse(report)
    CrossCheck.objects.bulk_create([
        CrossCheck(report=report, kind=item.kind, metric=item.metric,
                   label=item.label, message=item.message, value=item.value,
                   baseline=item.baseline, severity=item.severity,
                   reviewed=(item.kind, item.metric) in reviewed)
        for item in found])
    return len(found)


def recheck_range(start: date | None = None,
                  end: date | None = None) -> tuple[int, int]:
    """Пересчитать межсуточные замечания за отрезок дат.

    Args:
        start: Первая дата или None — с самого начала.
        end: Последняя дата или None — до конца.

    Returns:
        Пару «сколько суток проверено, сколько замечаний найдено».
    """
    reports = Report.objects.order_by("date")
    if start is not None:
        reports = reports.filter(date__gte=start)
    if end is not None:
        reports = reports.filter(date__lte=end)

    days = total = 0
    for report in reports:
        total += recheck(report)
        days += 1
    return days, total


def sheet_data(period) -> dict:
    """Данные сводки в том виде, в котором их рисует лист А3.

    Слой отрисовки не знает ни про Django, ни про базу, поэтому
    выборки приводятся здесь к простым значениям: словари, списки
    и даты.

    Args:
        period: Период сводки.

    Returns:
        Словарь для :func:`rvp_report.render.period_sheet.build`.
    """
    from . import summary as summary_service

    data = summary_service.build(period)
    return {
        "title": period.title,
        "start": period.start,
        "end": period.end,
        "clamped": getattr(period, "clamped", False),
        "completeness": data["completeness"],
        "production": data["production"],
        "losses": data["losses"],
        "fields": list(data["fields"]),
        "reasons": list(data["reasons"]),
        "wells": list(data["wells"]),
        "gas": list(data["gas"]),
        "injection": data["injection"],
        "series": [{"date": row["date"],
                    "closed": row["production__closed_day"],
                    "plan": row["production__plan_bp_day"]}
                   for row in data["series"]],
    }
