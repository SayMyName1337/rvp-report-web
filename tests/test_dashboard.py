# -*- coding: utf-8 -*-
"""Проверки дашборда руководства.

Дашборд отвечает на три вопроса: что было за последние сутки, как идёт
месяц и можно ли этим цифрам верить. Третий проверяется особенно
внимательно: руководство смотрит на итог, а не на страницу качества
данных, и оговорки должны стоять рядом с цифрами.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.analytics import dashboard, periods
from apps.analytics.models import CrossCheck
from apps.reports.models import (DeliveryDaily, HseDaily, PowerDaily,
                                 ProductionDaily, Report, WellTotals)

START = date(2026, 8, 1)


def make_day(offset: int, closed: float = 8300.0,
             plan: float = 8200.0) -> Report:
    """Сутки с показателями, достаточными для дашборда."""
    report = Report.objects.create(date=START + timedelta(days=offset))
    ProductionDaily.objects.create(report=report, closed_day=closed,
                                   plan_bp_day=plan, plan_sg_day=plan,
                                   cumulative_month=closed * (offset + 1))
    DeliveryDaily.objects.create(report=report, fact_day=closed)
    PowerDaily.objects.create(report=report, total_with_psp=41.0 + offset * 0.1)
    HseDaily.objects.create(report=report, incidents_count=0, medical_count=1)
    for category, qo in (("downtime", 1000.0), ("idle", 400.0),
                         ("vsp", 20.0)):
        WellTotals.objects.create(report=report, category=category, qo=qo)
    return report


@pytest.mark.django_db
def test_empty_base_does_not_break() -> None:
    """Без единого рапорта дашборд должен собираться, а не падать."""
    data = dashboard.build()
    assert data["latest"] is None
    assert data["total"] == 0


@pytest.mark.django_db
def test_plan_progress_accumulates() -> None:
    """Выполнение плана считается нарастающим итогом с начала месяца."""
    for offset in range(5):
        make_day(offset, closed=8000.0, plan=7900.0)

    progress = dashboard.plan_progress(START + timedelta(days=4))
    assert progress["fact"] == [8000.0, 16000.0, 24000.0, 32000.0, 40000.0]
    assert progress["plan"][-1] == pytest.approx(39500.0)
    assert progress["gap"] == pytest.approx(500.0)


@pytest.mark.django_db
def test_progress_counts_only_current_month() -> None:
    """Нарастающий итог не тянет в месяц данные соседнего."""
    Report.objects.create(date=date(2026, 7, 31))
    ProductionDaily.objects.create(report=Report.objects.get(
        date=date(2026, 7, 31)), closed_day=9999.0, plan_bp_day=9999.0)
    make_day(0, closed=8000.0)

    progress = dashboard.plan_progress(START)
    assert progress["fact"] == [8000.0], "в август попали июльские сутки"


@pytest.mark.django_db
def test_trend_keeps_gaps_empty() -> None:
    """Пропущенные сутки остаются пустыми, а не сглаживаются.

    Разрыв на графике честнее ровной линии через дыру в данных.
    """
    for offset in (0, 1, 3):
        make_day(offset)

    series = dashboard.trend(START + timedelta(days=3), days=4)
    assert series["labels"] == ["01.08", "02.08", "03.08", "04.08"]
    assert series["fact"][2] is None, "пропуск заполнен значением"
    assert series["fact"][3] is not None


@pytest.mark.django_db
def test_trend_splits_losses_by_kind() -> None:
    """Потери на графике разложены на составляющие."""
    make_day(0)
    series = dashboard.trend(START, days=1)
    assert series["downtime"] == [1000.0]
    assert series["idle"] == [400.0]
    assert series["vsp"] == [20.0]


@pytest.mark.django_db
def test_trust_is_clean_when_everything_is_in_order() -> None:
    """Полные проверенные данные не должны вызывать оговорок."""
    for offset in range(31):
        make_day(offset)
    result = dashboard.trust(periods.period_of("month", START))
    assert result["clean"] is True
    assert result["cross"] == 0


@pytest.mark.django_db
def test_trust_notices_missing_days() -> None:
    """Пропуск суток снимает признак «всё в порядке»."""
    for offset in range(30):
        make_day(offset)
    result = dashboard.trust(periods.period_of("month", START))
    assert result["clean"] is False
    assert result["completeness"]["missing"] == [date(2026, 8, 31)]


@pytest.mark.django_db
def test_trust_notices_unreviewed_cross_checks() -> None:
    """Неразобранное межсуточное замечание — тоже оговорка к цифрам."""
    for offset in range(31):
        report = make_day(offset)
    CrossCheck.objects.create(report=report, kind=CrossCheck.Kind.JUMP,
                              metric="closed_day", label="Добыча",
                              message="скачок")

    result = dashboard.trust(periods.period_of("month", START))
    assert result["cross"] == 1
    assert result["clean"] is False


@pytest.mark.django_db
def test_reviewed_cross_check_stops_counting() -> None:
    """Разобранное замечание перестаёт быть оговоркой."""
    for offset in range(31):
        report = make_day(offset)
    CrossCheck.objects.create(report=report, kind=CrossCheck.Kind.JUMP,
                              metric="closed_day", label="Добыча",
                              message="скачок", reviewed=True)

    assert dashboard.trust(periods.period_of("month", START))["clean"] is True


@pytest.mark.django_db
def test_page_shows_caveats_next_to_numbers(client) -> None:
    """Оговорки стоят на самой странице, а не только в разделе качества."""
    for offset in range(30):
        report = make_day(offset)
    CrossCheck.objects.create(report=report, kind=CrossCheck.Kind.JUMP,
                              metric="closed_day", label="Добыча",
                              message="скачок")

    user = User.objects.create_user(username="chief", password="x" * 14)
    client.force_login(user)
    page = client.get(reverse("analytics:dashboard")).content.decode()

    assert "есть оговорки" in page
    assert "31.08" in page, "не названы сутки без данных"
    # Разметка переносит фразу по строкам, поэтому ищутся её части.
    assert "межсуточных" in page and "замечаний: 1" in page


@pytest.mark.django_db
def test_page_works_without_reports(client) -> None:
    """Пустая база даёт страницу с пояснением, а не ошибку."""
    user = User.objects.create_user(username="chief", password="x" * 14)
    client.force_login(user)
    response = client.get(reverse("analytics:dashboard"))
    assert response.status_code == 200
    assert "не загружено" in response.content.decode()
