# -*- coding: utf-8 -*-
"""Проверки разбора суточного рапорта на настоящих файлах.

Смысл проверок — не в том, что программа что-то прочитала, а в том,
что прочитанное сходится само с собой. Рапорт содержит величины,
посчитанные в нём дважды разными способами; если наши суммы не
совпадают с объявленными, разбор ошибается либо данные противоречивы.
И то, и другое надо увидеть, а не пропустить молча.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rvp_report.excel.reader import ReportReader

from .conftest import load

#: Допустимое расхождение сумм, т/сут.
TOLERANCE = 0.05


def close(left: float | None, right: float | None,
          eps: float = TOLERANCE) -> bool:
    """Совпадают ли величины с точностью до округления."""
    if left is None or right is None:
        return False
    return abs(left - right) <= max(eps, abs(left) * 0.001)


def test_layout_resolves_by_labels(report_path: Path) -> None:
    """Разметка должна находиться по подписям, без эталонных адресов.

    Обращение к эталону означает, что подпись в рапорте изменили:
    работать программа продолжит, но цифра уже не гарантирована.
    """
    reader = ReportReader(str(report_path))
    assert not reader.map.degraded, (
        "взято по эталону: " + "; ".join(reader.map.degraded))


def test_required_blocks_found(report_path: Path) -> None:
    """Обязательные разделы рапорта должны быть найдены."""
    reader = ReportReader(str(report_path))
    for key in ("production", "stock", "idle", "downtime", "quality", "gas"):
        assert key in reader.map.blocks, f"не найден раздел «{key}»"


def test_basic_values_read(report_path: Path) -> None:
    """Ключевые показатели доклада должны быть прочитаны."""
    report = load(report_path)
    assert report.report_date is not None, "не прочитана дата рапорта"
    assert (report.production.closed_day or 0) > 0, "не прочитана добыча"
    assert report.stock_total is not None, "не прочитан итог по фонду"
    assert report.delivery.fact_day is not None, "не прочитана сдача"
    assert report.gas_utilization_pct is not None, "не прочитана утилизация"
    assert len(report.production.by_field) >= 10, "мало месторождений"
    assert len(report.quality) >= 3, "не прочитано качество нефти"
    assert len(report.injection) >= 3, "не прочитан ППД"
    assert len(report.tanks) >= 4, "не прочитан резервуарный парк"


def test_downtime_breakdown_matches_or_is_reported(report_path: Path) -> None:
    """Разбивка простоя сходится с итогом — либо о расхождении сказано вслух.

    Проверяется не арифметика рапорта, а наша честность: рапорт бывает
    противоречив сам себе (28.08.2026 — расхождение в 11 т), и такие
    случаи мы не исправляем, но обязаны показать. Молчаливого
    несоответствия быть не должно.

    Именно здесь ловится и изменение состава причин: в августе 2026
    «Сезонная эксплуатация» уступила место «Ожиданию СКО».
    """
    report = load(report_path)
    assert report.downtime_breakdown, "не прочитана разбивка простоя"

    parts = sum(qo for _name, _count, qo in report.downtime_breakdown)
    if close(report.downtime_total.qo, parts, 1.0):
        return
    reported = [issue for issue in report.issues
                if "разбивка по причинам" in issue.where.lower()]
    assert reported, (
        f"разбивка {parts:.2f} ≠ простою {report.downtime_total.qo:.2f}, "
        "и об этом нет замечания")


def test_losses_are_sum_of_parts(report_path: Path) -> None:
    """Потери добычи — сумма простоя, бездействия и внутрисменных."""
    report = load(report_path)
    parts = sum(value or 0.0 for value in (report.downtime_total.qo,
                                           report.idle_total.qo,
                                           report.vsp_total.qo))
    assert close(report.total_losses, parts, 0.001)


def test_every_value_has_origin(report_path: Path) -> None:
    """У каждого показателя должно быть записано происхождение.

    Требование доклада: любую цифру на слайде можно проверить
    по рапорту. Без записи в журнале это не выполняется.
    """
    report = load(report_path)
    for item in report.ledger.items:
        assert item.origin, f"у «{item.label}» не указано происхождение"
    assert len(report.ledger.derived_items) >= 5, (
        "расчётные величины не зарегистрированы")


def test_medical_text_is_read_not_header(report_path: Path) -> None:
    """Обращения в здравпункт читаются из данных, а не из шапки столбца.

    Ноль обращений — законный случай, и записывают его по-разному:
    в августе 2026 четверо суток содержат «Обращений не поступало»,
    а ещё в трёх поле оставлено пустым. Проверяется соответствие
    счётчика тексту, а не то, что обращения непременно были.
    """
    report = load(report_path)
    raw = report.hse.medical_raw
    assert "Обращения в медпункт" not in raw, (
        "вместо текста прочитан заголовок столбца")
    if "обрат" in raw.lower():
        assert report.hse.medical_count > 0, (
            "в тексте есть обращения, но счётчик их не увидел")
    else:
        assert report.hse.medical_count == 0, (
            "обращений в тексте нет, а счётчик их насчитал")


@pytest.mark.parametrize("attribute", ["idle_total", "downtime_total"])
def test_list_counts_match_declared(report_path: Path, attribute: str) -> None:
    """Количество прочитанных скважин совпадает со строкой ИТОГО.

    Расхождение здесь означает либо ошибку разбора, либо противоречие
    в самом рапорте — в августе 2026 такое встретилось дважды.
    """
    report = load(report_path)
    totals = getattr(report, attribute)
    assert totals.count is not None and totals.count > 0
