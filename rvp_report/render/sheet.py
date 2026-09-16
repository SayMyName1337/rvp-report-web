# -*- coding: utf-8 -*-
"""Суточный рапорт на одном листе А3.

Та же отчётность, что на слайдах доклада, но сведённая на один
лист: его печатают и раздают на совещании либо пересылают файлом.
Доклад по слайдам это не заменяет — состав слайдов согласован
и изменению не подлежит.

На лист выносятся первые десять слайдов. Одиннадцатый служебный —
замечания к исходным данным и перечень посчитанных величин; он нужен
тому, кто отвечает за данные, а не тем, кому лист раздают. Эти
сведения остаются в системе и в презентации доклада.

Лист собирается тем же разбором того же исходного файла, что
и презентация, поэтому цифры на нём совпадают со слайдами
по построению, а не по совпадению.

**Что на лист не помещается.** Площадь А3 больше слайда всего
в 1,9 раза, а слайдов десять. Поэтому перечни, у которых
в рапорте бывают десятки строк — месторождения, фонд, скважины
в бурении, — выводятся до заданного числа строк, а остаток
сворачивается в строку «прочие»: свёрнутое не теряется, а
складывается, и сумма сходится. В подвале листа сказано, что полные
перечни есть в презентации доклада.
"""
from __future__ import annotations

from pptx.enum.text import PP_ALIGN
from pptx.util import Pt

from ..domain.model import DailyReport
from . import theme as T
from .deck import Deck
from .fmt import date_ru, num, pct, signed

#: Размер листа: А3 в альбомной ориентации, сантиметры.
A3_W_CM = 42.0
A3_H_CM = 29.7

#: Поля листа и промежуток между блоками.
MARGIN = 1.0
GAP = 0.5

#: Ширина полосы содержимого.
CONTENT_W = A3_W_CM - 2 * MARGIN

#: Отступ нижней полосы и верх подвала.
BAND = 23.0
FOOTER_TOP = A3_H_CM - 1.4

#: Кегли листа. Мельче слайдовых: данных выносится больше, но лист
#: читают с руки, а не с экрана в конце зала.
SIZE_TABLE = Pt(8)
SIZE_TABLE_HEAD = Pt(7.5)
SIZE_KPI = Pt(17)
SIZE_KPI_LABEL = Pt(7)
SIZE_BLOCK = Pt(10)
SIZE_FOOT = Pt(7)

#: Высота строки и заголовка таблицы листа.
ROW_H = 0.46
HEAD_H = 0.5

#: Пометка расчётной величины.
DERIVED = "расч."

#: Сколько строк показывать в перечнях, которые бывают длиннее.
#: Значения подобраны так, чтобы самая длинная колонка укладывалась
#: между плитками и нижней полосой на данных за август и сентябрь.
TOP_FIELDS = 9
TOP_STOCK = 7
TOP_REASONS = 5
TOP_DRILLING = 8
TOP_BOTTOM = 6


def _short(text, limit: int) -> str:
    """Укоротить подпись до предела, обозначив обрыв многоточием."""
    text = str(text or "").strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


