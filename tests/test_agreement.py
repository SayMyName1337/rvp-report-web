# -*- coding: utf-8 -*-
"""Согласие двух источников: файла рапорта и базы данных.

Устройство системы двоякое намеренно. Презентация доклада собирается
**из исходного файла**, минуя базу: так слайды заведомо совпадают с тем,
что проверил начальник ЦИТУ. Страницы, сводки и дашборд считаются
**из базы**: файл за период не существует.

Отсюда и риск, которого нет у систем с одним источником. Если разбор
прочитает одно, а запись в базу сохранит другое, главный инженер
увидит на слайде одну цифру, а на экране рядом — другую, и ни одна
проверка разбора или страницы этого не заметит: каждая из них права
по-своему.

Поэтому здесь сверяются именно два пути одного и того же показателя.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from apps.reports.loader import store
from apps.reports.models import Report

from .conftest import load

#: Допуск сравнения. Величины хранятся как есть, без округления,
#: поэтому расхождение возможно только из-за представления числа.
TOLERANCE = 0.001


def _same(first, second) -> bool:
    """Совпадают ли две величины с точностью до допуска."""
    if first is None and second is None:
        return True
    if first is None or second is None:
        return False
    return abs(float(first) - float(second)) <= TOLERANCE


@pytest.mark.django_db
def test_stored_values_match_the_file(report_path: Path) -> None:
    """Каждый ключевой показатель в базе равен прочитанному из файла.

    Проверяются показатели, которые попадают и на слайд доклада,
    и на страницу: расхождение между ними заметит главный инженер
    на совещании, а не разработчик.
    """
    daily = load(report_path)
    report: Report = store(daily, [])

    checks = [
        ("добыча, закрытые сутки", daily.production.closed_day,
         report.production.closed_day),
        ("план БП за сутки", daily.production.plan_bp_day,
         report.production.plan_bp_day),
        ("план СГ за сутки", daily.production.plan_sg_day,
         report.production.plan_sg_day),
        ("нарастающий итог месяца", daily.production.cumulative_month,
         report.production.cumulative_month),
        ("сдача нефти", daily.delivery.fact_day, report.delivery.fact_day),
        ("выработка электроэнергии", daily.power.total_with_psp,
         report.power.total_with_psp),
        ("обращений в здравпункт", daily.hse.medical_count,
         report.hse.medical_count),
        ("происшествий", len(daily.hse.incidents),
         report.hse.incidents_count),
    ]

    wrong = [f"{name}: в файле {from_file}, в базе {from_db}"
             for name, from_file, from_db in checks
             if not _same(from_file, from_db)]
    assert not wrong, (
        f"{report_path.name}: база расходится с файлом — " + "; ".join(wrong))


@pytest.mark.django_db
def test_stored_losses_match_the_file(report_path: Path) -> None:
    """Составляющие потерь в базе равны прочитанным из файла.

    Потери — расчётная величина, и на слайде она раскрывается
    слагаемыми. Слагаемые обязаны быть теми же самыми.
    """
    daily = load(report_path)
    report: Report = store(daily, [])
    stored = {item.category: item.qo for item in report.well_totals.all()}

    pairs = [
        ("текущий простой", daily.downtime_total, stored.get("downtime")),
        ("бездействие", daily.idle_total, stored.get("idle")),
        ("внутрисменные потери", daily.vsp_total, stored.get("vsp")),
    ]
    for name, from_file, from_db in pairs:
        if from_file is None:
            continue
        assert _same(from_file.qo, from_db), (
            f"{report_path.name}: {name} — в файле {from_file.qo}, "
            f"в базе {from_db}")


@pytest.mark.django_db
def test_well_lists_are_stored_completely(report_path: Path) -> None:
    """Скважины из перечней доходят до базы все до одной.

    Потерянная при записи строка не видна ни на слайде (он собирается
    из файла), ни в сводке (она не знает, сколько строк ожидалось),
    а история скважины от этого становится неполной.
    """
    daily = load(report_path)
    report: Report = store(daily, [])

    # Групповые записи вида «76 скважин» по скважинам не разносятся
    # и хранятся отдельно — они считаются вместе с ними.
    expected = (len(daily.downtime) + len(daily.idle) + len(daily.vsp)
                + len(daily.startups))
    stored = report.wells.count() + report.group_events.count()

    # Строка может не дойти до базы по двум законным причинам: скважина
    # повторяется в одном списке дважды либо её номер не удалось
    # разобрать. Обе сопровождаются замечанием — молча теряться строка
    # не имеет права.
    explained = report.issues.filter(
        where__icontains="скважин").count() + report.issues.filter(
        message__icontains="скв.").count()

    assert stored + explained >= expected, (
        f"{report_path.name}: в файле {expected} строк по скважинам, "
        f"в базе {stored}, замечаний о потерянных строках {explained}")
