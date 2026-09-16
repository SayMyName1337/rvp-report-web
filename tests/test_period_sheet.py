# -*- coding: utf-8 -*-
"""Проверки листа А3 с аналитикой за период.

Лист собирается из готового словаря, без базы: слой отрисовки
о Django не знает. Поэтому здесь проверяется вёрстка и построение
ряда добычи, а не выборки — за них отвечают проверки сводок.

Отдельно проверяется то, ради чего лист вообще отделён от страницы:
оговорка о полноте данных обязана стоять выше цифр, а пропущенные
сутки обязаны остаться разрывом. Лист уходит из системы файлом,
и всё, что о данных нужно знать, обязано уехать вместе с ним.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.util import Cm

from rvp_report.render import period_sheet

#: Допуск при сравнении размеров, сантиметры.
TOLERANCE = 0.05

#: Заголовки блоков листа — по ним подписи опознаются среди надписей.
BLOCK_TITLES = (
    "Добыча", "Итоги периода", "Добыча по месторождениям",
    "Причины простоя", "Наибольшие потери по скважинам",
    "Потери по составляющим", "Попутный нефтяной газ",
)


def _series(start: date, days: int, skip: set[int] | None = None) -> list:
    """Ряд суток периода; номера из ``skip`` пропускаются."""
    skip = skip or set()
    return [{"date": start + timedelta(days=index),
             "closed": 8300.0 + index, "plan": 8310.0}
            for index in range(days) if index not in skip]


def _data(start: date = date(2026, 8, 1), end: date = date(2026, 8, 31),
          days: int = 31, skip: set[int] | None = None,
          title: str = "Август 2026") -> dict:
    """Данные листа: настоящих выборок здесь не нужно."""
    rows = _series(start, days, skip)
    present = len(rows)
    expected = (min(end, date(2026, 9, 8)) - start).days + 1
    missing = [start + timedelta(days=index) for index in range(expected)
               if (start + timedelta(days=index)) not in
               {row["date"] for row in rows}]
    return {
        "title": title,
        "start": start,
        "end": end,
        "clamped": False,
        "completeness": {
            "expected": expected, "present": present, "missing": missing,
            "complete": not missing, "unfinished": end > date(2026, 9, 8),
            "needs_review": 0,
            "first": rows[0]["date"] if rows else None,
            "last": rows[-1]["date"] if rows else None,
        },
        "production": {
            "closed": 257887.0, "average": 8318.9, "plan_bp": 257615.0,
            "dev_bp": 272.0, "plan_sg": 257508.0, "dev_sg": 379.0,
            "delivered": 262585.0, "power": 1265.4, "incidents": 2,
            "medical": 45,
            "declared": {"value": 257887.0, "gap": 0.0, "notable": False},
        },
        "losses": {
            "total": 49753.0,
            "parts": [("Текущий простой", 31735.0), ("Бездействие", 14144.0),
                      ("Внутрисменные потери", 3874.0)],
            "groups": {"qo": 4781.0, "count": 67},
        },
        "fields": [{"field__name": f"Месторождение {index}",
                    "qo": 20000.0 - index * 900} for index in range(16)],
        "reasons": [{"reason__name": f"Причина простоя {index}",
                     "qo": 9000.0 - index * 700, "days": 31}
                    for index in range(11)],
        "wells": [{"well__number": 44100 + index,
                   "well__field__name": "Северо-Ошкотынское",
                   "qo": 2000.0 - index * 90, "days": 31}
                  for index in range(15)],
        "gas": [{"label": "Добыча газа", "plan": 12135.0, "fact": 12467.7},
                {"label": "Утилизация (с/н + потери)", "plan": 11590.2,
                 "fact": 11908.3},
                {"label": "Факел", "plan": 544.8, "fact": 559.4}],
        "injection": {"fact": 705757.0, "plan": 700000.0},
        "series": rows,
    }


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    """Лист за полный месяц."""
    output = tmp_path_factory.mktemp("period") / "аналитика.pptx"
    period_sheet.build(_data(), str(output))
    return output


# --- вёрстка -----------------------------------------------------------------
def test_sheet_is_a3_landscape(built: Path) -> None:
    """Лист имеет размер А3 в альбомной ориентации."""
    prs = Presentation(str(built))

    assert abs(prs.slide_width - Cm(period_sheet.A3_W_CM)) < Cm(TOLERANCE)
    assert abs(prs.slide_height - Cm(period_sheet.A3_H_CM)) < Cm(TOLERANCE)
    assert len(prs.slides) == 1, "лист должен быть один"


def test_nothing_runs_off_the_sheet(built: Path) -> None:
    """Ни один элемент не выходит за край листа."""
    prs = Presentation(str(built))
    width, height = prs.slide_width, prs.slide_height

    for shape in prs.slides[0].shapes:
        assert shape.left >= -Cm(TOLERANCE), f"«{shape.name}» слева"
        assert shape.top >= -Cm(TOLERANCE), f"«{shape.name}» сверху"
        assert shape.left + shape.width <= width + Cm(TOLERANCE), (
            f"элемент выходит за правый край: {shape.name}")
        assert shape.top + shape.height <= height + Cm(TOLERANCE), (
            f"элемент выходит за нижний край: {shape.name}")


def _apart(first, second) -> bool:
    """Не пересекаются ли два прямоугольника."""
    return (first[0] + first[2] <= second[0]
            or second[0] + second[2] <= first[0]
            or first[1] + first[3] <= second[1]
            or second[1] + second[3] <= first[1])


def test_tables_do_not_overlap_each_other(built: Path) -> None:
    """Таблицы не накладываются друг на друга.

    Высота таблицы рассчитывается по числу строк. Если содержимое
    ячейки в строку не помещается, PowerPoint её растит, и расчёт
    перестаёт сходиться — блок ниже оказывается накрыт.
    """
    prs = Presentation(str(built))
    boxes = [(shape.left, shape.top, shape.width, shape.height)
             for shape in prs.slides[0].shapes if shape.has_table]

    assert len(boxes) >= 6, "таблицы листа не опознаны"
    for index, first in enumerate(boxes):
        for second in boxes[index + 1:]:
            assert _apart(first, second), (
                f"таблицы перекрываются: {first} и {second}")


def test_tables_do_not_cover_block_titles(built: Path) -> None:
    """Таблица не накрывает заголовок блока.

    Соседство таблицы снизу и заголовка следующего блока — самое узкое
    место раскладки: проверка только по таблицам его не ловит, потому
    что заголовок таблицей не является.
    """
    prs = Presentation(str(built))
    tables = [(s.left, s.top, s.width, s.height)
              for s in prs.slides[0].shapes if s.has_table]
    titles = [(s.left, s.top, s.width, s.height, s.text_frame.text)
              for s in prs.slides[0].shapes
              if s.has_text_frame and s.text_frame.text in BLOCK_TITLES]

    assert len(titles) >= 6, "заголовки блоков не опознаны"
    for title in titles:
        for table in tables:
            assert _apart(title[:4], table), (
                f"таблица накрывает заголовок «{title[4]}»")


def test_chart_does_not_cover_the_neighbouring_block(built: Path) -> None:
    """Диаграмма не наезжает на соседние блоки.

    Диаграмма занимает три колонки из четырёх, а рядом с ней стоят
    итоги периода. Высота диаграммы задана числом, а не считается,
    поэтому её соседство проверяется отдельно.
    """
    prs = Presentation(str(built))
    charts = [(s.left, s.top, s.width, s.height)
              for s in prs.slides[0].shapes if s.has_chart]
    others = [(s.left, s.top, s.width, s.height)
              for s in prs.slides[0].shapes if s.has_table]

    assert charts, "диаграммы на листе нет"
    for chart in charts:
        for other in others:
            assert _apart(chart, other), "диаграмма накрывает таблицу"


def test_completeness_stands_above_the_figures(built: Path) -> None:
    """Оговорка о полноте данных стоит выше показателей.

    Лист уходит файлом, и сумма за неполный период без этой оговорки
    назавтра становится в чужой презентации «итогом месяца».
    """
    prs = Presentation(str(built))
    shapes = [s for s in prs.slides[0].shapes if s.has_text_frame]
    band = [s for s in shapes if "Данные за период полные" in s.text_frame.text]
    figures = [s for s in shapes
               if s.text_frame.text.startswith("ДОБЫЧА НЕФТИ ЗА ПЕРИОД")]

    assert band and figures, "полоса полноты или плитки не найдены"
    assert band[0].top < figures[0].top, (
        "оговорка о полноте оказалась ниже цифр")


def test_service_sections_are_absent(built: Path) -> None:
    """Служебных разделов на листе нет.

    Требование заказчика: одиннадцатый слайд доклада служебный
    и на листы А3 не выносится.
    """
    prs = Presentation(str(built))
    text = "\n".join(shape.text_frame.text for shape in prs.slides[0].shapes
                     if shape.has_text_frame)

    for title in ("Замечания к исходным данным",
                  "Величины, посчитанные программой"):
        assert title not in text, f"на листе служебный раздел «{title}»"


# --- ряд добычи --------------------------------------------------------------
def test_missing_days_stay_a_gap() -> None:
    """Пропущенные сутки остаются разрывом, а не смыкаются.

    Если строить ряд по имеющимся суткам, двадцать семь суток месяца
    выстроятся подряд и месяц будет выглядеть полным.
    """
    row = period_sheet._series(_data(skip={4, 5}))

    assert row["daily"] is True
    assert len(row["labels"]) == 31, "ряд построен не по календарю"
    assert row["fact"][4] is None and row["fact"][5] is None
    assert row["fact"][3] is not None and row["fact"][6] is not None


def test_long_period_is_rolled_up_by_month() -> None:
    """Период длиннее месяца сворачивается по месяцам.

    Триста шестьдесят пять подписей на листе сливаются в полосу.
    """
    data = _data(start=date(2026, 1, 1), end=date(2026, 12, 31),
                 days=0, title="2026 год")
    data["series"] = [{"date": date(2026, 8, day), "closed": 8300.0,
                       "plan": 8310.0} for day in range(1, 32)]
    data["completeness"]["first"] = date(2026, 8, 1)
    data["completeness"]["last"] = date(2026, 8, 31)

    row = period_sheet._series(data)

    assert row["daily"] is False
    assert row["labels"] == ["Янв 26", "Фев 26", "Мар 26", "Апр 26",
                             "Май 26", "Июн 26", "Июл 26", "Авг 26"]
    assert row["fact"][:7] == [None] * 7, (
        "месяцы без данных показаны нулями вместо пропуска")
    assert row["fact"][7] == pytest.approx(8300.0 * 31)


def test_unfinished_period_is_not_drawn_to_its_end() -> None:
    """Хвост незавершённого периода не рисуется.

    Пустая половина года справа от последних суток ничего не сообщает,
    а место занимает.
    """
    data = _data(start=date(2026, 8, 1), end=date(2026, 8, 31), days=10)
    data["completeness"]["last"] = date(2026, 8, 10)

    row = period_sheet._series(data)

    assert len(row["labels"]) == 10
    assert row["labels"][-1] == "10.08"


def test_empty_period_is_stated_plainly(tmp_path) -> None:
    """Период без данных даёт лист с надписью, а не падение."""
    data = _data(days=0)
    data["completeness"].update({"first": None, "last": None})

    output = tmp_path / "пусто.pptx"
    period_sheet.build(data, str(output))

    text = "\n".join(shape.text_frame.text
                     for shape in Presentation(str(output)).slides[0].shapes
                     if shape.has_text_frame)
    assert "За период нет данных." in text
