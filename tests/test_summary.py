# -*- coding: utf-8 -*-
"""Проверки сводок за период.

Главное здесь — не арифметика, а честность: сводка обязана сказать,
за сколько суток из скольких она посчитана. Сумма за месяц, собранная
из двадцати семи суток вместо тридцати одних, — не месячная сумма.
"""
from __future__ import annotations

from datetime import date
from unittest import mock

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.analytics import periods, summary
from apps.decks import services as deck_services
from apps.decks.models import Download
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


def test_custom_period_shifts_by_its_own_length() -> None:
    """Соседний произвольный период — такой же длины.

    Этой ветки не было, и `shift` бросал ValueError на любом
    произвольном периоде.
    """
    period = periods.custom(date(2026, 8, 1), date(2026, 8, 10))

    assert periods.shift(period, -1).start == date(2026, 7, 22)
    assert periods.shift(period, 1).end == date(2026, 8, 20)


def test_absurd_period_is_shortened_and_marked() -> None:
    """Период длиннее двух лет укорачивается и помечается.

    Полнота данных перечисляет каждые пропущенные сутки поимённо,
    поэтому диапазон в двести лет превращал страницу в пару мегабайт.
    """
    period = periods.custom(date(1900, 1, 1), date(2100, 12, 31))

    assert period.clamped is True
    assert period.days == periods.MAX_CUSTOM_DAYS


def test_usual_period_is_not_shortened() -> None:
    """Обычный период не трогается и не помечается."""
    period = periods.custom(date(2026, 1, 1), date(2026, 3, 31))

    assert period.clamped is False
    assert period.end == date(2026, 3, 31)


def test_query_restores_the_period() -> None:
    """Ссылка «предыдущий» не подменяет произвольный период месяцем."""
    assert periods.custom(date(2026, 8, 1), date(2026, 8, 10)).query == (
        "start=2026-08-01&end=2026-08-10")
    assert periods.period_of("month", date(2026, 8, 5)).query == (
        "kind=month&on=2026-08-01")


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
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
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


@pytest.mark.django_db
@pytest.mark.parametrize("page", ["analytics:summary", "analytics:quality"])
def test_pages_survive_a_custom_period(client, page: str) -> None:
    """Обе страницы открываются на произвольном периоде.

    Страница качества данных на нём падала с ошибкой сервера: она
    просит соседний период, а для произвольного такой ветки не было.
    """
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)

    response = client.get(reverse(page),
                          {"start": "2026-08-01", "end": "2026-08-31"})
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("page", ["analytics:summary", "analytics:quality"])
def test_pages_survive_an_absurd_period(client, page: str) -> None:
    """Период в двести лет не превращает страницу в мегабайты."""
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)

    response = client.get(reverse(page),
                          {"start": "1900-01-01", "end": "2100-12-31"})
    assert response.status_code == 200
    assert len(response.content) < 300 * 1024


# --- лист А3 -----------------------------------------------------------------
@pytest.mark.django_db
def test_sheet_is_given_out_and_recorded(client) -> None:
    """Лист А3 за период выдаётся по кнопке и попадает в журнал выдач.

    Лист собирается на каждое обращение и в хранилище не оседает:
    сочетаний периодов не перечесть. Поэтому в журнале он отмечается
    без ссылки на сутки — суток у него нет.
    """
    for day in range(1, 32):
        _day(day)
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("analytics:summary_sheet"),
                          {"kind": "month", "on": "2026-08-01"})
    assert response.status_code == 200

    record = Download.objects.get()
    assert record.kind == Download.Kind.SHEET
    assert record.report is None
    response.close()


@pytest.mark.django_db
def test_sheet_survives_an_empty_period(client) -> None:
    """Период без единых суток даёт лист, а не ошибку сервера."""
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("analytics:summary_sheet"),
                          {"kind": "month", "on": "2026-08-01"})
    assert response.status_code == 200
    response.close()


@pytest.mark.django_db
def test_sheet_without_libreoffice_says_so(client) -> None:
    """Без LibreOffice выдача в PDF объясняет причину, а не падает.

    Ветка сообщения обращается к модулю сообщений Django, и её
    единственная опечатка видна только здесь: в обычной работе
    LibreOffice на месте и ветка не исполняется.
    """
    for day in range(1, 32):
        _day(day)
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)

    with mock.patch.object(deck_services, "to_pdf",
                           side_effect=RuntimeError("LibreOffice не найден")):
        response = client.get(
            reverse("analytics:summary_sheet_format", args=["pdf"]),
            {"kind": "month", "on": "2026-08-01"}, follow=True)

    assert response.status_code == 200
    assert "LibreOffice не найден" in response.content.decode()


