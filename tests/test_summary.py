# -*- coding: utf-8 -*-
"""Проверки сводок за период.

Главное здесь — не арифметика, а честность: сводка обязана сказать,
за сколько суток из скольких она посчитана. Сумма за месяц, собранная
из двадцати семи суток вместо тридцати одних, — не месячная сумма.
"""
from __future__ import annotations

from datetime import date

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.analytics import periods, summary
from apps.reports.models import (DeliveryDaily, HseDaily, ProductionDaily,
                                 Report, WellTotals)


# --- периоды -----------------------------------------------------------------
@pytest.mark.parametrize("kind,anchor,start,end", [
    ("month", date(2026, 8, 14), date(2026, 8, 1), date(2026, 8, 31)),
    ("month", date(2026, 2, 3), date(2026, 2, 1), date(2026, 2, 28)),
    ("quarter", date(2026, 8, 14), date(2026, 7, 1), date(2026, 9, 30)),
    ("half", date(2026, 8, 14), date(2026, 7, 1), date(2026, 12, 31)),
    ("half", date(2026, 3, 2), date(2026, 1, 1), date(2026, 6, 30)),
    ("year", date(2026, 8, 14), date(2026, 1, 1), date(2026, 12, 31)),
    ("week", date(2026, 8, 14), date(2026, 8, 10), date(2026, 8, 16)),
])
def test_periods_follow_the_calendar(kind: str, anchor: date, start: date,
                                     end: date) -> None:
    """Периоды считаются по календарю, а не по числу дней назад.

    «Месяц» — это август целиком, иначе сводка не сойдётся
    с нарастающими итогами самого рапорта, которые тоже календарные.
    """
    period = periods.period_of(kind, anchor)
    assert (period.start, period.end) == (start, end)


def test_month_title_is_in_nominative_case() -> None:
    """Заголовок месяца — «Август 2026», а не «Августа 2026»."""
    assert periods.period_of("month", date(2026, 8, 14)).title == "Август 2026"


@pytest.mark.parametrize("kind,step,expected", [
    ("month", -1, date(2026, 7, 1)),
    ("month", 1, date(2026, 9, 1)),
    ("quarter", -1, date(2026, 4, 1)),
    ("year", 1, date(2027, 1, 1)),
    ("week", -1, date(2026, 8, 3)),
])
def test_shift_moves_to_neighbour(kind: str, step: int,
                                  expected: date) -> None:
    """Соседний период того же вида находится сдвигом."""
    period = periods.period_of(kind, date(2026, 8, 14))
    assert periods.shift(period, step).start == expected


def test_custom_period_orders_its_bounds() -> None:
    """Произвольный период не зависит от порядка дат."""
    period = periods.custom(date(2026, 8, 31), date(2026, 8, 1))
    assert (period.start, period.end) == (date(2026, 8, 1),
                                          date(2026, 8, 31))


# --- полнота данных ----------------------------------------------------------
def _day(day: int, closed: float = 8000.0, plan: float = 8100.0) -> Report:
    """Сутки августа с минимальным набором показателей."""
    report = Report.objects.create(date=date(2026, 8, day))
    ProductionDaily.objects.create(report=report, closed_day=closed,
                                   plan_bp_day=plan, plan_sg_day=plan)
    DeliveryDaily.objects.create(report=report, fact_day=closed)
    HseDaily.objects.create(report=report, incidents_count=0,
                            medical_count=0)
    return report


@pytest.mark.django_db
def test_complete_period_says_so() -> None:
    """Полный период отмечается как полный."""
    for day in range(1, 32):
        _day(day)
    result = summary.completeness(periods.period_of("month", date(2026, 8, 1)),
                                  today=date(2026, 9, 11))
    assert result["complete"] is True
    assert (result["present"], result["expected"]) == (31, 31)
    assert result["missing"] == []


@pytest.mark.django_db
def test_gaps_are_listed_not_hidden() -> None:
    """Пропущенные сутки перечисляются поимённо.

    Без этого сумма за месяц выглядела бы месячной, хотя таковой
    не является.
    """
    for day in range(1, 32):
        if day in (7, 8, 19):
            continue
        _day(day)
    result = summary.completeness(periods.period_of("month", date(2026, 8, 1)),
                                  today=date(2026, 9, 11))
    assert result["complete"] is False
    assert result["present"] == 28
    assert result["missing"] == [date(2026, 8, 7), date(2026, 8, 8),
                                 date(2026, 8, 19)]


