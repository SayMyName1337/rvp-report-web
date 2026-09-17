# -*- coding: utf-8 -*-
"""Сверка суток с соседними.

Проверки внутри суток ловят противоречия рапорта самому себе: список
не сходится с итогом, разбивка — с простоем. Но рапорт бывает
непротиворечив и при этом неправдоподобен.

Так было 21.08.2026: фонд «в работе» показал 329 скважин вместо
обычных 253, простой — 11 вместо 84–87, и при этом добыча оказалась
самой низкой за месяц. Внутри суток всё сходилось; увидеть это можно
было только рядом с соседними днями.

Здесь собраны четыре правила, каждое ловит свой вид неправдоподобия:

* **скачок** — показатель резко изменился относительно прошлых суток;
* **уровень** — показатель ушёл далеко от привычного за две недели;
* **застыл** — значение не меняется несколько суток подряд;
* **противоречие** — фонд и добыча движутся в разные стороны.

Ни одно из них не объявляет данные ошибочными: они говорят «посмотрите
сюда». Решает человек.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from apps.reports.models import Report

#: Сколько прошлых суток берётся за «привычный уровень».
HISTORY_DAYS = 14

#: Сколько суток подряд с одинаковым значением считать застоем.
FROZEN_DAYS = 3

#: Во сколько раз отклонение должно превысить обычный разброс,
#: чтобы считаться выходом за уровень.
LEVEL_FACTOR = 5.0

#: Минимальный разброс, ниже которого правило «уровень» не работает:
#: у почти постоянного показателя любая мелочь выглядит выбросом.
MIN_SPREAD = 1e-6

#: Какую долю от порога скачка должно составлять отклонение от уровня,
#: чтобы о нём вообще стоило говорить.
LEVEL_MIN_SHARE = 0.75


@dataclass(frozen=True)
class Metric:
    """Показатель, за которым следят от суток к суткам."""

    key: str
    label: str
    unit: str
    jump: float                   # доля изменения, считающаяся скачком
    watch_frozen: bool = False    # должен ли показатель меняться каждые сутки


#: За чем следим.
#:
#: Пороги подобраны на августе 2026 так, чтобы правила срабатывали
#: на действительно необычных сутках. При первых порогах на 31 сутки
#: приходилось 75 замечаний — столько никто читать не станет, а среди
#: них теряется настоящее.
#:
#: Застой отслеживается только у величин, которые обязаны меняться
#: каждые сутки: добыча, потери, сдача, закачка, выработка. Количество
#: скважин в работе или в простое может не меняться неделю, и это
#: обычное дело, а не признак копипасты.
METRICS = (
    Metric("closed_day", "Добыча нефти", "т/сут", 0.08, watch_frozen=True),
    Metric("losses", "Потери добычи", "т/сут", 0.35, watch_frozen=True),
    Metric("in_work", "Фонд в работе", "скв.", 0.08),
    Metric("in_downtime", "В текущем простое", "скв.", 0.30),
    Metric("in_idle", "В бездействии", "скв.", 0.25),
    Metric("delivered", "Сдача нефти", "т/сут", 0.15, watch_frozen=True),
    Metric("injection", "Закачка ППД", "м³/сут", 0.30, watch_frozen=True),
    Metric("power", "Выработка Э/Э", "МВт·ч", 0.15, watch_frozen=True),
)

#: Насколько должен вырасти фонд и упасть добыча, чтобы это считалось
#: противоречием. Именно эта пара сработала на 21.08.2026.
CONTRADICTION_FUND = 0.05
CONTRADICTION_OUTPUT = 0.02


@dataclass(frozen=True)
class Finding:
    """Замечание, найденное сравнением с соседними сутками."""

    kind: str
    metric: str
    label: str
    message: str
    value: float | None = None
    baseline: float | None = None
    severity: str = "warning"


def _ru(value: float | None, digits: int = 1) -> str:
    """Число в русской записи для текста замечания."""
    if value is None:
        return "—"
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def sample(report: Report) -> dict:
    """Показатели одних суток, за которыми следит сверка.

    Args:
        report: Сутки.

    Returns:
        Соответствие «ключ показателя — значение». Отсутствующие
        показатели опускаются: считать по ним нечего.
    """
    values: dict[str, float] = {}
    production = getattr(report, "production", None)
    delivery = getattr(report, "delivery", None)
    power = getattr(report, "power", None)
    stock = report.stock.filter(is_total=True).first()

    if production is not None and production.closed_day is not None:
        values["closed_day"] = production.closed_day
    if delivery is not None and delivery.fact_day is not None:
        values["delivered"] = delivery.fact_day
    if power is not None and power.total_with_psp is not None:
        values["power"] = power.total_with_psp
    if stock is not None:
        for key in ("in_work", "in_downtime", "in_idle"):
            found = getattr(stock, key)
            if found is not None:
                values[key] = found

    losses = sum(item.qo or 0.0 for item in report.well_totals.all()
                 if item.category in Report.LOSS_CATEGORIES)
    if losses:
        values["losses"] = losses

    injection = report.injection.filter(is_total=True).first()
    if injection is not None and injection.fact_day is not None:
        values["injection"] = injection.fact_day
    return values


def history(day: date, days: int = HISTORY_DAYS) -> list[dict]:
    """Показатели предыдущих суток, от давних к недавним.

    Args:
        day: Сутки, для которых нужна история.
        days: Сколько суток назад смотреть.

    Returns:
        Список значений по суткам; пропущенные сутки просто отсутствуют.
    """
    since = day - timedelta(days=days)
    reports = (Report.objects
               .filter(date__gte=since, date__lt=day)
               .select_related("production", "delivery", "power")
               .prefetch_related("well_totals", "stock", "injection")
               .order_by("date"))
    return [sample(report) for report in reports]


def _spread(values: list[float]) -> float:
    """Обычный разброс значений — медиана отклонений от медианы.

    Устойчив к одиночному выбросу: одна необычная величина в истории
    не раздувает порог и не прячет следующую.
    """
    if len(values) < 3:
        return 0.0
    middle = median(values)
    return median([abs(value - middle) for value in values])


def _check_jump(metric: Metric, value: float, past: list[float]) -> Finding | None:
    """Резкое изменение относительно прошлых суток."""
    if not past:
        return None
    previous = past[-1]
    if not previous:
        return None
    change = (value - previous) / abs(previous)
    if abs(change) < metric.jump:
        return None
    direction = "вырос" if change > 0 else "упал"
    return Finding(
        kind="jump", metric=metric.key, label=metric.label,
        value=value, baseline=previous,
        message=(f"{metric.label} {direction} на {abs(change) * 100:.0f} % "
                 f"за сутки: было {_ru(previous)}, стало {_ru(value)} "
                 f"{metric.unit}"))


def _check_level(metric: Metric, value: float,
                 past: list[float]) -> Finding | None:
    """Выход за привычный уровень последних двух недель.

    Одного превышения разброса мало. У почти постоянного показателя
    разброс схлопывается, и тогда выбросом выглядит любая мелочь:
    «в простое 87 скважин при обычных 84» — не новость. Поэтому
    отклонение должно быть заметным и само по себе, в долях величины.
    """
    if len(past) < 5:
        return None
    middle = median(past)
    spread = _spread(past)
    if spread <= MIN_SPREAD or not middle:
        return None

    gap = abs(value - middle)
    if gap <= LEVEL_FACTOR * spread:
        return None
    if gap / abs(middle) < metric.jump * LEVEL_MIN_SHARE:
        return None
    return Finding(
        kind="level", metric=metric.key, label=metric.label,
        value=value, baseline=middle,
        message=(f"{metric.label}: {_ru(value)} {metric.unit} при обычных "
                 f"{_ru(middle)} за последние {len(past)} суток"))


def _check_frozen(metric: Metric, value: float,
                  past: list[float]) -> Finding | None:
    """Значение не меняется несколько суток подряд.

    Признак того, что строку скопировали, а не заполнили заново.
    """
    if not metric.watch_frozen or len(past) < FROZEN_DAYS - 1:
        return None
    tail = past[-(FROZEN_DAYS - 1):]
    if not all(abs(item - value) < 0.001 for item in tail):
        return None
    return Finding(
        kind="frozen", metric=metric.key, label=metric.label,
        value=value, baseline=value, severity="info",
        message=(f"{metric.label} не меняется {FROZEN_DAYS} суток подряд: "
                 f"{_ru(value)} {metric.unit}"))


def _check_contradiction(values: dict, past: list[dict]) -> Finding | None:
    """Фонд и добыча движутся в разные стороны.

    Именно это правило ловит 21.08.2026: скважин в работе стало больше
    на три десятка, а добыча при этом упала до самой низкой за месяц.
    """
    if not past:
        return None
    previous = past[-1]
    work, work_was = values.get("in_work"), previous.get("in_work")
    output, output_was = values.get("closed_day"), previous.get("closed_day")
    if not (work and work_was and output and output_was):
        return None

    work_change = (work - work_was) / work_was
    output_change = (output - output_was) / output_was
    if work_change < CONTRADICTION_FUND or output_change > -CONTRADICTION_OUTPUT:
        return None
    return Finding(
        kind="contradiction", metric="in_work", label="Фонд и добыча",
        value=work, baseline=work_was,
        message=(f"Скважин в работе стало больше на "
                 f"{work_change * 100:.0f} % ({_ru(work_was, 0)} → "
                 f"{_ru(work, 0)}), а добыча при этом упала на "
                 f"{abs(output_change) * 100:.1f} % "
                 f"({_ru(output_was)} → {_ru(output)} т)"))


def analyse(report: Report) -> list[Finding]:
    """Сверить сутки с предыдущими.

    Args:
        report: Сутки, которые проверяются.

    Returns:
        Замечания, найденные сравнением с историей. Пустой список
        означает, что сутки выглядят обычно.
    """
    values = sample(report)
    past = history(report.date)
    if not past:
        return []

    found: list[Finding] = []
    for metric in METRICS:
        value = values.get(metric.key)
        if value is None:
            continue
        series = [item[metric.key] for item in past if metric.key in item]

        jump = _check_jump(metric, value, series)
        if jump is not None:
            found.append(jump)
        else:
            # «Уровень» повторял бы уже сказанное: если показатель
            # скакнул за сутки, он же и вышел за привычный уровень.
            level = _check_level(metric, value, series)
            if level is not None:
                found.append(level)

        frozen = _check_frozen(metric, value, series)
        if frozen is not None:
            found.append(frozen)

    contradiction = _check_contradiction(values, past)
    if contradiction is not None:
        found.append(contradiction)
    return found
