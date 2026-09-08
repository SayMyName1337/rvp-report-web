# -*- coding: utf-8 -*-
"""Сборка презентации из модели DailyReport.

Каждый слайд — отдельная функция. Порядок и состав задаются списком SLIDES
внизу файла: убрать слайд из доклада = убрать строку из списка.
"""
from __future__ import annotations

import os
import tempfile

from pptx.enum.text import PP_ALIGN

from . import charts, theme as T
from .deck import Deck
from .fmt import DASH, date_ru, num, pct, ratio_pct, short, signed
from ..domain.model import QUALITY_LIMITS, DailyReport
from ..domain.provenance import DERIVED_MARK

CONTENT_W = T.SLIDE_W_CM - 2 * T.MARGIN_CM
LEFT = T.MARGIN_CM
TOP = T.CONTENT_TOP_CM + 0.5

MONTHS_RU = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
             "августа", "сентября", "октября", "ноября", "декабря")


def _date_long(value) -> str:
    """Дата прописью: ``21 июля 2026 г.``"""
    if value is None:
        return DASH
    return f"{value.day} {MONTHS_RU[value.month - 1]} {value.year} г."


def _losses_formula(r: DailyReport) -> str:
    """Расшифровка суммы потерь — цифры рядом с результатом, а не в уме."""
    return (f"{num(r.downtime_total.qo)} простой + "
            f"{num(r.idle_total.qo)} бездействие + "
            f"{num(r.vsp_total.qo, 1)} ВСП")


def _kpi_row(deck: Deck, slide, tiles: list[dict], y: float,
             height: float = 3.5, gap: float = 0.35,
             columns: int | None = None,
             width_limit: float | None = None) -> None:
    """Ряд плиток по ширине контента.

    Args:
        tiles: Описания плиток: label, value и необязательные note,
            color, note_color, accent, mark.
        y: Отступ сверху, см.
        height: Высота плитки, см.
        gap: Промежуток между плитками, см.
        columns: На сколько колонок делить ширину. По умолчанию — по числу
            плиток. Задаётся, когда плиток меньше, чем колонок в ряду выше,
            и они должны сохранить ту же ширину.
        width_limit: Ширина полосы под плитки, см. Нужна там, где справа
            стоит таблица и плитки не могут занять весь слайд.
    """
    count = max(columns or len(tiles), 1)
    span = width_limit or CONTENT_W
    width = (span - gap * (count - 1)) / count
    for i, tile in enumerate(tiles):
        deck.kpi(slide, LEFT + i * (width + gap), y, width, height,
                 tile["label"], tile["value"], tile.get("note", ""),
                 tile.get("color", T.INK), tile.get("accent"),
                 tile.get("note_color", T.MUTED), tile.get("mark", ""))


# --- 1. Титул, погода, ПБиОТ -------------------------------------------------
def slide_intro_hse(deck: Deck, r: DailyReport, tmp: str) -> None:
    """Титул с датой и погодой, промышленная безопасность за сутки."""
    slide = deck.slide()
    deck.rect(slide, 0, 0, T.SLIDE_W_CM, 5.9, fill=T.BRAND)
    deck.rect(slide, 0, 5.9, T.SLIDE_W_CM, 0.16, fill=T.ACCENT)
    deck.place_logo(slide, LEFT, 1.3, 1.4, on_dark=True)
    deck.write(deck.textbox(slide, LEFT, 3.4, CONTENT_W, 1.6),
               "Суточный рапорт с промысла", size=T.SIZE_TITLE, bold=True,
               color=T.CANVAS)
    deck.write(deck.textbox(slide, LEFT, 5.05, CONTENT_W, 0.9),
               _date_long(r.report_date), size=T.SIZE_SUBTITLE,
               color=T.CANVAS)

    deck.section_title(slide, 6.3, "Промышленная безопасность и охрана труда",
                       "События за отчётные сутки")

    incidents = r.hse.incidents
    _kpi_row(deck, slide, [
        {"label": "Происшествий", "value": num(len(incidents)),
         "note": "за сутки",
         "color": T.GOOD if not incidents else T.BAD,
         "accent": T.GOOD if not incidents else T.BAD},
        {"label": "Обращений в здравпункт", "value": num(r.hse.medical_count),
         "note": "все данные — в суточном рапорте", "accent": T.BRAND_LIGHT},
    ], y=9.1, height=3.2, columns=4)
    _weather_tile(deck, slide, r, y=9.1, height=3.2)

    y = 12.7
    if incidents:
        rows = [[short(i.get("dzo", ""), 18), short(i.get("field", ""), 20),
                 short(i.get("area", ""), 18), short(i.get("type", ""), 18),
                 short(i.get("description", ""), 60),
                 short(i.get("consequences", ""), 34)] for i in incidents[:4]]
        deck.table(slide, LEFT, y, CONTENT_W,
                   ["ДЗО", "Месторождение", "Область события", "Тип",
                    "Описание", "Последствия"],
                   rows, widths=[1.4, 1.6, 1.4, 1.2, 4.0, 2.4], row_h=1.0,
                   aligns=[PP_ALIGN.LEFT] * 6)
        y += 0.78 + 1.0 * len(rows) + 0.5
    else:
        deck.rect(slide, LEFT, y, CONTENT_W, 2.6, fill=T.PANEL, rounded=True)
        deck.write(deck.textbox(slide, LEFT + 0.8, y + 0.9,
                                CONTENT_W - 1.6, 1.2),
                   "Происшествий, аварий и инцидентов за отчётные сутки "
                   "не зарегистрировано.", size=T.SIZE_BODY, color=T.GOOD,
                   bold=True)
        y += 3.2

    deck.note(slide, LEFT, min(y + 0.4, 16.3), CONTENT_W,
              "Сведения об обращениях в здравпункт содержат персональные "
              "данные (ФИО, сведения о состоянии здоровья) и в презентацию "
              "не выносятся. Детальная информация — в суточном рапорте "
              "у ответственного должностного лица.", size=T.SIZE_FOOTER)


