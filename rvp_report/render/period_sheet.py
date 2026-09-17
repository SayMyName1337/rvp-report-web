# -*- coding: utf-8 -*-
"""Аналитика за период на одном листе А3.

Второй лист выдачи: то же, что на странице сводок, но сведённое
на лист, который печатают и раздают либо пересылают файлом.

**Чем отличается от суточного листа.** Суточный собирается разбором
исходного файла рапорта. Этот собирается из накопленных данных: за
период их нет ни в одном файле. Отсюда главное требование к нему —
полнота данных выносится наверх, отдельной полосой, а не прячется
в примечании. Сводка за месяц, собранная из двадцати семи суток, —
не месячная сумма, и лист, попавший кому-то в почту без этой оговорки,
назавтра превращается в чужой презентации в «итог месяца».

Данные приходят готовым словарём. Здесь не должно быть ни обращений
к базе, ни знания о Django: слой отрисовки остаётся независимым,
как и весь пакет `rvp_report`.
"""
from __future__ import annotations

from datetime import date, timedelta

from pptx.enum.text import PP_ALIGN
from pptx.util import Pt

from . import theme as T
from .deck import Deck
from .fmt import num, pct, short, signed
from .sheet import (A3_H_CM, A3_W_CM, CONTENT_W, GAP, MARGIN, SIZE_FOOT,
                    SIZE_TABLE, Sheet)

#: Сколько строк показывать в перечнях.
TOP_FIELDS = 12
TOP_REASONS = 8
TOP_WELLS = 12

#: Наибольшая длина периода, которую ещё показывают по суткам. Дальше
#: ряд сворачивается по месяцам: подписи трёхсот шестидесяти пяти суток
#: на листе сливаются в сплошную полосу. Значение выбрано по самому
#: длинному месяцу — месячный ряд остаётся суточным.
MAX_DAYS = 31

#: Столбцов свёрнутого ряда, при котором ещё подписывают значения.
MAX_LABELLED = 12

#: Отступ подвала.
FOOTER_TOP = A3_H_CM - 1.4

#: Названия месяцев в именительном падеже — для свёрнутого ряда.
MONTHS = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
          "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")


def _series(data: dict) -> dict:
    """Ряд добычи для диаграммы: по суткам либо свёрнутый по месяцам.

    Ряд строится по календарю периода, а не по имеющимся суткам.
    Иначе пропуски сомкнулись бы, и тридцать три разрозненных суток
    года выглядели бы непрерывным рядом — ровно то искажение, ради
    исключения которого наверху листа стоит полоса полноты данных.
    Пропущенные сутки передаются как ``None`` и остаются разрывом.

    Args:
        data: Данные листа.

    Returns:
        Подписи, ряд факта, ряд плана, способ построения и признак
        того, суточный ряд или месячный.
    """
    rows = data["series"]
    by_day = {row["date"]: row for row in rows}
    start: date = data["start"]
    # Хвост незавершённого периода не рисуется: пустая половина года
    # справа от последних суток ничего не сообщает.
    last = data["completeness"].get("last") or start
    end = min(data["end"], max(last, start))

    if (end - start).days + 1 <= MAX_DAYS:
        labels, fact, plan = [], [], []
        day = start
        while day <= end:
            row = by_day.get(day)
            labels.append(day.strftime("%d.%m"))
            fact.append(row.get("closed") if row else None)
            plan.append(row.get("plan") if row else None)
            day += timedelta(days=1)
        return {"daily": True, "labels": labels, "fact": fact, "plan": plan,
                "note": "по суткам"}

    totals: dict[tuple[int, int], float | None] = {}
    month = (start.year, start.month)
    while month <= (end.year, end.month):
        totals[month] = None
        year, index = month
        month = (year + 1, 1) if index == 12 else (year, index + 1)
    for row in rows:
        key = (row["date"].year, row["date"].month)
        if key in totals:
            totals[key] = (totals[key] or 0.0) + (row.get("closed") or 0.0)

    keys = sorted(totals)
    return {"daily": False,
            "labels": [f"{MONTHS[index - 1][:3]} {year % 100:02d}"
                       for year, index in keys],
            "fact": [totals[key] for key in keys], "plan": [],
            "note": "по месяцам · неполные месяцы показаны как есть"}


