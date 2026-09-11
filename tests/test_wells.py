# -*- coding: utf-8 -*-
"""Проверки истории скважины.

Суточный рапорт показывает срез на одни сутки. Здесь проверяется то,
что появляется только при наличии истории: отрезки простоя, накопленные
потери и остановки вскоре после ремонта.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.catalog.models import Field, Well
from apps.reports import wells
from apps.reports.models import ProductionDaily, Report, WellDaily

START = date(2026, 8, 1)


@pytest.fixture
def well(db) -> Well:
    """Скважина на месторождении."""
    field = Field.objects.create(name="Висовое")
    return Well.objects.create(number="2504", field=field)


def day(offset: int) -> Report:
    """Сутки, за которые есть рапорт."""
    report, _created = Report.objects.get_or_create(
        date=START + timedelta(days=offset))
    ProductionDaily.objects.get_or_create(report=report,
                                          defaults={"closed_day": 8300.0})
    return report


def entry(well: Well, offset: int, category: str = "downtime",
          qo: float = 27.5, reason: str = "КРС",
          stop: date | None = None, repair: date | None = None) -> WellDaily:
    """Запись о скважине за одни сутки."""
    return WellDaily.objects.create(
        report=day(offset), well=well, category=category, qo=qo,
        reason=reason, stop_date=stop, last_repair=repair)


# --- итоги -------------------------------------------------------------------
@pytest.mark.django_db
def test_totals_accumulate_over_time(well: Well) -> None:
    """Потери складываются за всё время наблюдения."""
    for offset in range(4):
        entry(well, offset, qo=10.0)

    result = wells.totals(well)
    assert result["qo"] == pytest.approx(40.0)
    assert result["days"] == 4
    assert result["first"] == START
    assert result["last"] == START + timedelta(days=3)


@pytest.mark.django_db
def test_totals_split_by_list(well: Well) -> None:
    """Итоги разложены по спискам, в которых стояла скважина."""
    entry(well, 0, category="downtime", qo=10.0)
    entry(well, 1, category="idle", qo=5.0)

    labels = {item["label"]: item["qo"]
              for item in wells.totals(well)["by_category"]}
    assert labels["Текущий простой"] == pytest.approx(10.0)
    assert labels["Бездействие"] == pytest.approx(5.0)


# --- отрезки -----------------------------------------------------------------
@pytest.mark.django_db
def test_consecutive_days_become_one_spell(well: Well) -> None:
    """Подряд идущие сутки объединяются в один отрезок.

    «Стояла с 1 по 5 августа» читается лучше пяти одинаковых строк.
    """
    for offset in range(5):
        entry(well, offset, qo=10.0)

    found = wells.spells(well)
    assert len(found) == 1
    assert found[0].days == 5
    assert found[0].start == START
    assert found[0].end == START + timedelta(days=4)
    assert found[0].qo == pytest.approx(50.0)


@pytest.mark.django_db
def test_gap_breaks_the_spell(well: Well) -> None:
    """Пропуск суток разрывает отрезок, а не склеивает его."""
    entry(well, 0)
    entry(well, 1)
    entry(well, 5)

    found = wells.spells(well)
    assert len(found) == 2
    assert found[0].start == START + timedelta(days=5), "порядок не от новых"
    assert found[1].days == 2


@pytest.mark.django_db
def test_change_of_list_breaks_the_spell(well: Well) -> None:
    """Переход из простоя в бездействие — новый отрезок."""
    entry(well, 0, category="downtime")
    entry(well, 1, category="idle")

    found = wells.spells(well)
    assert len(found) == 2
    assert {item.category for item in found} == {"downtime", "idle"}


# --- остановки после ремонта -------------------------------------------------
@pytest.mark.django_db
def test_stop_soon_after_repair_is_found(well: Well) -> None:
    """Остановка вскоре после ремонта попадает в перечень."""
    entry(well, 0, stop=date(2026, 8, 7), repair=date(2026, 6, 29))

    found = wells.stops_after_repair(well)
    assert len(found) == 1
    assert found[0].days_after == 39


@pytest.mark.django_db
def test_old_repair_is_not_counted(well: Well) -> None:
    """Ремонт годичной давности к остановке не притягивается."""
    entry(well, 0, stop=date(2026, 8, 7), repair=date(2022, 2, 8))
    assert wells.stops_after_repair(well) == []


@pytest.mark.django_db
def test_repair_after_the_stop_is_not_counted(well: Well) -> None:
    """Ремонт, случившийся позже остановки, перечень не пополняет."""
    entry(well, 0, stop=date(2026, 8, 1), repair=date(2026, 8, 20))
    assert wells.stops_after_repair(well) == []


@pytest.mark.django_db
def test_same_stop_counted_once(well: Well) -> None:
    """Одна остановка, повторённая в тридцати рапортах, — один случай."""
    for offset in range(30):
        entry(well, offset, stop=date(2026, 8, 1), repair=date(2026, 7, 1))
    assert len(wells.stops_after_repair(well)) == 1


@pytest.mark.django_db
def test_reason_is_returned_with_the_stop(well: Well) -> None:
    """Причина возвращается рядом с датами.

    Связь остановки с ремонтом из этих данных не следует: среди таких
    случаев есть и плановые, вроде вывода на КВД. Судит человек,
    и для этого ему нужна причина.
    """
    entry(well, 0, stop=date(2026, 8, 7), repair=date(2026, 6, 29),
          reason="КВД")
    assert wells.stops_after_repair(well)[0].reason == "КВД"


# --- график ------------------------------------------------------------------
@pytest.mark.django_db
def test_working_days_stay_empty_on_the_chart(well: Well) -> None:
    """Сутки, когда скважина работала, остаются пустыми.

    Ноль потерь и отсутствие скважины в списках — разные вещи.
    """
    entry(well, 0, qo=10.0)
    entry(well, 2, qo=12.0)

    series = wells.series(well)
    assert series["labels"] == ["01.08", "02.08", "03.08"]
    assert series["values"] == [10.0, None, 12.0]


# --- перечень ----------------------------------------------------------------
@pytest.mark.django_db
def test_ranking_orders_by_accumulated_losses(well: Well) -> None:
    """Скважины упорядочены по накопленным потерям."""
    other = Well.objects.create(number="3602", field=well.field)
    entry(well, 0, qo=10.0)
    entry(other, 0, qo=90.0)

    rows = wells.ranking()
    assert rows[0]["well__number"] == "3602"
    assert rows[0]["qo"] == pytest.approx(90.0)


@pytest.mark.django_db
def test_ranking_filters_by_number(well: Well) -> None:
    """Отбор по части номера скважины работает."""
    other = Well.objects.create(number="3602", field=well.field)
    entry(well, 0)
    entry(other, 0)

    rows = wells.ranking(search="2504")
    assert len(rows) == 1
    assert rows[0]["well__number"] == "2504"


# --- страницы ----------------------------------------------------------------
@pytest.mark.django_db
def test_well_page_states_fact_not_cause(client, well: Well) -> None:
    """Страница не приписывает остановку ремонту.

    Утверждать причину по этим данным нельзя, и страница об этом
    говорит прямо.
    """
    entry(well, 0, stop=date(2026, 8, 7), repair=date(2026, 6, 29),
          reason="КВД")
    user = User.objects.create_user(username="chief", password="x" * 14)
    client.force_login(user)

    page = client.get(reverse("reports:well", args=[well.pk])).content.decode()
    assert "Остановки вскоре после ремонта" in page
    assert "не следует" in page, "нет оговорки о том, что связь не доказана"
    assert "КВД" in page, "причина не показана рядом"


@pytest.mark.django_db
def test_well_list_requires_login(client) -> None:
    """Перечень скважин закрыт от посторонних."""
    response = client.get(reverse("reports:wells"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


@pytest.mark.django_db
def test_unknown_well_gives_404(client) -> None:
    """Несуществующая скважина не даёт пустую страницу."""
    user = User.objects.create_user(username="chief", password="x" * 14)
    client.force_login(user)
    assert client.get(
        reverse("reports:well", args=[999999])).status_code == 404