@pytest.mark.django_db
def test_days_are_counted_with_a_noun(client) -> None:
    """Рядом с числом суток стоит само слово «суток».

    Встроенный фильтр ``pluralize`` рассчитан на два варианта, а при
    трёх, как в русском, молча возвращал пустую строку: страница
    выводила «31 из 31» без существительного.
    """
    for day in range(1, 32):
        _day(day)
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)

    page = client.get(reverse("analytics:summary"),
                      {"kind": "month", "on": "2026-08-01"}).content.decode()
    assert "из 31 суток" in page, "существительное со счётом пропало"


@pytest.mark.django_db
def test_long_gap_lists_are_replaced_by_a_summary(client) -> None:
    """Сотни пропущенных суток не перечисляются поимённо.

    Перечень полезен, пока пропусков немного: «нет данных за 07.08,
    08.08, 19.08» — это указание, что проверить. Две сотни дат за год
    ничего не проясняют и занимают пол-экрана.
    """
    for day in range(1, 32):
        _day(day)
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)

    # Переносы строк в разметке значения не имеют: сравнивается текст.
    page = " ".join(client.get(
        reverse("analytics:summary"),
        {"kind": "year", "on": "2026-08-01"}).content.decode().split())
    assert "Данные есть с 01.08.2026 по 31.08.2026" in page
    assert "Нет данных за:" not in page, "перечень дат остался"


@pytest.mark.django_db
def test_short_gap_list_names_the_days(client) -> None:
    """Несколько пропусков по-прежнему называются поимённо."""
    for day in range(1, 32):
        if day in (7, 8, 19):
            continue
        _day(day)
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)

    page = client.get(reverse("analytics:summary"),
                      {"kind": "month", "on": "2026-08-01"}).content.decode()
    assert "Нет данных за:" in page
    assert "07.08" in page and "19.08" in page


# --- период, который ещё не наступил -----------------------------------------
@pytest.mark.django_db
def test_future_period_is_not_complete() -> None:
    """Будущий период полным не считается.

    Ни одних суток такого периода ещё не ожидается, пропусков поэтому
    нет, и «полнота» получалась сама собой: сводка за будущий квартал
    объявляла себя полной. Полным может быть только начавшийся период.
    """
    result = summary.completeness(periods.period_of("month",
                                                    date(2026, 10, 1)),
                                  today=date(2026, 9, 17))

    assert result["started"] is False
    assert result["complete"] is False
    assert result["expected"] == 0 and result["present"] == 0


@pytest.mark.django_db
def test_past_period_without_data_is_incomplete() -> None:
    """Прошедший период без данных неполон, а не «не начался».

    Разница существенная: за январь данные могли быть и не загружены,
    а за будущий октябрь их не может быть в принципе.
    """
    result = summary.completeness(periods.period_of("month",
                                                    date(2026, 1, 1)),
                                  today=date(2026, 9, 17))

    assert result["started"] is True
    assert result["complete"] is False
    assert result["expected"] == 31 and result["present"] == 0


@pytest.mark.django_db
def test_future_period_page_says_it_has_not_started(client) -> None:
    """Страница будущего периода говорит, что он не начался."""
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)

    page = client.get(reverse("analytics:summary"),
                      {"kind": "month", "on": "2026-12-01"}).content.decode()

    assert "Период ещё не начался" in page
    assert "Данные за период полные" not in page


@pytest.mark.django_db
def test_losses_without_data_are_a_dash(client) -> None:
    """Потери за период без данных — прочерк, а не ноль.

    «Нет данных» и «ноль» — разные вещи: ноль утверждает, что потерь
    не было, хотя суток не было вовсе.
    """
    period = periods.period_of("month", date(2026, 12, 1))
    result = summary.losses(period)

    assert result["total"] is None
    assert result["has_data"] is False

    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)
    page = client.get(reverse("analytics:summary"),
                      {"kind": "month", "on": "2026-12-01"}).content.decode()
    assert "складывать нечего" in page


