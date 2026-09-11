# -*- coding: utf-8 -*-
"""История отдельной скважины.

Суточный рапорт показывает срез на одни сутки: какие скважины стоят
сегодня и сколько на этом теряется. Чего в нём нет — так это судьбы
конкретной скважины: сколько раз она вставала, по каким причинам,
сколько потеряно за всё время и не встала ли она снова вскоре после
ремонта.

Последнее — самое ценное. Увидеть это по суточным рапортам нельзя:
нужно сопоставить дату остановки с датой последнего ремонта, а такое
сопоставление возможно только при наличии истории.

Важно, что именно тут утверждается. Система показывает **факт**:
скважина остановилась через столько-то суток после ремонта. Вывод
о том, виноват ли ремонт, она не делает и делать не может: среди таких
остановок есть и плановые — вывод на КВД, технологические ограничения.
Причина показывается рядом, чтобы читающий судил сам.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count, Max, Min, Sum

from apps.catalog.models import Well

from .models import RampUpDaily, WellDaily

#: Сколько суток после ремонта считать «вскоре». Порог не означает,
#: что остановка вызвана ремонтом, — он лишь очерчивает круг случаев,
#: которые стоит посмотреть.
REPAIR_WINDOW = 90

#: Сколько причин показывать в разборе по частоте.
TOP_REASONS = 8


@dataclass(frozen=True)
class Spell:
    """Непрерывный отрезок, который скважина провела в одном состоянии."""

    category: str
    label: str
    start: date
    end: date
    days: int
    qo: float
    reason: str

    @property
    def is_single_day(self) -> bool:
        """Длился ли отрезок одни сутки."""
        return self.start == self.end


@dataclass(frozen=True)
class StopAfterRepair:
    """Остановка, случившаяся вскоре после ремонта.

    Название описывает наблюдение, а не причину: связь с ремонтом
    из этих данных не следует.
    """

    stopped: date
    repaired: date
    reason: str
    qo: float

    @property
    def days_after(self) -> int:
        """Сколько суток скважина проработала после ремонта."""
        return (self.stopped - self.repaired).days


def totals(well: Well) -> dict:
    """Итоги по скважине за всё время наблюдения.

    Args:
        well: Скважина.

    Returns:
        Суммы потерь и число суток по каждому списку, а также границы
        наблюдения.
    """
    rows = (WellDaily.objects.filter(well=well)
            .values("category")
            .annotate(qo=Sum("qo"), days=Count("id"))
            .order_by("-qo"))
    span = (WellDaily.objects.filter(well=well)
            .aggregate(first=Min("report__date"), last=Max("report__date")))

    by_category = {row["category"]: row for row in rows}
    return {
        "by_category": [
            {"label": WellDaily.Category(key).label,
             "category": key,
             "qo": by_category[key]["qo"] or 0.0,
             "days": by_category[key]["days"]}
            for key in WellDaily.Category.values if key in by_category],
        "qo": sum((row["qo"] or 0.0) for row in rows),
        "days": sum(row["days"] for row in rows),
        "first": span["first"],
        "last": span["last"],
    }


def spells(well: Well) -> list[Spell]:
    """Отрезки, которые скважина провела в каждом состоянии.

    Подряд идущие сутки в одном списке объединяются: «стояла
    с 3 по 17 августа» читается лучше, чем пятнадцать одинаковых строк.

    Args:
        well: Скважина.

    Returns:
        Отрезки от недавних к давним.
    """
    rows = list(WellDaily.objects.filter(well=well)
                .select_related("report")
                .order_by("report__date")
                .values("report__date", "category", "qo", "reason"))

    found: list[Spell] = []
    current: dict | None = None
    for row in rows:
        day = row["report__date"]
        same = (current is not None
                and current["category"] == row["category"]
                and day - current["end"] == timedelta(days=1))
        if same:
            current["end"] = day
            current["days"] += 1
            current["qo"] += row["qo"] or 0.0
            continue
        if current is not None:
            found.append(_spell(current))
        current = {"category": row["category"], "start": day, "end": day,
                   "days": 1, "qo": row["qo"] or 0.0,
                   "reason": row["reason"] or ""}
    if current is not None:
        found.append(_spell(current))
    return list(reversed(found))


def _spell(raw: dict) -> Spell:
    """Собрать отрезок из накопленных значений."""
    return Spell(category=raw["category"],
                 label=WellDaily.Category(raw["category"]).label,
                 start=raw["start"], end=raw["end"], days=raw["days"],
                 qo=raw["qo"], reason=raw["reason"])


def reasons(well: Well) -> list[dict]:
    """Причины остановок по частоте и накопленным потерям.

    Args:
        well: Скважина.

    Returns:
        Причины от наиболее затратных к наименее.
    """
    return list(WellDaily.objects
                .filter(well=well)
                .exclude(reason="")
                .values("reason")
                .annotate(days=Count("id"), qo=Sum("qo"))
                .order_by("-qo")[:TOP_REASONS])


def repairs(well: Well) -> list[date]:
    """Даты ремонтов, упомянутые в рапортах.

    Args:
        well: Скважина.

    Returns:
        Даты от недавних к давним, без повторов.
    """
    found = (WellDaily.objects
             .filter(well=well, last_repair__isnull=False)
             .values_list("last_repair", flat=True).distinct())
    return sorted(set(found), reverse=True)


def stops_after_repair(well: Well) -> list[StopAfterRepair]:
    """Остановки, случившиеся вскоре после ремонта.

    Ради этого вида история и накапливается: по одному суточному
    рапорту такое не увидеть. Но вывод о причине не делается —
    среди таких остановок есть и плановые, вроде вывода на КВД.
    Причина возвращается вместе с датами, чтобы судил человек.

    Args:
        well: Скважина.

    Returns:
        Случаи от недавних к давним, по одному на каждую остановку.
    """
    rows = (WellDaily.objects
            .filter(well=well, stop_date__isnull=False,
                    last_repair__isnull=False)
            .values("stop_date", "last_repair", "reason", "qo")
            .distinct())

    seen: set[tuple[date, date]] = set()
    found: list[StopAfterRepair] = []
    for row in rows:
        stopped, repaired = row["stop_date"], row["last_repair"]
        gap = (stopped - repaired).days
        if not 0 <= gap <= REPAIR_WINDOW:
            continue
        key = (stopped, repaired)
        if key in seen:
            continue
        seen.add(key)
        found.append(StopAfterRepair(stopped=stopped,
                                     repaired=repaired,
                                     reason=row["reason"] or "",
                                     qo=row["qo"] or 0.0))
    return sorted(found, key=lambda item: item.stopped, reverse=True)


def ramp_ups(well: Well) -> list[RampUpDaily]:
    """Случаи вывода скважины на режим после мероприятий.

    Args:
        well: Скважина.

    Returns:
        Записи от недавних к давним.
    """
    return list(RampUpDaily.objects.filter(well=well)
                .select_related("report").order_by("-report__date"))


def series(well: Well) -> dict:
    """Потери по суткам — для графика.

    Сутки, когда скважина работала, остаются пустыми: ноль потерь
    и отсутствие скважины в списках — разные вещи, и рисовать их
    одинаково нельзя.

    Args:
        well: Скважина.

    Returns:
        Подписи суток и ряд потерь.
    """
    rows = {row["report__date"]: row["qo"] for row in WellDaily.objects
            .filter(well=well).values("report__date", "qo")}
    if not rows:
        return {"labels": [], "values": []}

    labels, values = [], []
    day, last = min(rows), max(rows)
    while day <= last:
        labels.append(day.strftime("%d.%m"))
        values.append(rows.get(day))
        day += timedelta(days=1)
    return {"labels": labels, "values": values}


def history(well: Well) -> dict:
    """Собрать историю скважины целиком.

    Args:
        well: Скважина.

    Returns:
        Все разделы страницы истории.
    """
    return {
        "well": well,
        "totals": totals(well),
        "spells": spells(well),
        "reasons": reasons(well),
        "repairs": repairs(well),
        "after_repair": stops_after_repair(well),
        "ramp_ups": ramp_ups(well),
        "series": series(well),
    }


def ranking(field_id: int | None = None, search: str = "",
            limit: int = 100) -> list[dict]:
    """Скважины по накопленным потерям.

    Args:
        field_id: Ограничить одним месторождением.
        search: Отбор по части номера скважины.
        limit: Сколько строк вернуть.

    Returns:
        Скважины от наибольших потерь к наименьшим.
    """
    rows = (WellDaily.objects
            .values("well_id", "well__number", "well__field__name")
            .annotate(qo=Sum("qo"), days=Count("id"),
                      last=Max("report__date"))
            .order_by("-qo"))
    if field_id:
        rows = rows.filter(well__field_id=field_id)
    if search:
        rows = rows.filter(well__number__icontains=search)
    return list(rows[:limit])