def _weather_tile(deck: Deck, slide, r: DailyReport, y: float,
                  height: float) -> None:
    """Плитка погоды: температура и ветер двумя значениями рядом.

    Ветер в рапорте записан одной ячейкой вида «7 СВ» — скорость
    и направление вместе, поэтому выводится как есть.

    Args:
        deck: Презентация.
        slide: Слайд размещения.
        r: Прочитанный суточный рапорт.
        y: Отступ сверху, см.
        height: Высота плитки, см.
    """
    gap = 0.35
    width = (CONTENT_W - gap * 3) / 4
    x = LEFT + 3 * (width + gap)
    deck.rect(slide, x, y, width, height, fill=T.PANEL, rounded=True)
    deck.rect(slide, x, y, 0.14, height, fill=T.BRAND_LIGHT)

    pad = 0.45
    deck.write(deck.textbox(slide, x + pad, y + 0.35, width - 2 * pad, 0.6),
               "ПОГОДА", size=T.SIZE_KPI_LABEL, color=T.MUTED, bold=True)
    half = (width - 2 * pad) / 2
    columns = (("Температура, °C", num(r.temperature)),
               ("Ветер, м/с", r.wind or DASH))
    for index, (caption, value) in enumerate(columns):
        left = x + pad + index * half
        deck.write(deck.textbox(slide, left, y + 1.0, half, 0.6),
                   caption, size=T.SIZE_KPI_LABEL, color=T.MUTED)
        deck.write(deck.textbox(slide, left, y + 1.55, half, 1.2),
                   value, size=T.SIZE_KPI, bold=True, color=T.INK)