def _header(deck: Deck, sheet: Sheet, data: dict) -> float:
    """Шапка листа: знак, название, период."""
    slide = sheet.slide
    deck.rect(slide, 0, 0, A3_W_CM, 2.45, fill=T.BRAND)
    deck.rect(slide, 0, 2.45, A3_W_CM, 0.12, fill=T.ACCENT)
    deck.place_logo(slide, MARGIN, 0.52, 1.4, on_dark=True)

    deck.write(deck.textbox(slide, MARGIN + 5.6, 0.5, 24.0, 1.0),
               "Аналитика за период", size=Pt(22), bold=True, color=T.CANVAS)
    deck.write(deck.textbox(slide, MARGIN + 5.6, 1.5, 24.0, 0.7),
               data["title"], size=Pt(11), color=T.CANVAS)

    span = (f"{data['start']:%d.%m.%Y} — {data['end']:%d.%m.%Y}")
    deck.write(deck.textbox(slide, A3_W_CM - MARGIN - 14.0, 0.72, 14.0, 0.7),
               span, size=Pt(11), color=T.CANVAS, align=PP_ALIGN.RIGHT)
    deck.write(deck.textbox(slide, A3_W_CM - MARGIN - 14.0, 1.52, 14.0, 0.6),
               "ООО «СК Русвьетпетро»", size=SIZE_FOOT, color=T.CANVAS,
               align=PP_ALIGN.RIGHT)
    return 2.95


def _completeness(deck: Deck, sheet: Sheet, data: dict, y: float) -> float:
    """Полоса полноты данных — первое, что читают на листе.

    Суммы за период имеют смысл только вместе с указанием, за сколько
    суток они собраны. Поэтому полоса идёт до показателей, а не после.
    """
    c = data["completeness"]
    # Период, который ещё не наступил, не ожидает ни одних суток,
    # и «пропусков нет» выходит само собой. Полным он от этого
    # не становится: полным может быть только начавшийся период.
    started = c.get("started", True)
    full = c["complete"] and started
    height = 1.65
    deck.rect(sheet.slide, MARGIN, y, CONTENT_W, height,
              fill=T.PANEL if full else T.ACCENT_SOFT, rounded=True)
    deck.rect(sheet.slide, MARGIN, y, 0.12, height,
              fill=T.GOOD if full else T.WARN)

    if not started:
        title = "Период ещё не начался"
        note = (f"Он начинается {data['start']:%d.%m.%Y}, и данных за него "
                "пока быть не может. Показатели ниже — прочерки, а не нули.")
    elif full:
        title = (f"Данные за период полные: {c['present']} "
                 f"из {c['expected']} суток")
        note = "Суммы ниже посчитаны по всем суткам периода."
    else:
        title = (f"Данные неполные: {c['present']} из {c['expected']} суток")
        note = ("Суммы ниже посчитаны не по всему периоду. Сравнивать их "
                "с другими периодами напрямую нельзя.")
    if started and c.get("unfinished"):
        title += " · период ещё не завершён"
    if c.get("needs_review"):
        note += (f" Суток с неподтверждёнными показателями: "
                 f"{c['needs_review']}.")

    deck.write(deck.textbox(sheet.slide, MARGIN + 0.45, y + 0.18,
                            CONTENT_W - 1.0, 0.55),
               title, size=Pt(11), bold=True,
               color=T.INK if full else T.WARN)
    deck.write(deck.textbox(sheet.slide, MARGIN + 0.45, y + 0.72,
                            CONTENT_W - 1.0, 0.5),
               note, size=SIZE_TABLE, color=T.MUTED)

    missing = c.get("missing") or []
    if missing:
        # Перечень пропусков полезен, пока их немного. Когда данных нет
        # за большую часть периода, первые двадцать чисел января ничего
        # не проясняют — важнее, за какой отрезок данные всё-таки есть.
        # Решение принято вместе с данными, чтобы лист и страница
        # говорили о полноте одинаково.
        if c.get("many_missing") and c.get("first") and c.get("last"):
            line = (f"Данные есть с {c['first']:%d.%m.%Y} "
                    f"по {c['last']:%d.%m.%Y}. Суток с данными: "
                    f"{c['present']}, пропущено: {len(missing)}.")
        else:
            line = "Нет данных за: " + ", ".join(
                day.strftime("%d.%m") for day in missing)
        deck.write(deck.textbox(sheet.slide, MARGIN + 0.45, y + 1.16,
                                CONTENT_W - 1.0, 0.5),
                   line, size=SIZE_FOOT, color=T.MUTED)
    return y + height + GAP


