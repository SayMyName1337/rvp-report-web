# -*- coding: utf-8 -*-
"""Проверки поведения при нечисловых значениях в исходных данных.

Ячейка рапорта может содержать сохранённый результат формулы, который
не является числом: NaN или бесконечность. Такое значение опаснее
пустоты. Пустота видна сразу — на её месте прочерк; NaN же выглядит
числом и ведёт себя как число до первого сравнения: сумма с ним
обращается в NaN, любое сравнение молча даёт ложь, а в данных графика
NaN — недопустимая запись JSON, на которой разбор в браузере
останавливается и пропадают все диаграммы страницы разом.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.reports.models import ProductionDaily, Report
from apps.reports.templatetags.rvp import num, share, signed
from rvp_report.excel.reader import _num

#: Значения, которые не являются числами с точки зрения арифметики.
NOT_NUMBERS = (float("nan"), float("inf"), float("-inf"), "nan", "inf",
               "-inf", "NaN", "Infinity")


# --- разбор ------------------------------------------------------------------
@pytest.mark.parametrize("value", NOT_NUMBERS)
def test_parser_treats_non_numbers_as_missing(value) -> None:
    """Разбор считает NaN и бесконечность отсутствующим значением."""
    assert _num(value) is None


@pytest.mark.parametrize("value,expected", [
    (8351.8, 8351.8), ("1 234,5", 1234.5), ("<4", 4.0), (0, 0.0),
])
def test_parser_still_reads_ordinary_numbers(value, expected: float) -> None:
    """Обычные значения читаются как прежде."""
    assert _num(value) == pytest.approx(expected)


# --- вывод -------------------------------------------------------------------
@pytest.mark.parametrize("value", [float("nan"), float("inf"),
                                   float("-inf")])
def test_filters_show_a_dash_instead_of_nan(value) -> None:
    """На странице вместо «nan» стоит прочерк.

    Значение могло попасть в базу до того, как разбор стал их отсеивать,
    и выводиться оно обязано как отсутствующее.
    """
    assert num(value, 1) == "—"
    assert signed(value, 1) == "—"
    assert share(value, 100) == "—"


# --- график ------------------------------------------------------------------
@pytest.mark.django_db
def test_nan_in_the_base_does_not_break_the_charts(client) -> None:
    """NaN в базе не превращает данные графика в негодный JSON.

    Проверяется именно разбираемость: JSON с записью NaN браузер
    не читает, и вместе с одной точкой пропадают все диаграммы
    страницы.
    """
    report = Report.objects.create(date=date(2026, 8, 1))
    ProductionDaily.objects.create(report=report, closed_day=float("nan"),
                                   plan_bp_day=8100.0, plan_sg_day=8100.0)
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)

    page = client.get(reverse("analytics:summary"),
                      {"kind": "month", "on": "2026-08-01"}).content.decode()

    start = page.index('id="data-daily"')
    body = page[page.index(">", start) + 1:page.index("</script>", start)]
    data = json.loads(body, parse_constant=_reject)
    assert data["fact"][0] is None, "NaN дошёл до данных графика"


def _reject(token: str):
    """Обработчик особых записей JSON: их быть не должно."""
    raise AssertionError(f"в данных графика недопустимая запись «{token}»")