@pytest.mark.django_db
def test_future_days_are_not_counted_as_missing() -> None:
    """За будущие сутки данных быть не может — это не пропуск."""
    for day in range(1, 6):
        _day(day)
    result = summary.completeness(periods.period_of("month", date(2026, 8, 1)),
                                  today=date(2026, 8, 5))
    assert result["expected"] == 5
    assert result["missing"] == []
    assert result["unfinished"] is True


@pytest.mark.django_db
def test_quarter_with_one_month_is_marked_incomplete() -> None:
    """Квартал, в котором есть только один месяц, полным не считается.

    Иначе сумму за август можно принять за квартальную.
    """
    for day in range(1, 32):
        _day(day)
    result = summary.completeness(periods.period_of("quarter",
                                                    date(2026, 8, 1)),
                                  today=date(2026, 9, 11))
    assert result["complete"] is False
    assert result["present"] == 31
    assert result["expected"] > 70


# --- показатели --------------------------------------------------------------
@pytest.mark.django_db
def test_production_sums_and_deviation() -> None:
    """Сумма добычи и отклонение от бизнес-плана за период."""
    for day in range(1, 11):
        _day(day, closed=8000.0, plan=7900.0)
    period = periods.period_of("month", date(2026, 8, 1))
    result = summary.production(period)
    assert result["closed"] == pytest.approx(80000.0)
    assert result["average"] == pytest.approx(8000.0)
    assert result["dev_bp"] == pytest.approx(1000.0)


@pytest.mark.django_db
def test_losses_exclude_fund_movement() -> None:
    """В потери за период входят простой, бездействие и внутрисменные.

    Запуски и остановки — движение фонда, а не потери.
    """
    report = _day(1)
    for category, qo in (("downtime", 100.0), ("idle", 50.0), ("vsp", 5.0),
                         ("startup", 900.0), ("shutdown", 700.0)):
        WellTotals.objects.create(report=report, category=category, qo=qo)

    result = summary.losses(periods.period_of("month", date(2026, 8, 1)))
    assert result["total"] == pytest.approx(155.0)


@pytest.mark.django_db
def test_cumulative_check_notices_a_gap() -> None:
    """Расхождение с нарастающим итогом рапорта должно быть замечено."""
    for day in range(1, 11):
        _day(day, closed=8000.0)
    last = Report.objects.order_by("-date").first()
    last.production.cumulative_month = 70000.0
    last.production.save()

    result = summary.production(periods.period_of("month", date(2026, 8, 1)))
    declared = result["declared"]
    assert declared is not None
    assert declared["gap"] == pytest.approx(10000.0)
    assert declared["notable"] is True


@pytest.mark.django_db
def test_cumulative_check_ignores_rounding() -> None:
    """Расхождение в пределах округления замечанием не считается."""
    for day in range(1, 11):
        _day(day, closed=8000.0)
    last = Report.objects.order_by("-date").first()
    last.production.cumulative_month = 80000.2
    last.production.save()

    declared = summary.production(
        periods.period_of("month", date(2026, 8, 1)))["declared"]
    assert declared["notable"] is False


@pytest.mark.django_db
def test_cumulative_check_only_for_whole_month() -> None:
    """Для недели и квартала сверка нарастающего итога неприменима."""
    for day in range(1, 11):
        _day(day)
    for kind in ("week", "quarter", "year"):
        result = summary.production(periods.period_of(kind, date(2026, 8, 5)))
        assert result["declared"] is None


# --- страница ----------------------------------------------------------------
@pytest.mark.django_db
def test_page_warns_about_gaps(client) -> None:
    """Страница сводки сообщает о неполноте данных прямым текстом."""
    for day in range(1, 31):
        _day(day)
    user = User.objects.create_user(username="chief", password="x" * 14)
    client.force_login(user)

    page = client.get(reverse("analytics:summary"),
                      {"kind": "month", "on": "2026-08-01"}).content.decode()
    assert "Данные неполные" in page
    assert "31.08" in page, "не названы пропущенные сутки"


@pytest.mark.django_db
def test_page_requires_login(client) -> None:
    """Сводки закрыты от посторонних."""
    response = client.get(reverse("analytics:summary"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url