class Sheet:
    """Раскладка листа: заголовки блоков, таблицы и плитки."""

    def __init__(self, deck: Deck, slide) -> None:
        """Args:
        deck: Презентация, в которую добавляется лист.
        slide: Сам лист.
        """
        self.deck = deck
        self.slide = slide

    def block(self, x: float, y: float, w: float, title: str,
              note: str = "") -> float:
        """Заголовок блока. Возвращает отступ, с которого идёт таблица.

        Под заголовок отведены две строки: в узкой колонке длинное
        название переносится, и однострочной полосы ему не хватало —
        вторая строка ложилась на шапку таблицы.
        """
        self.deck.write(self.deck.textbox(self.slide, x, y, w * 0.62, 0.84),
                        title, size=SIZE_BLOCK, bold=True, color=T.BRAND)
        if note:
            self.deck.write(
                self.deck.textbox(self.slide, x + w * 0.62, y + 0.08,
                                  w * 0.38, 0.5),
                note, size=SIZE_FOOT, color=T.MUTED, align=PP_ALIGN.RIGHT)
        self.deck.line(self.slide, x, y + 0.84, w, color=T.ACCENT, weight=1.2)
        return y + 1.0

    def table(self, x: float, y: float, w: float, headers: list,
              rows: list, widths: list | None = None,
              aligns: list | None = None,
              cell_colors: dict | None = None) -> float:
        """Таблица листа. Возвращает отступ под ней."""
        self.deck.table(self.slide, x, y, w, headers, rows, widths=widths,
                        row_h=ROW_H, head_h=HEAD_H, aligns=aligns,
                        cell_colors=cell_colors, size=SIZE_TABLE,
                        head_size=SIZE_TABLE_HEAD)
        return y + HEAD_H + ROW_H * max(len(rows), 1)

    def tile(self, x: float, y: float, w: float, h: float,
             item: dict) -> None:
        """Плитка показателя.

        Плитка слайда рассчитана на высоту 3,5 см; на листе она вдвое
        ниже, и слайдовая разметка накладывала значение на пояснение.
        Поэтому здесь своя: отступы отсчитываются от содержимого,
        а не от нижнего края.
        """
        deck = self.deck
        deck.rect(self.slide, x, y, w, h, fill=T.PANEL, rounded=True)
        if item.get("accent") is not None:
            deck.rect(self.slide, x, y, 0.1, h, fill=item["accent"])
        if item.get("mark"):
            deck.write(
                deck.textbox(self.slide, x + w - 2.0, y + 0.16, 1.8, 0.4),
                item["mark"], size=SIZE_FOOT, color=T.MUTED,
                align=PP_ALIGN.RIGHT)

        pad = 0.3
        deck.write(deck.textbox(self.slide, x + pad, y + 0.14,
                                w - 2 * pad, 0.42),
                   item["label"].upper(), size=SIZE_KPI_LABEL,
                   color=T.MUTED, bold=True)
        deck.write(deck.textbox(self.slide, x + pad, y + 0.56,
                                w - 2 * pad, 0.95),
                   item["value"], size=SIZE_KPI, bold=True,
                   color=item.get("color", T.INK))
        if item.get("note"):
            deck.write(deck.textbox(self.slide, x + pad, y + 1.54,
                                    w - 2 * pad, 0.72),
                       item["note"], size=SIZE_KPI_LABEL,
                       color=item.get("note_color", T.MUTED))


def _header(deck: Deck, sheet: Sheet, r: DailyReport) -> float:
    """Шапка листа: знак, название, отчётная дата, погода."""
    slide = sheet.slide
    deck.rect(slide, 0, 0, A3_W_CM, 2.45, fill=T.BRAND)
    deck.rect(slide, 0, 2.45, A3_W_CM, 0.12, fill=T.ACCENT)
    deck.place_logo(slide, MARGIN, 0.52, 1.4, on_dark=True)

    deck.write(deck.textbox(slide, MARGIN + 5.6, 0.5, 22.0, 1.0),
               "Суточный рапорт", size=Pt(22), bold=True, color=T.CANVAS)
    deck.write(deck.textbox(slide, MARGIN + 5.6, 1.5, 22.0, 0.7),
               f"Отчётная дата — {date_ru(r.report_date)}",
               size=Pt(11), color=T.CANVAS)

    weather = []
    if r.temperature is not None:
        weather.append(f"{num(r.temperature, 0)} °C")
    if r.wind:
        weather.append(str(r.wind))
    deck.write(deck.textbox(slide, A3_W_CM - MARGIN - 14.0, 0.72, 14.0, 0.7),
               "  ·  ".join(weather), size=Pt(11), color=T.CANVAS,
               align=PP_ALIGN.RIGHT)
    deck.write(deck.textbox(slide, A3_W_CM - MARGIN - 14.0, 1.52, 14.0, 0.6),
               "ООО «СК Русвьетпетро»", size=SIZE_FOOT, color=T.CANVAS,
               align=PP_ALIGN.RIGHT)
    return 2.95