# --- 2. Ключевые показатели --------------------------------------------------
def slide_kpi(deck: Deck, r: DailyReport, tmp: str) -> None:
    """Ключевые показатели за сутки: двенадцать плиток."""
    p, d = r.production, r.delivery
    slide = deck.slide("Ключевые показатели за сутки",
                       f"Отчётная дата — {date_ru(r.report_date)}")

    stock_delta = r.stock_total.in_work_delta if r.stock_total else None
    _kpi_row(deck, slide, [
        {"label": "Добыча нефти, т",
         "value": num(p.closed_day, 1),
         "note": f"план СГ {num(p.plan_sg_day)}  ·  "
                 f"{signed(p.dev_sg_day, 1)} к СГ",
         "note_color": T.status_color(p.dev_sg_day),
         "accent": T.status_color(p.dev_sg_day)},
        {"label": "К бизнес-плану, т/сут",
         "value": signed(p.dev_bp_day, 1),
         "note": f"план БП {num(p.plan_bp_day)}",
         "color": T.status_color(p.dev_bp_day),
         "accent": T.status_color(p.dev_bp_day)},
        {"label": "Нарастающая за месяц, т",
         "value": num(p.cumulative_month),
         "note": f"{signed(p.dev_sg_month)} к СГ  ·  "
                 f"{signed(p.dev_bp_month)} к БП",
         "note_color": T.status_color(p.dev_bp_month),
         "accent": T.status_color(p.dev_bp_month)},
        {"label": "Сдача нефти, т",
         "value": num(d.fact_day),
         "note": f"план {num(d.plan_day)}  ·  {signed(d.dev_day)}",
         "note_color": T.status_color(d.dev_day),
         "accent": T.status_color(d.dev_day)},
    ], y=TOP)

    _kpi_row(deck, slide, [
        {"label": "Потери добычи, т/сут", "value": num(r.total_losses),
         "note": _losses_formula(r),
         "note_color": T.BAD, "accent": T.BAD, "mark": DERIVED_MARK},
        {"label": "Фонд в работе",
         "value": num(r.stock_total.in_work if r.stock_total else None),
         "note": f"{signed(stock_delta)} за сутки",
         "note_color": T.status_color(stock_delta),
         "accent": T.status_color(stock_delta)},
        {"label": "Утилизация газа", "value": pct(r.gas_utilization_pct, 2),
         "note": "целевой уровень — не ниже 95 %",
         "note_color": T.GOOD if (r.gas_utilization_pct or 0) >= 95 else T.BAD,
         "accent": T.GOOD if (r.gas_utilization_pct or 0) >= 95 else T.BAD},
        {"label": "Выработка э/э, МВт·ч",
         "value": num(r.power.total_with_psp, 1),
         "note": f"{signed(r.power.total_with_psp_delta, 2)} к прошлым суткам",
         "note_color": T.status_color(r.power.total_with_psp_delta),
         "accent": T.BRAND},
    ], y=TOP + 4.1)

    injection_plan = r.injection_total.plan_day if r.injection_total else None
    injection_fact = r.injection_total.fact_day if r.injection_total else None
    _kpi_row(deck, slide, [
        {"label": "Закачка ППД, м³/сут",
         "value": num(injection_fact),
         "note": f"режим {num(injection_plan)}",
         "accent": T.BRAND_LIGHT},
        {"label": "НСЖ ЦОМ, м³", "value": num(p.nsj_fact),
         "note": f"{signed(p.nsj_dev)} к закрытию", "accent": T.BRAND_LIGHT},
        {"label": "Свободный объём, м³", "value": num(r.free_volume_total_m3),
         "note": "по всем объектам", "accent": T.BRAND_LIGHT},
        {"label": "В бурении", "value": num(len(r.drilling)),
         "note": "скважин", "accent": T.BRAND_LIGHT},
    ], y=TOP + 8.2)


# --- 3. Потенциал ------------------------------------------------------------
#: Столбцы диаграммы потенциала: подпись, поле модели и цвет.
POTENTIAL_BARS = (
    ("Потенциал", "potential_com", T.MUTED),
    ("Потенциал с учётом\nограничений", "potential_limited", T.WARN),
    ("Закрытие по сводке\nза сутки", "closed_day", T.BRAND),
    ("Факт ЦОМ\nза сутки", "fact_com_day", T.ACCENT),
)


