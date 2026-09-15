# -*- coding: utf-8 -*-
"""Проверки записи разобранного рапорта в базу."""
from __future__ import annotations

from pathlib import Path

import pytest

from apps.accounts.models import User
from apps.reports.loader import (WELL_NUMBER, missing_names, store)
from apps.reports.models import (DeliveryDaily, GroupEvent, PowerDaily,
                                 ProductionDaily, Report, StockDaily,
                                 WellDaily)
from rvp_report.domain.model import Delivery, PowerState, Production, StockRow

from .conftest import load, report_files


@pytest.mark.parametrize("text", ["32201", "9Р", "13р", "1П", "44119", "2"])
def test_well_numbers_are_recognised(text: str) -> None:
    """Номер скважины — цифры и, возможно, одна буква."""
    assert WELL_NUMBER.match(text)


@pytest.mark.parametrize("text", [
    "76 скважин", "куст №1", "12 Скважин к.№2", "1102, 1110", "КП-6", "",
])
def test_group_rows_are_not_well_numbers(text: str) -> None:
    """Групповая запись не должна приниматься за номер скважины."""
    assert not WELL_NUMBER.match(text)


@pytest.mark.parametrize("model,structure", [
    (ProductionDaily, Production),
    (DeliveryDaily, Delivery),
    (PowerDaily, PowerState),
    (StockDaily, StockRow),
])
def test_model_fields_match_parsed_structure(model, structure) -> None:
    """Имена полей модели должны совпадать с именами в разборе.

    Перекладка идёт по именам, поэтому расхождение означало бы, что
    показатель молча перестал записываться.
    """
    assert not missing_names(model, structure), (
        f"в {structure.__name__} нет полей: "
        + ", ".join(missing_names(model, structure)))


@pytest.fixture
def sample() -> Path:
    """Один рапорт для проверок записи."""
    files = report_files()
    if not files:
        pytest.skip("нет рапортов для проверки")
    return files[0]


@pytest.mark.django_db
def test_load_is_idempotent(sample: Path) -> None:
    """Повторная загрузка за ту же дату заменяет данные, а не удваивает.

    Рапорт присылают с исправлениями, и это обычный ход дела.
    """
    daily = load(sample)
    first = store(daily, [])
    counts = (WellDaily.objects.count(), GroupEvent.objects.count(),
              StockDaily.objects.count())

    second = store(daily, [])
    assert second.pk == first.pk, "сутки не должны раздвоиться"
    assert Report.objects.count() == 1
    assert (WellDaily.objects.count(), GroupEvent.objects.count(),
            StockDaily.objects.count()) == counts


@pytest.mark.django_db
def test_losses_exclude_movement(sample: Path) -> None:
    """Потери — это простой, бездействие и внутрисменные, и только они.

    Запуски и остановки — движение фонда, а не потери. Включив их,
    показатель доклада завысился бы: за 31.08.2026 вышло бы 1 994 т
    вместо 1 725 т.
    """
    daily = load(sample)
    report = store(daily, [])

    expected = sum(value or 0.0 for value in (daily.downtime_total.qo,
                                              daily.idle_total.qo,
                                              daily.vsp_total.qo))
    assert abs(report.total_losses - expected) < 0.01

    everything = sum(item.qo or 0.0 for item in report.well_totals.all())
    assert report.total_losses <= everything


@pytest.mark.django_db
def test_group_rows_go_to_events(sample: Path) -> None:
    """Строки вида «76 скважин» не должны становиться скважинами."""
    store(load(sample), [])
    for well in WellDaily.objects.select_related("well"):
        assert WELL_NUMBER.match(well.well.number), (
            f"«{well.well.number}» попало в скважины, а это групповая запись")


@pytest.mark.django_db
def test_degraded_layout_marks_report_for_review(sample: Path) -> None:
    """Показатель, взятый по эталону, переводит сутки в «требуют проверки».

    Пока такой показатель не подтверждён, сутки помечены, и цифра
    не выдаётся за проверенную.
    """
    report = store(load(sample), ["показатель «Прогноз сдачи» не найден"])
    assert report.status == Report.Status.NEEDS_REVIEW

    clean = store(load(sample), [])
    assert clean.status == Report.Status.LOADED


@pytest.mark.django_db
def test_abbreviations_are_reported_on_empty_catalog(sample: Path) -> None:
    """При пустом справочнике сокращения должны быть замечены.

    В блоке бурения месторождения пишут сокращённо — «СХ», «С.Ошк».
    Загрузка заводит их как новые, но обязана сказать об этом:
    иначе история месторождения разойдётся по двум записям молча.
    """
    report = store(load(sample), [])
    hints = report.issues.filter(where="Справочники")
    assert hints.exists(), "о сокращениях не сказано ни слова"
    assert any("похоже на сокращение" in issue.message for issue in hints)


@pytest.mark.django_db
def test_upload_becomes_current(sample: Path) -> None:
    """Действующей считается последняя успешная загрузка за дату."""
    from apps.reports.models import Upload

    user = User.objects.create_user(username="citu", password="x" * 14,
                                    must_change_password=False)
    daily = load(sample)

    first = Upload.objects.create(uploaded_by=user, original_name="а.xlsx",
                                  sha256="a" * 64, size=1)
    store(daily, [], first)
    second = Upload.objects.create(uploaded_by=user, original_name="б.xlsx",
                                   sha256="b" * 64, size=1)
    store(daily, [], second)

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.is_current is False
    assert second.is_current is True
    assert Upload.objects.filter(is_current=True).count() == 1