def _tiles(sheet: Sheet, data: dict, y: float) -> float:
    """Шесть итогов периода."""
    p = data["production"]
    losses = data["losses"]
    # Доля считается, только если есть обе величины: у периода
    # без данных итог потерь — прочерк, а не ноль.
    share = (losses["total"] / p["closed"] * 100
             if p.get("closed") and losses.get("total") else None)

    tiles = [
        {"label": "Добыча нефти за период, т", "value": num(p.get("closed")),
         "note": f"в среднем {num(p.get('average'), 1)} т/сут",
         "accent": T.BRAND},
        {"label": "План БП за период, т", "value": num(p.get("plan_bp")),
         "note": f"{signed(p.get('dev_bp'))} к плану",
         "note_color": T.status_color(p.get("dev_bp")),
         "accent": T.status_color(p.get("dev_bp"))},
        {"label": "Потери добычи, т", "value": num(losses["total"]),
         "note": f"{pct(share, 1)} от добычи" if share else "расчётная",
         "note_color": T.BAD, "accent": T.BAD, "mark": "расч."},
        {"label": "Сдача нефти, т", "value": num(p.get("delivered")),
         "note": "за период", "accent": T.BRAND_LIGHT},
        {"label": "Выработка э/э, МВт·ч", "value": num(p.get("power"), 1),
         "note": "за период", "accent": T.BRAND_LIGHT},
        {"label": "Происшествий", "value": num(p.get("incidents")),
         "note": f"обращений в здравпункт {num(p.get('medical'))}",
         "accent": T.GOOD if not p.get("incidents") else T.BAD},
    ]

    columns, height = 6, 2.45
    width = (CONTENT_W - GAP * (columns - 1)) / columns
    for index, item in enumerate(tiles):
        sheet.tile(MARGIN + index * (width + GAP), y, width, height, item)
    return y + height + GAP


def _chart(deck: Deck, sheet: Sheet, data: dict, x: float, y: float,
           w: float) -> float:
    """Диаграмма добычи по суткам или по месяцам."""
    row = _series(data)
    top = sheet.block(x, y, w, "Добыча", row["note"])
    height = 8.6
    if not any(value is not None for value in row["fact"]):
        deck.write(deck.textbox(sheet.slide, x, top + 0.2, w, 0.6),
                   "За период нет данных.", size=SIZE_TABLE, color=T.MUTED)
        return top + 0.8

    if row["daily"]:
        series = [{"name": "Факт", "values": row["fact"], "color": T.BRAND}]
        if any(value is not None for value in row["plan"]):
            series.append({"name": "План БП", "values": row["plan"],
                           "color": T.MUTED, "dash": True, "width": 1.25})
        deck.line_chart(sheet.slide, x, top, w, height, row["labels"],
                        series, number_format="# ##0")
    else:
        deck.column_chart(sheet.slide, x, top, w, height, row["labels"],
                          row["fact"], [T.BRAND],
                          data_labels=len(row["labels"]) <= MAX_LABELLED,
                          number_format="# ##0")
    return top + height