def _tiles(sheet: Sheet, r: DailyReport, y: float) -> float:
    """Двенадцать ключевых показателей в два ряда по шесть."""
    p, d = r.production, r.delivery
    stock, injection = r.stock_total, r.injection_total
    delta = stock.in_work_delta if stock else None

    tiles = [
        {"label": "Добыча нефти, т", "value": num(p.closed_day, 1),
         "note": f"план СГ {num(p.plan_sg_day)} · {signed(p.dev_sg_day, 1)}",
         "note_color": T.status_color(p.dev_sg_day),
         "accent": T.status_color(p.dev_sg_day)},
        {"label": "К бизнес-плану, т/сут", "value": signed(p.dev_bp_day, 1),
         "note": f"план БП {num(p.plan_bp_day)}",
         "color": T.status_color(p.dev_bp_day),
         "accent": T.status_color(p.dev_bp_day)},
        {"label": "Нарастающая за месяц, т", "value": num(p.cumulative_month),
         "note": f"{signed(p.dev_bp_month)} к БП",
         "note_color": T.status_color(p.dev_bp_month),
         "accent": T.status_color(p.dev_bp_month)},
        {"label": "Сдача нефти, т", "value": num(d.fact_day),
         "note": f"план {num(d.plan_day)} · {signed(d.dev_day)}",
         "note_color": T.status_color(d.dev_day),
         "accent": T.status_color(d.dev_day)},
        {"label": "Потери добычи, т/сут", "value": num(r.total_losses, 1),
         "note": "простой + бездействие + внутрисменные",
         "note_color": T.BAD, "accent": T.BAD, "mark": DERIVED},
        {"label": "Фонд в работе",
         "value": num(stock.in_work if stock else None),
         "note": f"{signed(delta)} за сутки",
         "note_color": T.status_color(delta),
         "accent": T.status_color(delta)},
        {"label": "Утилизация газа", "value": pct(r.gas_utilization_pct, 2),
         "note": "целевой уровень — не ниже 95 %",
         "accent": T.GOOD if (r.gas_utilization_pct or 0) >= 95 else T.BAD},
        {"label": "Выработка э/э, МВт·ч",
         "value": num(r.power.total_with_psp, 1),
         "note": f"{signed(r.power.total_with_psp_delta, 2)} к прошлым сут.",
         "note_color": T.status_color(r.power.total_with_psp_delta),
         "accent": T.BRAND},
        {"label": "Закачка ППД, м³/сут",
         "value": num(injection.fact_day if injection else None),
         "note": f"режим {num(injection.plan_day if injection else None)}",
         "accent": T.BRAND_LIGHT},
        {"label": "Свободный объём, м³", "value": num(r.free_volume_total_m3),
         "note": "по всем объектам", "accent": T.BRAND_LIGHT},
        {"label": "НСЖ ЦОМ, м³", "value": num(p.nsj_fact),
         "note": f"{signed(p.nsj_dev)} к закрытию",
         "accent": T.BRAND_LIGHT},
        {"label": "В бурении", "value": num(len(r.drilling)),
         "note": "скважин у подрядчиков", "accent": T.BRAND_LIGHT},
    ]

    columns, height = 6, 2.45
    width = (CONTENT_W - GAP * (columns - 1)) / columns
    for index, item in enumerate(tiles):
        row, col = divmod(index, columns)
        sheet.tile(MARGIN + col * (width + GAP),
                   y + row * (height + GAP), width, height, item)
    return y + 2 * height + 2 * GAP


