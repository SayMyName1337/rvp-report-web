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