def _totals(sheet: Sheet, data: dict, x: float, y: float, w: float) -> float:
    """Итоги периода и сверка с нарастающим итогом рапорта."""
    p = data["production"]
    top = sheet.block(x, y, w, "Итоги периода")
    rows = [
        ["Добыча нефти, т", num(p.get("closed"))],
        ["В среднем за сутки, т", num(p.get("average"), 1)],
        ["План БП, т", num(p.get("plan_bp"))],
        ["Отклонение от БП, т", signed(p.get("dev_bp"))],
        ["План СГ, т", num(p.get("plan_sg"))],
        ["Отклонение от СГ, т", signed(p.get("dev_sg"))],
        ["Сдача нефти, т", num(p.get("delivered"))],
        ["Закачка ППД, м³", num(data["injection"].get("fact"))],
    ]
    marks = {(3, 1): T.status_color(p.get("dev_bp")),
             (5, 1): T.status_color(p.get("dev_sg"))}

    declared = p.get("declared")
    if declared:
        rows.append(["Нарастающий итог рапорта, т", num(declared["value"])])
        rows.append(["Расхождение с суммой по суткам, т",
                     signed(declared["gap"])])
        marks[(9, 1)] = T.BAD if declared["notable"] else T.GOOD
    return sheet.table(x, top, w, ["Показатель", "Значение"], rows,
                       widths=[2.6, 1.0], cell_colors=marks)


def _fields(sheet: Sheet, data: dict, x: float, y: float, w: float) -> float:
    """Добыча по месторождениям за период."""
    items = [row for row in data["fields"] if row.get("qo")]
    total = sum(row["qo"] for row in items) or 0.0
    top = sheet.block(x, y, w, "Добыча по месторождениям",
                      f"всего {num(total)} т")
    rows = [[short(row["field__name"], 22), num(row["qo"]),
             pct(row["qo"] / total * 100, 1) if total else "—"]
            for row in items[:TOP_FIELDS]]
    rest = items[TOP_FIELDS:]
    if rest:
        left = sum(row["qo"] for row in rest)
        rows.append([f"прочие ({len(rest)})", num(left),
                     pct(left / total * 100, 1) if total else "—"])
    if not rows:
        rows = [["нет данных", "—", "—"]]
    return sheet.table(x, top, w, ["Месторождение", "т", "доля"], rows,
                       widths=[2.6, 1.1, 0.8])


def _reasons(sheet: Sheet, data: dict, x: float, y: float, w: float) -> float:
    """Потери простоя по причинам за период."""
    items = [row for row in data["reasons"] if row.get("qo")]
    top = sheet.block(x, y, w, "Причины простоя",
                      f"потери {num(data['losses']['total'])} т · расч.")
    rows = [[short(row["reason__name"], 26), num(row["qo"]),
             num(row["days"])] for row in items[:TOP_REASONS]]
    rest = items[TOP_REASONS:]
    if rest:
        rows.append([f"прочие ({len(rest)})",
                     num(sum(row["qo"] for row in rest)), ""])
    if not rows:
        rows = [["разбивка не прочитана", "—", "—"]]
    return sheet.table(x, top, w, ["Причина", "Потери, т", "Суток"], rows,
                       widths=[2.6, 1.1, 0.8])


def _wells(sheet: Sheet, data: dict, x: float, y: float, w: float) -> float:
    """Скважины с наибольшими накопленными потерями."""
    items = data["wells"]
    top = sheet.block(x, y, w, "Наибольшие потери по скважинам",
                      "накопленным итогом")
    rows = [[str(row["well__number"]), short(row["well__field__name"], 18),
             num(row["qo"]), num(row["days"])]
            for row in items[:TOP_WELLS]]
    if not rows:
        rows = [["нет данных", "", "", ""]]
    return sheet.table(x, top, w,
                       ["Скв.", "Месторождение", "Потери, т", "Суток"],
                       rows, widths=[0.8, 2.0, 1.1, 0.8])