def _potential(sheet: Sheet, r: DailyReport, x: float, y: float,
               w: float) -> float:
    """Потенциал добычи и отклонения от планов."""
    p = r.production
    top = sheet.block(x, y, w, "Потенциал добычи")
    rows = [
        ["Потенциал, т", num(p.potential_com)],
        ["С учётом ограничений, т", num(p.potential_limited)],
        ["Закрытие по сводке, т", num(p.closed_day, 1)],
        ["Факт ЦОМ, т", num(p.fact_com_day)],
        ["Прогноз на 6:00, т", num(p.forecast_0600)],
        ["План СГ на сутки, т", num(p.plan_sg_day)],
        ["План БП на сутки, т", num(p.plan_bp_day)],
        ["± к СГ за сутки, т", signed(p.dev_sg_day, 1)],
        ["± к БП за сутки, т", signed(p.dev_bp_day, 1)],
        ["± к СГ с начала месяца, т", signed(p.dev_sg_month)],
        ["± к БП с начала месяца, т", signed(p.dev_bp_month)],
        ["± к БП с начала года, т", signed(p.dev_bp_year)],
    ]
    marks = {(7, 1): T.status_color(p.dev_sg_day),
             (8, 1): T.status_color(p.dev_bp_day),
             (9, 1): T.status_color(p.dev_sg_month),
             (10, 1): T.status_color(p.dev_bp_month),
             (11, 1): T.status_color(p.dev_bp_year)}
    return sheet.table(x, top, w, ["Показатель", "Значение"], rows,
                       widths=[2.3, 1.0], cell_colors=marks)


def _fields(sheet: Sheet, r: DailyReport, x: float, y: float,
            w: float) -> float:
    """Добыча по месторождениям: крупнейшие и остаток одной строкой."""
    items = sorted(((name, value) for name, value in r.production.by_field
                    if value), key=lambda item: item[1], reverse=True)
    total = sum(value for _name, value in items) or 0.0
    top = sheet.block(x, y, w, "Добыча по месторождениям",
                      f"всего {num(total, 1)} т")

    rows = [[_short(name, 22), num(value, 1),
             pct(value / total * 100, 1) if total else "—"]
            for name, value in items[:TOP_FIELDS]]
    rest = items[TOP_FIELDS:]
    if rest:
        left = sum(value for _name, value in rest)
        rows.append([f"прочие ({len(rest)})", num(left, 1),
                     pct(left / total * 100, 1) if total else "—"])
    if not rows:
        rows = [["нет данных по месторождениям", "—", "—"]]
    return sheet.table(x, top, w, ["Месторождение", "т/сут", "доля"], rows,
                       widths=[2.6, 1.0, 0.8])


def _stock(sheet: Sheet, r: DailyReport, x: float, y: float,
           w: float) -> float:
    """Фонд скважин по месторождениям и итог."""
    total = r.stock_total
    top = sheet.block(
        x, y, w, "Состояние фонда скважин",
        f"эксплуатационный {num(total.operating_stock if total else None)}")

    items = sorted((s for s in r.stock_by_field if s.total is not None),
                   key=lambda s: s.total, reverse=True)
    rows = [[_short(s.name, 20), num(s.total), num(s.in_work),
             num(s.in_downtime), num(s.in_idle)]
            for s in items[:TOP_STOCK]]
    rest = items[TOP_STOCK:]
    if rest:
        rows.append([f"прочие ({len(rest)})",
                     num(sum(s.total or 0 for s in rest)),
                     num(sum(s.in_work or 0 for s in rest)),
                     num(sum(s.in_downtime or 0 for s in rest)),
                     num(sum(s.in_idle or 0 for s in rest))])
    if total is not None:
        rows.append(["Всего", num(total.total), num(total.in_work),
                     num(total.in_downtime), num(total.in_idle)])
    if not rows:
        rows = [["нет данных по фонду", "", "", "", ""]]
    return sheet.table(x, top, w,
                       ["Месторождение", "Всего", "В работе", "Простой",
                        "Бездейств."],
                       rows, widths=[2.4, 0.8, 0.9, 0.85, 1.0])


def _downtime(sheet: Sheet, r: DailyReport, x: float, y: float,
              w: float) -> float:
    """Причины текущего простоя."""
    items = sorted(r.downtime_breakdown, key=lambda row: row[2] or 0.0,
                   reverse=True)
    top = sheet.block(x, y, w, "Причины текущего простоя",
                      f"потери {num(r.total_losses, 1)} т/сут · {DERIVED}")
    rows = [[_short(reason, 26), num(wells), num(qo, 1)]
            for reason, wells, qo in items[:TOP_REASONS]]
    rest = items[TOP_REASONS:]
    if rest:
        rows.append([f"прочие ({len(rest)})",
                     num(sum(row[1] or 0 for row in rest)),
                     num(sum(row[2] or 0 for row in rest), 1)])
    if not rows:
        rows = [["разбивка не прочитана", "—", "—"]]
    return sheet.table(x, top, w, ["Причина", "Скв.", "Потери, т"], rows,
                       widths=[2.8, 0.7, 1.0])


