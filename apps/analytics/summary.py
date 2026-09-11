# -*- coding: utf-8 -*-
"""Сводка за период.

Главное правило этого слоя: **сводка обязана сказать, за сколько суток
из скольких она посчитана**. Сумма за месяц, собранная из двадцати семи
суток вместо тридцати одних, — не месячная сумма, и выдавать её за
таковую нельзя. Поэтому полнота данных считается наравне с самими
показателями и возвращается вместе с ними.

Второе правило: нарастающие итоги, посчитанные в самом рапорте,
сверяются с суммой по суткам. Расхождение между ними — не ошибка
приложения, а диагностика исходных данных, и её надо видеть.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Avg, Count, Q, Sum

from apps.reports.models import (DowntimeBreakdownDaily, FieldProductionDaily,
                                 GasDaily, GroupEvent, InjectionDaily,
                                 LoadIssue, Report, WellDaily, WellTotals)

from .periods import Period

#: Сколько строк показывать в списках «наибольший вклад».
TOP_ROWS = 10

#: Расхождение нарастающего итога с суммой по суткам, при котором
#: о нём стоит говорить, доли от итога.
CUMULATIVE_TOLERANCE = 0.005


def completeness(period: Period, today: date | None = None) -> dict:
    """Полнота данных за период.

    Args:
        period: Период сводки.
        today: Текущая дата; за будущие сутки данных быть не может.

    Returns:
        Сколько суток ожидалось, сколько есть, какие пропущены и сколько
        суток требуют подтверждения.
    """
    today = today or date.today()
    last = min(period.end, today)
    present = list(Report.objects
                   .filter(date__range=(period.start, period.end))
                   .order_by("date")
                   .values_list("date", flat=True))

    expected: list[date] = []
    day = period.start
    while day <= last:
        expected.append(day)
        day += timedelta(days=1)

    have = set(present)
    missing = [day for day in expected if day not in have]

    needs_review = Report.objects.filter(
        date__range=(period.start, period.end),
        status=Report.Status.NEEDS_REVIEW).count()

    return {
        "expected": len(expected),
        "present": len(present),
        "missing": missing,
        "complete": not missing,
        "unfinished": period.end > last,
        "needs_review": needs_review,
        "first": present[0] if present else None,
        "last": present[-1] if present else None,
    }


def production(period: Period) -> dict:
    """Добыча и сдача за период с проверкой нарастающего итога."""
    rows = Report.objects.filter(date__range=(period.start, period.end))
    totals = rows.aggregate(
        closed=Sum("production__closed_day"),
        fact=Sum("production__fact_com_day"),
        average=Avg("production__closed_day"),
        plan_sg=Sum("production__plan_sg_day"),
        plan_bp=Sum("production__plan_bp_day"),
        delivered=Sum("delivery__fact_day"),
        power=Sum("power__total_with_psp"),
        incidents=Sum("hse__incidents_count"),
        medical=Sum("hse__medical_count"))

    closed = totals["closed"] or 0.0
    plan_bp = totals["plan_bp"] or 0.0
    totals["dev_bp"] = closed - plan_bp if plan_bp else None
    totals["dev_sg"] = (closed - (totals["plan_sg"] or 0.0)
                        if totals["plan_sg"] else None)
    totals["declared"] = _declared_cumulative(period, closed)
    return totals


def _declared_cumulative(period: Period, computed: float) -> dict | None:
    """Сверка суммы по суткам с нарастающим итогом самого рапорта.

    Нарастающий итог в рапорте считают за календарный месяц, поэтому
    сверка имеет смысл только для месячного периода, целиком лежащего
    в одном месяце.

    Args:
        period: Период сводки.
        computed: Сумма суточной добычи, посчитанная нами.

    Returns:
        Объявленное значение, расхождение и признак существенности,
        либо None, если сверка неприменима.
    """
    if period.kind != "month" or not computed:
        return None
    last = (Report.objects
            .filter(date__range=(period.start, period.end),
                    production__cumulative_month__isnull=False)
            .order_by("-date").first())
    if last is None:
        return None

    declared = last.production.cumulative_month
    gap = computed - declared
    return {"value": declared, "on": last.date, "gap": gap,
            "notable": abs(gap) > CUMULATIVE_TOLERANCE * abs(declared)}


def losses(period: Period) -> dict:
    """Потери добычи за период по составляющим."""
    rows = (WellTotals.objects
            .filter(report__date__range=(period.start, period.end),
                    category__in=Report.LOSS_CATEGORIES)
            .values("category").annotate(qo=Sum("qo")))
    by_kind = {row["category"]: row["qo"] or 0.0 for row in rows}
    return {
        "parts": [(WellTotals.Category(key).label, by_kind.get(key, 0.0))
                  for key in Report.LOSS_CATEGORIES],
        "total": sum(by_kind.values()),
        "groups": (GroupEvent.objects
                   .filter(report__date__range=(period.start, period.end))
                   .aggregate(qo=Sum("qo"), count=Count("id"))),
    }


def by_field(period: Period) -> list[dict]:
    """Добыча по месторождениям за период."""
    return list(FieldProductionDaily.objects
                .filter(report__date__range=(period.start, period.end))
                .values("field__name")
                .annotate(qo=Sum("qo"), days=Count("report", distinct=True))
                .order_by("-qo"))


def by_reason(period: Period) -> list[dict]:
    """Потери простоя по причинам за период."""
    return list(DowntimeBreakdownDaily.objects
                .filter(report__date__range=(period.start, period.end))
                .values("reason__name")
                .annotate(qo=Sum("qo"), days=Count("report", distinct=True))
                .order_by("-qo"))


def top_wells(period: Period) -> list[dict]:
    """Скважины с наибольшими накопленными потерями простоя.

    То, чего в исходной таблице нет вообще: она показывает только сутки.
    """
    return list(WellDaily.objects
                .filter(report__date__range=(period.start, period.end),
                        category=WellDaily.Category.DOWNTIME)
                .values("well__number", "well__field__name")
                .annotate(qo=Sum("qo"), days=Count("report", distinct=True))
                .order_by("-qo")[:TOP_ROWS])


def gas(period: Period) -> list[dict]:
    """Баланс попутного газа за период в тысячах кубометров.

    Процент утилизации здесь не показывается намеренно: в рапорте он
    постоянен — за 31 сутки августа 2026 он равен 95,5135 % с точностью
    до пятого знака, потому что факел считается от добычи по нормативу,
    а не меряется. Среднее такого показателя за период не несёт
    сведений; добыча и факел в тоннах несут.
    """
    rows = (GasDaily.objects
            .filter(report__date__range=(period.start, period.end))
            .values("kind").annotate(fact=Sum("day_fact"),
                                     plan=Sum("day_plan")))
    order = [GasDaily.Kind.PRODUCTION, GasDaily.Kind.UTILIZATION,
             GasDaily.Kind.FLARE]
    found = {row["kind"]: row for row in rows}
    return [{"label": GasDaily.Kind(kind).label,
             "fact": found.get(kind, {}).get("fact"),
             "plan": found.get(kind, {}).get("plan")}
            for kind in order if kind in found]


def injection(period: Period) -> dict:
    """Закачка ППД за период: факт против режима."""
    return (InjectionDaily.objects
            .filter(report__date__range=(period.start, period.end),
                    is_total=True)
            .aggregate(fact=Sum("fact_day"), plan=Sum("plan_day")))


def daily_series(period: Period) -> list[dict]:
    """Ряд суточных значений для графика."""
    return list(Report.objects
                .filter(date__range=(period.start, period.end))
                .order_by("date")
                .values("date", "production__closed_day",
                        "production__plan_bp_day"))


def quality(period: Period) -> dict:
    """Замечания к исходным данным за период."""
    rows = (LoadIssue.objects
            .filter(report__date__range=(period.start, period.end))
            .exclude(level=LoadIssue.Level.INFO)
            .values("where").annotate(count=Count("id"))
            .order_by("-count")[:TOP_ROWS])
    counts = (LoadIssue.objects
              .filter(report__date__range=(period.start, period.end))
              .aggregate(
                  warnings=Count("id", filter=Q(level=LoadIssue.Level.WARNING)),
                  errors=Count("id", filter=Q(level=LoadIssue.Level.ERROR))))
    return {"top": list(rows), **counts}


def build(period: Period, today: date | None = None) -> dict:
    """Собрать сводку за период целиком.

    Args:
        period: Период сводки.
        today: Текущая дата — за будущие сутки данных быть не может.

    Returns:
        Все разделы сводки вместе со сведениями о полноте данных.
    """
    return {
        "period": period,
        "completeness": completeness(period, today),
        "production": production(period),
        "losses": losses(period),
        "fields": by_field(period),
        "reasons": by_reason(period),
        "wells": top_wells(period),
        "gas": gas(period),
        "injection": injection(period),
        "series": daily_series(period),
        "quality": quality(period),
    }
