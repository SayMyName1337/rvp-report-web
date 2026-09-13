# -*- coding: utf-8 -*-
"""Проверки сверки суток с соседними.

Эти правила существуют ради случая 21.08.2026: рапорт был
непротиворечив сам себе — список сходился с итогом, итог с фондом, —
но показывал 329 скважин в работе вместо обычных 253 при самой низкой
добыче за месяц. Внутрисуточные проверки такое не ловят в принципе.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User, ensure_roles
from apps.analytics import crosschecks
from apps.analytics.models import CrossCheck
from apps.analytics.services import recheck, recheck_range
from apps.reports.models import (DeliveryDaily, PowerDaily, ProductionDaily,
                                 Report, StockDaily, WellTotals)

START = date(2026, 8, 1)


def make_day(offset: int, closed: float = 8300.0, in_work: float = 253.0,
             in_downtime: float = 85.0, losses: float = 1600.0,
             delivered: float = 9200.0) -> Report:
    """Сутки с обычными показателями промысла.

    Args:
        offset: Смещение от первого августа.
        closed: Закрытие добычи за сутки, т.
        in_work: Скважин в работе.
        in_downtime: Скважин в текущем простое.
        losses: Потери добычи, т.
        delivered: Сдача нефти, т.

    Returns:
        Созданные сутки.
    """
    report = Report.objects.create(date=START + timedelta(days=offset))
    ProductionDaily.objects.create(report=report, closed_day=closed,
                                   plan_bp_day=8300.0)
    DeliveryDaily.objects.create(report=report, fact_day=delivered)
    # Выработка слегка гуляет от суток к суткам, как в жизни: ровная
    # константа сама по себе была бы поводом для замечания о застое.
    PowerDaily.objects.create(report=report,
                              total_with_psp=41.0 + (offset % 5) * 0.3)
    StockDaily.objects.create(report=report, is_total=True, in_work=in_work,
                              in_downtime=in_downtime, in_idle=56.0)
    WellTotals.objects.create(report=report, category="downtime", qo=losses)
    return report


def _usual(days: int = 12) -> None:
    """Заполнить историю обычными сутками с лёгкими колебаниями."""
    for offset in range(days):
        make_day(offset,
                 closed=8300.0 + (offset % 3) * 15,
                 in_work=253.0,
                 in_downtime=85.0 + (offset % 2),
                 losses=1600.0 + (offset % 4) * 20,
                 delivered=9200.0 + (offset % 3) * 40)


@pytest.mark.django_db
def test_ordinary_day_raises_nothing() -> None:
    """Обычные сутки не должны давать замечаний.

    Правило, срабатывающее каждый день, читать никто не станет,
    и настоящее замечание в нём утонет.
    """
    _usual()
    report = make_day(12)
    assert crosschecks.analyse(report) == []


@pytest.mark.django_db
def test_august_21_is_caught() -> None:
    """Случай 21.08.2026 должен быть замечен.

    Фонд в работе вырос на треть, простой упал почти до нуля,
    а добыча при этом снизилась.
    """
    _usual()
    report = make_day(12, closed=7950.0, in_work=329.0, in_downtime=11.0,
                      losses=651.0)
    kinds = {item.kind for item in crosschecks.analyse(report)}

    assert "jump" in kinds, "резкое изменение фонда осталось незамеченным"
    assert "contradiction" in kinds, (
        "рост фонда при падении добычи не признан противоречием")


@pytest.mark.django_db
def test_contradiction_names_both_sides() -> None:
    """Замечание о противоречии называет и фонд, и добычу."""
    _usual()
    report = make_day(12, closed=7950.0, in_work=329.0)
    found = [item for item in crosschecks.analyse(report)
             if item.kind == "contradiction"]
    assert found, "противоречие не найдено"
    message = found[0].message
    assert "329" in message and "7 950" in message


@pytest.mark.django_db
def test_growing_fund_with_growing_output_is_normal() -> None:
    """Рост фонда вместе с ростом добычи противоречием не считается."""
    _usual()
    report = make_day(12, closed=9200.0, in_work=329.0)
    kinds = {item.kind for item in crosschecks.analyse(report)}
    assert "contradiction" not in kinds


@pytest.mark.django_db
def test_frozen_value_is_noticed() -> None:
    """Показатель, не меняющийся трое суток, попадает в замечания.

    Признак того, что строку скопировали, а не заполнили заново.
    """
    _usual()
    for offset in (12, 13, 14):
        report = make_day(offset, losses=1234.5)
    found = [item for item in crosschecks.analyse(report)
             if item.kind == "frozen"]
    assert any(item.metric == "losses" for item in found)


@pytest.mark.django_db
def test_stable_well_count_is_not_frozen() -> None:
    """Неизменное число скважин застоем не считается.

    Фонд может не меняться неделю, и это обычное дело. Слежение
    за застоем включено только у величин, которые обязаны меняться
    каждые сутки.
    """
    _usual()
    for offset in (12, 13, 14):
        report = make_day(offset)
    frozen = [item for item in crosschecks.analyse(report)
              if item.kind == "frozen"]
    assert not any(item.metric.startswith("in_") for item in frozen)


@pytest.mark.django_db
def test_small_deviation_is_not_reported() -> None:
    """Отклонение на несколько скважин замечанием не считается.

    У почти постоянного показателя разброс схлопывается, и без
    дополнительного условия выбросом выглядела бы любая мелочь.
    """
    _usual()
    report = make_day(12, in_downtime=88.0)
    assert not [item for item in crosschecks.analyse(report)
                if item.metric == "in_downtime"]


@pytest.mark.django_db
def test_jump_replaces_level_for_the_same_metric() -> None:
    """Об одном показателе не говорят дважды разными словами."""
    _usual()
    report = make_day(12, closed=6000.0)
    kinds = [item.kind for item in crosschecks.analyse(report)
             if item.metric == "closed_day"]
    assert kinds.count("jump") == 1
    assert "level" not in kinds


@pytest.mark.django_db
def test_first_day_has_nothing_to_compare_with() -> None:
    """Первые сутки сравнивать не с чем — и это не замечание."""
    report = make_day(0)
    assert crosschecks.analyse(report) == []


# --- запись итогов -----------------------------------------------------------
@pytest.mark.django_db
def test_recheck_replaces_previous_findings() -> None:
    """Повторная сверка заменяет прежние замечания, а не добавляет."""
    _usual()
    report = make_day(12, in_work=329.0, closed=7950.0)

    first = recheck(report)
    second = recheck(report)
    assert first == second
    assert CrossCheck.objects.filter(report=report).count() == first


@pytest.mark.django_db
def test_reviewed_mark_survives_recheck() -> None:
    """Отметка «разобрано» не слетает при пересчёте.

    Иначе разобранное замечание возвращалось бы после каждой загрузки.
    """
    _usual()
    report = make_day(12, in_work=329.0, closed=7950.0)
    recheck(report)

    check = CrossCheck.objects.filter(report=report).first()
    check.reviewed = True
    check.save(update_fields=["reviewed"])

    recheck(report)
    assert CrossCheck.objects.filter(
        report=report, kind=check.kind, metric=check.metric,
        reviewed=True).exists()


@pytest.mark.django_db
def test_recheck_range_covers_every_day() -> None:
    """Пересчёт отрезка проходит по всем суткам."""
    _usual(days=6)
    days, _findings = recheck_range()
    assert days == 6


# --- страница ----------------------------------------------------------------
@pytest.mark.django_db
def test_quality_page_shows_findings(client) -> None:
    """Страница качества данных показывает межсуточные замечания."""
    _usual()
    report = make_day(12, in_work=329.0, closed=7950.0)
    recheck(report)

    user = User.objects.create_user(username="chief", password="x" * 14)
    client.force_login(user)
    page = client.get(reverse("analytics:quality"),
                      {"kind": "month", "on": "2026-08-01"}).content.decode()
    assert "Сверка с соседними сутками" in page
    assert "329" in page


@pytest.mark.django_db
def test_review_requires_permission(client) -> None:
    """Отмечать замечания разобранными может не всякий."""
    _usual()
    report = make_day(12, in_work=329.0, closed=7950.0)
    recheck(report)
    check = CrossCheck.objects.filter(report=report).first()

    groups = ensure_roles()
    viewer = User.objects.create_user(username="chief", password="x" * 14)
    viewer.groups.add(groups[Role.MANAGEMENT.value])
    client.force_login(viewer)
    assert client.post(
        reverse("analytics:reviewed", args=[check.pk])).status_code == 403

    operator = User.objects.create_user(username="citu", password="x" * 14)
    operator.groups.add(groups[Role.FIELD.value])
    client.force_login(operator)
    assert client.post(
        reverse("analytics:reviewed", args=[check.pk])).status_code == 302
    check.refresh_from_db()
    assert check.reviewed is True


@pytest.mark.django_db
def test_review_does_not_redirect_outside(client) -> None:
    """Отметка не уводит на чужой сайт.

    Возврат делается по заголовку `Referer`, который присылает браузер.
    Без проверки страница становится переадресатором на любой внешний
    адрес: достаточно прислать человеку ссылку с подставленным Referer.
    """
    _usual()
    report = make_day(12, in_work=329.0, closed=7950.0)
    recheck(report)
    check = CrossCheck.objects.filter(report=report).first()

    groups = ensure_roles()
    operator = User.objects.create_user(username="citu", password="x" * 14)
    operator.groups.add(groups[Role.FIELD.value])
    client.force_login(operator)

    response = client.post(reverse("analytics:reviewed", args=[check.pk]),
                           HTTP_REFERER="https://example.org/ловушка/")

    assert response.url == reverse("analytics:quality")


@pytest.mark.django_db
def test_review_returns_to_the_page_it_came_from(client) -> None:
    """Со своей страницы возврат идёт туда же, откуда пришли."""
    _usual()
    report = make_day(12, in_work=329.0, closed=7950.0)
    recheck(report)
    check = CrossCheck.objects.filter(report=report).first()

    groups = ensure_roles()
    operator = User.objects.create_user(username="citu", password="x" * 14)
    operator.groups.add(groups[Role.FIELD.value])
    client.force_login(operator)

    came_from = reverse("reports:detail", args=[report.date])
    response = client.post(reverse("analytics:reviewed", args=[check.pk]),
                           HTTP_REFERER=came_from)

    assert response.url == came_from