def _power(sheet: Sheet, r: DailyReport, x: float, y: float,
           w: float) -> float:
    """Энергетика: выработка и остатки дизтоплива."""
    p = r.power
    top = sheet.block(x, y, w, "Энергетика",
                      f"выработка {num(p.total_with_psp, 1)} МВт·ч")
    rows = [["Газ, МВт", num(p.generation_gas, 1)],
            ["Нефть, МВт", num(p.generation_oil, 2)],
            ["Дизтопливо, МВт", num(p.generation_diesel, 2)]]
    rows += [[_short(name, 22) + ", т ДТ", num(tons, 1)]
             for name, tons in p.diesel_stock]
    return sheet.table(x, top, w, ["Показатель", "Значение"], rows,
                       widths=[2.4, 1.0])


def _injection(sheet: Sheet, r: DailyReport, x: float, y: float,
               w: float) -> float:
    """Поддержание пластового давления."""
    top = sheet.block(x, y, w, "Поддержание пластового давления")
    source = list(r.injection)
    total = r.injection_total
    rows = [[_short(item.name, 22), num(item.plan_day), num(item.fact_day),
             signed(item.dev_day)] for item in source]
    if total is not None:
        source.append(total)
        rows.append(["Всего", num(total.plan_day), num(total.fact_day),
                     signed(total.dev_day)])
    if not rows:
        rows = [["нет данных по закачке", "", "", ""]]
    marks = {(index, 3): T.status_color(item.dev_day)
             for index, item in enumerate(source)
             if item.dev_day is not None}
    return sheet.table(x, top, w, ["Объект", "Режим, м³", "Факт, м³", "±"],
                       rows, widths=[2.0, 1.0, 1.0, 0.8], cell_colors=marks)


def _tanks(sheet: Sheet, r: DailyReport, x: float, y: float,
           w: float) -> float:
    """Резервуарный парк."""
    top = sheet.block(x, y, w, "Резервуарный парк",
                      f"свободно {num(r.free_volume_total_m3)} м³")
    rows = [[_short(t.name, 22), num(t.level, 2), num(t.volume), num(t.free)]
            for t in r.tanks]
    if not rows:
        rows = [["нет данных по резервуарам", "", "", ""]]
    return sheet.table(x, top, w,
                       ["Резервуар", "Взлив, м", "Объём, м³", "Свободно"],
                       rows, widths=[2.0, 0.9, 1.0, 1.0])


def _quality(sheet: Sheet, r: DailyReport, x: float, y: float,
             w: float) -> float:
    """Качество товарной нефти."""
    top = sheet.block(x, y, w, "Качество товарной нефти")
    rows = [[_short(q.node, 18), num(q.density, 1), num(q.water, 2),
             num(q.h2s, 1), num(q.salts, 1)] for q in r.quality]
    if not rows:
        rows = [["нет данных по качеству", "", "", "", ""]]
    return sheet.table(x, top, w,
                       ["Узел учёта", "ρ, кг/м³", "Вода, %", "H₂S", "Соли"],
                       rows, widths=[1.7, 1.0, 0.9, 0.8, 0.9])


def _gas(sheet: Sheet, r: DailyReport, x: float, y: float, w: float) -> float:
    """Попутный нефтяной газ."""
    top = sheet.block(x, y, w, "Попутный нефтяной газ",
                      f"утилизация {pct(r.gas_utilization_pct, 2)}")
    rows = [[_short(g.name, 24), num(g.day_plan, 1), num(g.day_fact, 1),
             num(g.year_fact)] for g in r.gas]
    if not rows:
        rows = [["нет данных по газу", "", "", ""]]
    return sheet.table(x, top, w,
                       ["Показатель", "БП, тыс. м³", "Факт", "Год"],
                       rows, widths=[2.0, 1.0, 0.9, 1.0])