@pytest.mark.django_db
def test_empty_period_draws_no_chart(client) -> None:
    """У периода без данных не рисуется пустая сетка графика.

    График без единой точки, но с виду настоящий, — хуже отсутствия
    графика: он выглядит как утверждение о нулях.
    """
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)

    page = client.get(reverse("analytics:summary"),
                      {"kind": "month", "on": "2026-12-01"}).content.decode()

    assert 'id="chart-daily"' not in page
    assert "нет ни одних суток с данными" in page


@pytest.mark.django_db
def test_quality_page_does_not_call_a_future_period_complete(client) -> None:
    """Страница качества данных тоже не считает будущий период полным."""
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)

    page = " ".join(client.get(
        reverse("analytics:quality"),
        {"kind": "month", "on": "2026-12-01"}).content.decode().split())

    assert "период ещё не начался" in page
    # Плитка полноты не должна быть зелёной. Ищется именно она:
    # зелёные плитки на странице есть и по другим поводам.
    start = page.index("Полнота данных")
    tile = page[page.rindex("<div class=\"tile", 0, start):start]
    assert "tile--good" not in tile, "полнота отмечена как благополучная"


@pytest.mark.django_db
def test_gas_deviation_is_a_difference_not_the_fact() -> None:
    """В столбце «±» баланса газа стоит отклонение, а не сам факт.

    Шаблон выводил в этот столбец повторно факт: под заголовком «±»
    читателю показывалось то же число, что и в соседней графе.
    """
    from apps.reports.models import GasDaily

    report = _day(1)
    GasDaily.objects.create(report=report, kind=GasDaily.Kind.PRODUCTION,
                            day_plan=400.0, day_fact=412.5)

    row = summary.gas(periods.period_of("month", date(2026, 8, 1)))[0]

    assert row["fact"] == pytest.approx(412.5)
    assert row["plan"] == pytest.approx(400.0)
    assert row["dev"] == pytest.approx(12.5)


@pytest.mark.django_db
def test_gas_deviation_without_plan_is_empty() -> None:
    """Без плана отклонение не выдумывается."""
    from apps.reports.models import GasDaily

    report = _day(1)
    GasDaily.objects.create(report=report, kind=GasDaily.Kind.FLARE,
                            day_plan=None, day_fact=17.0)

    row = summary.gas(periods.period_of("month", date(2026, 8, 1)))[0]

    assert row["dev"] is None


# --- согласие чисел между собой ----------------------------------------------
@pytest.mark.django_db
def test_deviation_matches_the_numbers_shown_beside_it() -> None:
    """Отклонение равно разности величин в том виде, как они показаны.

    На дашборде стояло «Добыча 116 987, План БП 116 342, Отклонение
    +646»: настоящая разность 645,54 округлялась вверх, а слагаемые —
    вниз. Каждое число верно по отдельности, но таблицу нельзя
    проверить вычитанием, а доклад читают с листа.
    """
    _day(1, closed=116987.16, plan=116341.61585)
    period = periods.period_of("month", date(2026, 8, 1))

    result = summary.production(period)

    assert round(result["closed"]) - round(result["plan_bp"]) == (
        round(result["dev_bp"]))
    assert result["dev_bp"] == pytest.approx(645.0)


@pytest.mark.django_db
def test_deviation_without_a_plan_is_absent() -> None:
    """Без плана отклонение не выдумывается."""
    report = Report.objects.create(date=date(2026, 8, 1))
    ProductionDaily.objects.create(report=report, closed_day=8000.0)

    result = summary.production(periods.period_of("month", date(2026, 8, 1)))

    assert result["dev_bp"] is None
    assert result["dev_sg"] is None


@pytest.mark.django_db
def test_month_table_on_the_dashboard_adds_up(client) -> None:
    """Строки таблицы месяца на дашборде сходятся между собой."""
    _day(1, closed=116987.16, plan=116341.61585)
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)

    # split() без аргумента разбивает и по неразрывному пробелу,
    # поэтому разряды чисел сравниваются с обычным пробелом.
    page = " ".join(client.get(
        reverse("analytics:dashboard")).content.decode().split())

    assert "116 987" in page
    assert "116 342" in page
    assert "+645" in page, "отклонение не сходится с показанными числами"