def slide_potential(deck: Deck, r: DailyReport, tmp: str) -> None:
    """Потенциал добычи и его потери на технологических ограничениях."""
    p = r.production
    slide = deck.slide("Потенциал",
                       "Потери потенциала за счёт технологических ограничений")

    categories = [name for name, _attr, _color in POTENTIAL_BARS]
    values = [getattr(p, attr) for _name, attr, _color in POTENTIAL_BARS]
    colors = [color for _name, _attr, color in POTENTIAL_BARS]

    delta = None
    if p.fact_com_day is not None and p.closed_day is not None:
        delta = p.fact_com_day - p.closed_day
    categories.append("Дельта закрытия\nи факта ЦОМ")
    values.append(delta)
    colors.append(T.BRAND_LIGHT)

    if any(value is not None for value in values):
        deck.column_chart(slide, 1.0, 3.1, 18.5, 11.5,
                          categories, values, colors)

    rows = [
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
    deviations = {5: p.dev_sg_day, 6: p.dev_bp_day, 7: p.dev_sg_month,
                  8: p.dev_bp_month, 9: p.dev_bp_year}
    marks = {(i, 1): T.status_color(v) for i, v in deviations.items()}
    deck.table(slide, 19.8, 3.8, CONTENT_W - 18.4, ["Показатель", "Значение"],
               rows, widths=[2.2, 1.0], row_h=0.78, cell_colors=marks)

    deck.note(slide, LEFT, 15.5, 18.5,
              f"НСЖ: закрытие {num(p.nsj_closed)} м³, факт ЦОМ "
              f"{num(p.nsj_fact)} м³, отклонение {signed(p.nsj_dev)} м³.")


# --- 4. Добыча по месторождениям ---------------------------------------------
def slide_fields(deck: Deck, r: DailyReport, tmp: str) -> None:
    """Добыча по месторождениям и вклад крупнейших."""
    items = [(name, value) for name, value in r.production.by_field if value > 0]
    slide = deck.slide(
        "Добыча по месторождениям",
        f"Всего за сутки — {num(r.production.closed_day, 1)} т  ·  "
        f"{len(items)} действующих объектов")
    if not items:
        deck.note(slide, LEFT, TOP, CONTENT_W, "Нет данных по месторождениям.")
        return

    path = charts.hbar(os.path.join(tmp, "fields.png"), items, unit="т",
                       size=(9.4, 6.6))
    deck.picture(slide, path, LEFT, TOP, w=19.0)

    total = sum(v for _, v in items) or 1.0
    top = sorted(items, key=lambda x: x[1], reverse=True)[:5]
    rows = [[short(name, 26), num(value, 1), pct(value / total * 100, 1)]
            for name, value in top]
    x = LEFT + 20.0
    deck.write(deck.textbox(slide, x, TOP, CONTENT_W - 20.0, 0.8),
               "Основной вклад", size=T.SIZE_BODY, bold=True, color=T.BRAND)
    deck.table(slide, x, TOP + 0.9, CONTENT_W - 20.0,
               ["Месторождение", "т/сут", "доля"], rows,
               widths=[2.4, 1.0, 0.8], row_h=0.82)
    covered = sum(v for _, v in top) / total * 100
    deck.note(slide, x, TOP + 6.4, CONTENT_W - 20.0,
              f"Пять месторождений дают {covered:.0f} % суточной добычи.")


# --- 5. Состояние и движение фонда скважин -----------------------------------
def slide_stock_movement(deck: Deck, r: DailyReport, tmp: str) -> None:
    """Фонд скважин и его движение за сутки на одном слайде."""
    stock = r.stock_total
    slide = deck.slide("Состояние и движение фонда скважин",
                       "Нефтяной фонд ООО «СК Русвьетпетро»")
    if stock is None:
        deck.note(slide, LEFT, TOP, CONTENT_W, "Нет данных по фонду.")
        return

    path = charts.stock_funnel(os.path.join(tmp, "funnel.png"), [
        ("Общий фонд", stock.total or 0),
        ("Эксплуатационный", stock.operating_stock or 0),
        ("В работе", stock.in_work or 0),
    ], size=(9.4, 2.0))
    deck.picture(slide, path, LEFT, 3.1, w=13.6)

    rows = [
        ["Общий фонд", num(stock.total)],
        ["Эксплуатационный", num(stock.operating_stock)],
        ["в работе", num(stock.in_work)],
        ["в текущем простое", num(stock.in_downtime)],
        ["в бездействии", num(stock.in_idle)],
        ["в ожидании освоения", num(stock.awaiting)],
        ["Нагнетательные", num(stock.inj_total)],
        ["Наблюдательные", num(stock.observation)],
        ["В консервации", num(stock.conservation)],
        ["Ликвидированные", num(stock.liquidated)],
    ]
    deck.table(slide, 26.3, 3.4, CONTENT_W - 24.9, ["Категория", "Скв."],
               rows, widths=[2.4, 1.0], row_h=0.72)

    _kpi_row(deck, slide, [
        {"label": "В работе", "value": num(stock.in_work),
         "note": f"{signed(stock.in_work_delta)} за сутки",
         "color": T.status_color(stock.in_work_delta), "accent": T.GOOD},
        {"label": "Текущий простой", "value": num(stock.in_downtime),
         "note": f"{num(stock.downtime_rate, 1)} т/сут", "accent": T.WARN},
        {"label": "Бездействие", "value": num(stock.in_idle),
         "note": f"{num(stock.idle_rate, 1)} т/сут", "accent": T.BAD},
    ], y=6.15, height=3.2, columns=4, width_limit=24.9)

    _kpi_row(deck, slide, [
        {"label": "Запущено скважин", "value": num(r.startups_total.count),
         "note": f"{num(r.startups_total.qo, 1)} т/сут", "accent": T.GOOD},
        {"label": "Остановлено скважин", "value": num(r.shutdowns_total.count),
         "note": f"{num(r.shutdowns_total.qo, 1)} т/сут", "accent": T.BAD},
        {"label": "На выводе на режим",
         "value": num(r.ramp_up_total.get("count")),
         "note": f"факт {num(r.ramp_up_total.get('fact_qo'), 1)} т/сут "
                 f"из {num(r.ramp_up_total.get('plan_qo'), 1)}",
         "accent": T.BRAND},
        {"label": "Внутрисменные потери", "value": num(r.vsp_total.qo, 1),
         "note": f"{num(r.vsp_total.count)} скв., т/сут", "accent": T.WARN},
    ], y=9.45, height=3.2, columns=4, width_limit=24.9)

    if r.ramp_up:
        rows = []
        for item in r.ramp_up[:5]:
            rows.append([
                item.well, short(item.field_name, 22), short(item.gtm, 18),
                item.days or DASH, num(item.plan_qo, 1), num(item.fact_qo, 1),
                ratio_pct(item.fact_qo, item.plan_qo), short(item.note, 26)])
        marks = {}
        for i, item in enumerate(r.ramp_up[:5]):
            if item.plan_qo:
                marks[(i, 6)] = T.status_color(
                    (item.fact_qo or 0) - 0.8 * item.plan_qo)
        deck.table(slide, LEFT, 12.9, CONTENT_W,
                   ["Скв.", "Месторождение", "Вид ГТМ", "Дней", "План, т",
                    "Факт, т", "Вып.", "Состояние"], rows,
                   widths=[0.8, 2.2, 1.8, 0.7, 1.0, 1.0, 0.8, 2.4],
                   row_h=0.72, cell_colors=marks)

    if r.shutdowns_note:
        deck.write(deck.textbox(slide, LEFT + 0.1, 17.2, CONTENT_W, 0.8),
                   f"Остановки: {short(r.shutdowns_note, 200)}",
                   size=T.SIZE_BODY, color=T.INK)


# --- 9. ППД ------------------------------------------------------------------
def slide_injection(deck: Deck, r: DailyReport, tmp: str) -> None:
    """Поддержание пластового давления по объектам."""
    total = r.injection_total
    slide = deck.slide(
        "Поддержание пластового давления",
        f"Закачка за сутки — {num(total.fact_day if total else None)} м³ "
        f"при режиме {num(total.plan_day if total else None)} м³")

    items = [(short(i.name, 16), i.plan_day or 0, i.fact_day or 0)
             for i in r.injection]
    if items:
        path = charts.plan_fact(os.path.join(tmp, "ppd.png"), items, unit="м³",
                                size=(9.4, 3.6))
        deck.picture(slide, path, LEFT, TOP, w=18.6)

    rows = []
    for i in r.injection:
        rows.append([
            short(i.name, 18), num(i.plan_day), num(i.fact_day),
            signed(i.dev_day), num(i.plan_month), num(i.fact_month),
            signed(i.dev_month), num(i.oil_in_water, 1), num(i.kvch, 0),
        ])
    if total:
        rows.append(["Всего", num(total.plan_day), num(total.fact_day),
                     signed(total.dev_day), num(total.plan_month),
                     num(total.fact_month), signed(total.dev_month), DASH, DASH])
    colors = {}
    for i, item in enumerate(r.injection):
        colors[(i, 3)] = T.status_color(item.dev_day)
        colors[(i, 6)] = T.status_color(item.dev_month)
    deck.table(slide, LEFT, TOP + 7.0, CONTENT_W,
               ["Объект", "Режим сут., м³", "Факт сут., м³", "±",
                "Режим мес., м³", "Факт мес., м³", "±",
                "Нефть в воде, мг/дм³", "КВЧ, мг/дм³"],
               rows, widths=[1.6, 1.2, 1.2, 1.0, 1.2, 1.2, 1.0, 1.3, 1.1],
               row_h=0.85, cell_colors=colors)


# --- 10. Подготовка и сдача --------------------------------------------------
def slide_delivery(deck: Deck, r: DailyReport, tmp: str) -> None:
    """Подготовка и сдача нефти: резервуары и качество."""
    d = r.delivery
    slide = deck.slide("Подготовка и сдача нефти",
                       "Товарный парк, сдача, качество товарной нефти")

    _kpi_row(deck, slide, [
        {"label": "Перевалка с ПСП «Мусюршор» на ПСП «Головные», т",
         "value": num(d.fact_day),
         "note": f"план {num(d.plan_day)}  ·  {signed(d.dev_day)}",
         "note_color": T.status_color(d.dev_day),
         "accent": T.status_color(d.dev_day)},
        {"label": "Сдача в ТН, т", "value": num(d.tn_fact_day),
         "note": f"план {num(d.tn_plan_day)}  ·  {signed(d.tn_dev_day)}",
         "note_color": T.status_color(d.tn_dev_day), "accent": T.BRAND},
        {"label": "Свободный объём, м³", "value": num(r.free_volume_total_m3),
         "note": "по всем резервуарам", "accent": T.BRAND_LIGHT},
    ], y=TOP, height=3.8, columns=4)

    y = TOP + 4.4
    deck.write(deck.textbox(slide, LEFT, y, 15.0, 0.8), "Резервуарный парк",
               size=T.SIZE_BODY, bold=True, color=T.BRAND)
    rows = [[short(t.name, 24), num(t.level, 2), num(t.volume), signed(t.delta),
             num(t.free)] for t in r.tanks]
    deck.table(slide, LEFT, y + 0.9, 15.0,
               ["Резервуар", "Взлив, м", "Объём, м³", "± сут.", "Свободно, м³"],
               rows, widths=[2.0, 1.0, 1.1, 1.0, 1.2], row_h=0.8)

    x = LEFT + 16.0
    w = CONTENT_W - 16.0
    deck.write(deck.textbox(slide, x, y, w, 0.8), "Качество товарной нефти",
               size=T.SIZE_BODY, bold=True, color=T.BRAND)
    rows, colors = [], {}
    for i, q in enumerate(r.quality):
        rows.append([
            q.node, num(q.density, 1), num(q.water, 2), num(q.solids, 4),
            num(q.sulfur, 2), num(q.h2s, 1), num(q.mercaptans, 1),
            num(q.chlorides, 2), num(q.salts, 1),
        ])
        for col, attr in ((3, "solids"), (5, "h2s"), (6, "mercaptans"),
                          (7, "chlorides"), (8, "salts")):
            value = getattr(q, attr)
            if value is not None:
                colors[(i, col)] = (T.BAD if value > QUALITY_LIMITS[attr]
                                    else T.GOOD)
    deck.table(slide, x, y + 0.9, w,
               ["Узел учёта", "ρ, кг/м³", "Вода, %", "Мех. примеси, %",
                "Сера, %", "H₂S, ppm", "Меркаптаны, ppm", "Хлориды, ppm",
                "Соли, мг/дм³"],
               rows, widths=[1.8, 1.0, 0.9, 1.2, 0.85, 0.95, 1.2, 1.05, 1.15],
               row_h=0.8, head_h=1.45)
    # PowerPoint растягивает строки под текст, поэтому подпись ставится
    # на заведомо свободной высоте, а не считается от числа строк
    deck.note(slide, x, T.QUALITY_NOTE_TOP, w,
              "Нормативы: мех. примеси < 0,05 %  ·  H₂S < 20 ppm  ·  "
              "меркаптаны < 40 ppm  ·  орг. хлориды < 6 ppm  ·  "
              "хлористые соли < 100 мг/дм³.")


# --- 11. Газ -----------------------------------------------------------------
def slide_gas(deck: Deck, r: DailyReport, tmp: str) -> None:
    """Попутный нефтяной газ: добыча, утилизация, факел."""
    slide = deck.slide("Попутный нефтяной газ",
                       "Добыча, утилизация, сжигание на факеле")

    by_name = {g.name: g for g in r.gas}
    produced = next((g for n, g in by_name.items() if "обыча" in n), None)
    flare = next((g for n, g in by_name.items() if "акел" in n), None)

    _kpi_row(deck, slide, [
        {"label": "Добыча газа, тыс. м³",
         "value": num(produced.day_fact if produced else None),
         "note": f"БП {num(produced.day_plan if produced else None)}  ·  "
                 f"{signed(produced.day_dev if produced else None)}",
         "color": T.status_color(produced.day_dev if produced else None),
         "accent": T.BRAND},
        {"label": "Утилизация", "value": pct(r.gas_utilization_pct, 2),
         "note": "за сутки",
         "color": T.GOOD if (r.gas_utilization_pct or 0) >= 95 else T.BAD,
         "accent": T.GOOD if (r.gas_utilization_pct or 0) >= 95 else T.BAD},
        {"label": "На факел, тыс. м³",
         "value": num(flare.day_fact if flare else None),
         "note": f"БП {num(flare.day_plan if flare else None)}  ·  "
                 f"{signed(flare.day_dev if flare else None)}",
         "color": T.status_color(flare.day_dev if flare else None, invert=True),
         "accent": T.WARN},
        {"label": "С начала года, тыс. м³",
         "value": num(produced.year_fact if produced else None),
         "note": "добыча газа", "accent": T.BRAND_LIGHT},
    ], y=TOP, height=3.4)

    rows = []
    for g in r.gas:
        rows.append([short(g.name, 30), num(g.day_plan, 1), num(g.day_fact, 1),
                     signed(g.day_dev, 1), num(g.month_fact, 1),
                     num(g.year_fact, 1)])
    deck.table(slide, LEFT, TOP + 4.2, CONTENT_W,
               ["Показатель", "Сутки, БП", "Сутки, факт", "±",
                "Месяц, факт", "Год, факт"],
               rows, widths=[2.6, 1.2, 1.2, 1.0, 1.2, 1.2], row_h=0.9,
               cell_colors={(i, 3): T.status_color(g.day_dev)
                            for i, g in enumerate(r.gas)})

    deck.note(slide, LEFT, TOP + 4.2 + 0.78 + 0.9 * len(rows) + 0.6, CONTENT_W,
              "Целевой уровень утилизации ПНГ — не ниже 95 %.", size=T.SIZE_BODY)


# --- 12. Энергетика ----------------------------------------------------------
def slide_power(deck: Deck, r: DailyReport, tmp: str) -> None:
    """Энергетика: выработка и остатки дизельного топлива."""
    p = r.power
    slide = deck.slide("Энергетика",
                       "Выработка электроэнергии и состояние оборудования")

    _kpi_row(deck, slide, [
        {"label": "Выработка СХ+ЗХ+ПСП, МВт·ч",
         "value": num(p.total_with_psp, 2),
         "note": f"{signed(p.total_with_psp_delta, 2)} к прошлым суткам",
         "note_color": T.status_color(p.total_with_psp_delta),
         "accent": T.BRAND},
        {"label": "На газу, МВт", "value": num(p.generation_gas, 1),
         "note": f"{num(p.count_gpea)} ГПЭА + ГТУ + МГТУ в работе",
         "accent": T.GOOD},
        {"label": "На нефти, МВт", "value": num(p.generation_oil, 2),
         "note": f"{num(p.count_nes)} НЭС в работе", "accent": T.BRAND_LIGHT},
        {"label": "На дизтопливе, МВт", "value": num(p.generation_diesel, 2),
         "note": f"{num(p.count_dies)} ДЭС в работе", "accent": T.WARN},
    ], y=TOP, height=3.4)

    y = TOP + 4.1
    if p.diesel_stock:
        deck.write(deck.textbox(slide, LEFT, y, 12.0, 0.8),
                   "Остатки дизельного топлива на 24:00, т",
                   size=T.SIZE_BODY, bold=True, color=T.BRAND)
        rows = [[short(name, 22), num(value, 1)] for name, value in p.diesel_stock]
        deck.table(slide, LEFT, y + 0.9, 12.0, ["Объект", "Тонн"], rows,
                   widths=[2.2, 1.0], row_h=0.82)


# --- 13. Бурение и очистные устройства ---------------------------------------
def slide_drilling(deck: Deck, r: DailyReport, tmp: str) -> None:
    """Бурение и очистка трубопроводов."""
    slide = deck.slide("Бурение и очистка трубопроводов",
                       f"{len(r.drilling)} скважин в работе буровых подрядчиков")

    items = [(f"{d.well} · {d.field_name}", d.target_depth, d.current_depth)
             for d in r.drilling
             if d.target_depth and d.current_depth]
    if items:
        path = charts.drilling_progress(os.path.join(tmp, "drilling.png"), items,
                                        size=(9.4, 3.8))
        deck.picture(slide, path, LEFT, TOP, w=18.6)

    rows = []
    for d in r.drilling:
        depth = num(d.current_depth) if d.current_depth is not None \
            else (d.current_depth_text or DASH)
        rows.append([d.contractor, d.field_name, d.well,
                     num(d.target_depth), depth, date_ru(d.start_date)])
    deck.table(slide, LEFT, TOP + 7.2, 18.6,
               ["Подрядчик", "Месторождение", "Скв.", "Проект, м",
                "Забой на 6:00", "Начало бурения"],
               rows, widths=[1.2, 1.6, 1.0, 1.2, 1.4, 1.4], row_h=0.82,
               aligns=[PP_ALIGN.LEFT, PP_ALIGN.LEFT, PP_ALIGN.LEFT,
                       PP_ALIGN.RIGHT, PP_ALIGN.RIGHT, PP_ALIGN.RIGHT])

    x = LEFT + 19.6
    w = CONTENT_W - 19.6
    deck.write(deck.textbox(slide, x, TOP, w, 0.8), "Очистные устройства",
               size=T.SIZE_BODY, bold=True, color=T.BRAND)
    rows = [[short(p.section, 30),
             p.launch.strftime("%d.%m %H:%M") if p.launch else DASH,
             p.receive.strftime("%d.%m %H:%M") if p.receive else DASH,
             num(p.travel_h, 1),
             short(p.note, 26)] for p in r.pigging[:8]]
    if rows:
        deck.table(slide, x, TOP + 0.9, w,
                   ["Участок", "Пуск", "Приём", "В пути, ч", "Примечание"],
                   rows, widths=[2.8, 1.1, 1.1, 0.9, 2.1], row_h=0.88,
                   aligns=[PP_ALIGN.LEFT, PP_ALIGN.RIGHT, PP_ALIGN.RIGHT,
                           PP_ALIGN.RIGHT, PP_ALIGN.LEFT])
    else:
        deck.note(slide, x, TOP + 0.9, w, "Пусков очистных устройств за сутки нет.")


#: Сколько места по вертикали остаётся под подпись внизу служебного слайда.
DERIVED_TABLE_LIMIT = 15.4
DERIVED_ROW_H = 0.82


def _derived_table(deck: Deck, slide, r: DailyReport, y: float) -> float:
    """Перечень величин, посчитанных программой, с их расшифровкой.

    Args:
        deck: Презентация, в которую добавляется таблица.
        slide: Слайд размещения.
        r: Прочитанный суточный рапорт.
        y: Отступ сверху, см.

    Returns:
        Нижнюю границу таблицы, чтобы под ней можно было разместить
        следующий элемент, не наложив его сверху.
    """
    items = r.ledger.derived_items
    if not items or y > DERIVED_TABLE_LIMIT:
        return y

    fits = int((DERIVED_TABLE_LIMIT - y - 1.7) / DERIVED_ROW_H)
    rows = [[short(item.label, 46), item.value, short(item.origin, 78)]
            for item in items[:max(0, min(6, fits))]]
    if not rows:
        return y

    deck.write(deck.textbox(slide, LEFT, y, CONTENT_W, 0.8),
               "Величины, посчитанные программой", size=T.SIZE_BODY,
               bold=True, color=T.BRAND)
    deck.table(slide, LEFT, y + 0.9, CONTENT_W,
               ["Показатель", "Значение", "Как получено"], rows,
               widths=[3.0, 1.2, 6.4], row_h=DERIVED_ROW_H,
               aligns=[PP_ALIGN.LEFT, PP_ALIGN.RIGHT, PP_ALIGN.LEFT])
    return y + 0.9 + 0.78 + DERIVED_ROW_H * len(rows)


# --- 15. Служебный: качество данных ------------------------------------------
def slide_data_quality(deck: Deck, r: DailyReport, tmp: str) -> None:
    """Служебный слайд с замечаниями к данным и расчётными величинами.

    Появляется только при обнаружении несоответствий; перед докладом
    удаляется.
    """
    # info-замечания касаются разметки файла, а не данных, и в доклад не идут
    issues = [i for i in r.issues if i.level in ("warning", "error")][:12]
    if not issues:
        return
    slide = deck.slide("Замечания к исходным данным",
                       "Служебный слайд: проверить перед докладом")
    rows = [[i.level.upper(), i.where, short(i.message, 110)] for i in issues]
    deck.table(slide, LEFT, TOP, CONTENT_W, ["Уровень", "Блок", "Замечание"],
               rows, widths=[0.9, 2.4, 7.0], row_h=0.9,
               aligns=[PP_ALIGN.LEFT] * 3,
               cell_colors={(i, 0): (T.BAD if item.level == "error"
                                     else T.WARN_TEXT)
                            for i, item in enumerate(issues)})
    bottom = TOP + 0.78 + 0.9 * len(rows) + 0.9
    bottom = _derived_table(deck, slide, r, bottom)
    deck.note(slide, LEFT, min(bottom + 0.5, 16.8), CONTENT_W,
              "Слайд формируется автоматически и появляется только при "
              "обнаружении несоответствий в исходном файле. "
              "Перед докладом слайд удаляется.", size=T.SIZE_BODY)


SLIDES = [
    slide_intro_hse,
    slide_kpi,
    slide_potential,
    slide_fields,
    slide_stock_movement,
    slide_injection,
    slide_delivery,
    slide_gas,
    slide_power,
    slide_drilling,
    slide_data_quality,
]


def build(report: DailyReport, output: str,
          template: str | None = None) -> str:
    """Собрать презентацию по прочитанному рапорту и сохранить в файл.

    Args:
        report: Прочитанный суточный рапорт.
        output: Путь к создаваемому файлу .pptx.
        template: Корпоративный шаблон .pptx/.potx.

    Returns:
        Путь к созданному файлу.
    """
    with tempfile.TemporaryDirectory(prefix="rvp-charts-") as tmp:
        deck = Deck(template, assets_dir=tmp)
        for make in SLIDES:
            make(deck, report, tmp)
        deck.save(output)
    return output