def _losses(sheet: Sheet, data: dict, x: float, y: float, w: float) -> float:
    """Потери добычи по составляющим."""
    losses = data["losses"]
    top = sheet.block(x, y, w, "Потери по составляющим", "расч.")
    rows = [[label, num(value)] for label, value in losses["parts"]]
    rows.append(["Всего", num(losses["total"])])
    groups = losses.get("groups") or {}
    if groups.get("qo"):
        rows.append([f"в том числе групповых ({num(groups.get('count'))})",
                     num(groups["qo"])])
    return sheet.table(x, top, w, ["Составляющая", "т"], rows,
                       widths=[2.8, 1.1])


def _gas(sheet: Sheet, data: dict, x: float, y: float, w: float) -> float:
    """Баланс попутного газа за период.

    Процент утилизации не показывается намеренно: в рапорте он
    постоянен — объём сжигания определяется от добычи по нормативу,
    а не измеряется, поэтому среднее за период не несёт сведений.
    """
    top = sheet.block(x, y, w, "Попутный нефтяной газ", "тыс. м³")
    rows = [[short(row["label"], 26), num(row.get("plan"), 1),
             num(row.get("fact"), 1)] for row in data["gas"]]
    if not rows:
        rows = [["нет данных по газу", "", ""]]
    return sheet.table(x, top, w, ["Показатель", "БП", "Факт"], rows,
                       widths=[2.6, 1.1, 1.1])


def _footer(deck: Deck, sheet: Sheet, data: dict) -> None:
    """Подвал: оговорки и гриф."""
    deck.line(sheet.slide, MARGIN, FOOTER_TOP, CONTENT_W, color=T.LINE)
    note = ("Перечни приведены до заданного числа строк; остаток сведён "
            "в строку «прочие» и в сумме учтён. Пометка «расч.» означает "
            "величину, вычисленную программой. Полнота данных за период "
            "указана в верхней части листа и учитывается при сравнении "
            "периодов между собой.")
    if data.get("clamped"):
        note = ("Запрошенный период длиннее двух лет и показан укороченным. "
                + note)
    deck.write(deck.textbox(sheet.slide, MARGIN, FOOTER_TOP + 0.14,
                            CONTENT_W - 10.0, 1.0),
               note, size=SIZE_FOOT, color=T.MUTED)
    deck.write(deck.textbox(sheet.slide, A3_W_CM - MARGIN - 10.0,
                            FOOTER_TOP + 0.14, 10.0, 0.6),
               T.CONFIDENTIALITY, size=SIZE_FOOT, color=T.MUTED,
               align=PP_ALIGN.RIGHT)


def build(data: dict, output: str, assets_dir: str | None = None) -> str:
    """Собрать лист А3 с аналитикой за период.

    Args:
        data: Готовые данные сводки: название и границы периода,
            полнота, итоги, перечни и ряд по суткам.
        output: Путь к создаваемому файлу .pptx.
        assets_dir: Каталог для кэша растрового знака.

    Returns:
        Путь к созданному файлу.
    """
    deck = Deck(assets_dir=assets_dir, size=(A3_W_CM, A3_H_CM))
    slide = deck.blank_slide()
    sheet = Sheet(deck, slide)

    y = _header(deck, sheet, data)
    y = _completeness(deck, sheet, data, y)
    y = _tiles(sheet, data, y)

    col = (CONTENT_W - 3 * GAP) / 4
    x1 = MARGIN
    x2 = MARGIN + col + GAP
    x3 = MARGIN + 2 * (col + GAP)
    x4 = MARGIN + 3 * (col + GAP)
    wide = 3 * col + 2 * GAP

    band = _chart(deck, sheet, data, x1, y, wide)
    _totals(sheet, data, x4, y, col)

    band += GAP
    _fields(sheet, data, x1, band, col)
    _reasons(sheet, data, x2, band, col)
    _wells(sheet, data, x3, band, col)
    rest = _losses(sheet, data, x4, band, col)
    _gas(sheet, data, x4, rest + GAP, col)

    _footer(deck, sheet, data)
    deck.prs.save(output)
    return output