def _drilling(sheet: Sheet, r: DailyReport, x: float, y: float,
              w: float) -> float:
    """Скважины в бурении."""
    rest = max(len(r.drilling) - TOP_DRILLING, 0)
    note = f"{len(r.drilling)} скв. у подрядчиков"
    if rest:
        note += f", показано {TOP_DRILLING}"
    top = sheet.block(x, y, w, "Бурение", note)
    rows = [[_short(item.contractor, 10), _short(item.field_name, 9),
             item.well, num(item.target_depth),
             item.current_depth_text or num(item.current_depth)]
            for item in r.drilling[:TOP_DRILLING]]
    if not rows:
        rows = [["скважин в бурении нет", "", "", "", ""]]
    return sheet.table(x, top, w,
                       ["Подрядчик", "Месторожд.", "Скв.", "Проект, м",
                        "Забой, м"],
                       rows, widths=[1.5, 1.3, 0.8, 1.0, 1.0])


def _ramp_up(sheet: Sheet, r: DailyReport, x: float, y: float,
             w: float) -> float:
    """Вывод скважин на режим после мероприятий."""
    rest = max(len(r.ramp_up) - TOP_BOTTOM, 0)
    note = f"{len(r.ramp_up)} скв."
    if rest:
        note += f", показано {TOP_BOTTOM}"
    top = sheet.block(x, y, w, "Вывод на режим", note)
    rows = [[item.well, _short(item.field_name, 10), _short(item.gtm, 14),
             num(item.plan_qo, 1), num(item.fact_qo, 1)]
            for item in r.ramp_up[:TOP_BOTTOM]]
    if not rows:
        rows = [["скважин на выводе нет", "", "", "", ""]]
    return sheet.table(x, top, w,
                       ["Скв.", "Месторожд.", "ГТМ", "План, т", "Факт, т"],
                       rows, widths=[0.8, 1.3, 1.8, 0.9, 0.9])


def _pigging(sheet: Sheet, r: DailyReport, x: float, y: float,
             w: float) -> float:
    """Очистка трубопроводов."""
    rest = max(len(r.pigging) - TOP_BOTTOM, 0)
    note = f"{len(r.pigging)} пусков"
    if rest:
        note += f", показано {TOP_BOTTOM}"
    top = sheet.block(x, y, w, "Очистные устройства", note)
    rows = [[_short(item.section or item.line, 22),
             item.launch.strftime("%d.%m %H:%M") if item.launch else "—",
             item.receive.strftime("%d.%m %H:%M") if item.receive else "—"]
            for item in r.pigging[:TOP_BOTTOM]]
    if not rows:
        rows = [["пусков за сутки не было", "", ""]]
    return sheet.table(x, top, w, ["Участок", "Пуск", "Приём"], rows,
                       widths=[2.2, 1.2, 1.2])


def _movement(sheet: Sheet, r: DailyReport, x: float, y: float,
              w: float) -> float:
    """Движение фонда за сутки: запуски и остановки."""
    top = sheet.block(x, y, w, "Движение фонда")
    stock = r.stock_total
    rows = [
        ["Запущено скважин", num(r.startups_total.count),
         num(r.startups_total.qo, 1)],
        ["Остановлено скважин", num(r.shutdowns_total.count),
         num(r.shutdowns_total.qo, 1)],
        ["В работе", num(stock.in_work if stock else None),
         signed(stock.in_work_delta if stock else None)],
    ]
    return sheet.table(x, top, w, ["Показатель", "Скв.", "т/сут"], rows,
                       widths=[2.4, 0.8, 1.0])


def _incidents(sheet: Sheet, r: DailyReport, x: float, y: float,
               w: float) -> float:
    """Происшествия за отчётные сутки.

    Состав столбцов тот же, что на первом слайде доклада. Описание
    происшествия в рапорте содержит фамилии и сведения о состоянии
    здоровья; на листе оно приводится так же, как на слайде, потому
    что лист собирается прямо из файла рапорта и через хранилище
    системы эти сведения не проходят.
    """
    items = r.hse.incidents
    note = f"обращений в здравпункт {num(r.hse.medical_count)}"
    top = sheet.block(x, y, w, "Промышленная безопасность", note)
    if not items:
        sheet.deck.write(
            sheet.deck.textbox(sheet.slide, x, top + 0.1, w, 0.7),
            "Происшествий, аварий и инцидентов за отчётные сутки "
            "не зарегистрировано.", size=SIZE_TABLE, bold=True, color=T.GOOD)
        return top + 0.8

    rows = [[_short(i.get("dzo", ""), 16), _short(i.get("field", ""), 18),
             _short(i.get("area", ""), 16), _short(i.get("type", ""), 16),
             _short(i.get("description", ""), 54)]
            for i in items[:TOP_BOTTOM]]
    return sheet.table(x, top, w,
                       ["ДЗО", "Месторождение", "Область события", "Тип",
                        "Описание"],
                       rows, widths=[1.2, 1.5, 1.4, 1.2, 4.2],
                       aligns=[PP_ALIGN.LEFT] * 5)


def _footer(deck: Deck, sheet: Sheet) -> None:
    """Подвал: оговорки и гриф."""
    deck.line(sheet.slide, MARGIN, FOOTER_TOP, CONTENT_W, color=T.LINE)
    note = ("Перечни месторождений, фонда и скважин в бурении приведены "
            "до заданного числа строк; остаток сведён в строку «прочие» "
            "и в сумме учтён. Полные перечни — в презентации доклада "
            f"за те же отчётные сутки. Пометка «{DERIVED}» означает "
            "величину, вычисленную программой; её слагаемые раскрыты "
            "в системе, раздел «Откуда цифры».")
    deck.write(deck.textbox(sheet.slide, MARGIN, FOOTER_TOP + 0.14,
                            CONTENT_W - 10.0, 1.0),
               note, size=SIZE_FOOT, color=T.MUTED)
    deck.write(deck.textbox(sheet.slide, A3_W_CM - MARGIN - 10.0,
                            FOOTER_TOP + 0.14, 10.0, 0.6),
               T.CONFIDENTIALITY, size=SIZE_FOOT, color=T.MUTED,
               align=PP_ALIGN.RIGHT)


def build(r: DailyReport, output: str, assets_dir: str | None = None) -> str:
    """Собрать лист А3 за отчётные сутки.

    Args:
        r: Разобранный суточный рапорт.
        output: Путь к создаваемому файлу .pptx.
        assets_dir: Каталог для кэша растрового знака.

    Returns:
        Путь к созданному файлу.
    """
    deck = Deck(assets_dir=assets_dir, size=(A3_W_CM, A3_H_CM))
    slide = deck.blank_slide()
    sheet = Sheet(deck, slide)

    y = _header(deck, sheet, r)
    y = _tiles(sheet, r, y)

    col = (CONTENT_W - 3 * GAP) / 4
    x1 = MARGIN
    x2 = MARGIN + col + GAP
    x3 = MARGIN + 2 * (col + GAP)
    x4 = MARGIN + 3 * (col + GAP)
    wide = 2 * col + GAP

    left = _potential(sheet, r, x1, y, col)
    _fields(sheet, r, x1, left + GAP, col)

    second = _stock(sheet, r, x2, y, col)
    second = _downtime(sheet, r, x2, second + GAP, col)
    _movement(sheet, r, x2, second + GAP, col)

    third = _injection(sheet, r, x3, y, col)
    third = _tanks(sheet, r, x3, third + GAP, col)
    _quality(sheet, r, x3, third + GAP, col)

    fourth = _gas(sheet, r, x4, y, col)
    fourth = _power(sheet, r, x4, fourth + GAP, col)
    _drilling(sheet, r, x4, fourth + GAP, col)

    _ramp_up(sheet, r, x1, BAND, col)
    _pigging(sheet, r, x2, BAND, col)
    _incidents(sheet, r, x3, BAND, wide)

    _footer(deck, sheet)
    deck.prs.save(output)
    return output
