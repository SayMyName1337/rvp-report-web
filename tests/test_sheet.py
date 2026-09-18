# -*- coding: utf-8 -*-
"""Проверки листа А3.

Лист собирается тем же разбором, что и презентация доклада, поэтому
проверяется не арифметика, а вёрстка: размер листа, полнота состава
и то, что блоки не наезжают друг на друга. Последнее особенно важно:
PowerPoint растит строку таблицы, если содержимое в неё не помещается,
и расчёт высоты блока перестаёт сходиться незаметно.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.util import Cm

from rvp_report.render import sheet

from .conftest import load, report_files

#: Допуск при сравнении размеров, сантиметры.
TOLERANCE = 0.05


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    """Лист, собранный из настоящего суточного рапорта."""
    files = report_files()
    if not files:
        pytest.skip("нет рапортов для проверки")
    output = tmp_path_factory.mktemp("sheet") / "лист.pptx"
    sheet.build(load(files[-1]), str(output))
    return output


def test_sheet_is_a3_landscape(built: Path) -> None:
    """Лист имеет размер А3 в альбомной ориентации."""
    prs = Presentation(str(built))

    assert abs(prs.slide_width - Cm(sheet.A3_W_CM)) < Cm(TOLERANCE)
    assert abs(prs.slide_height - Cm(sheet.A3_H_CM)) < Cm(TOLERANCE)
    assert len(prs.slides) == 1, "лист должен быть один"


def test_sheet_covers_every_block_of_the_deck(built: Path) -> None:
    """На листе присутствуют все разделы доклада.

    Требование заказчика: состав листа совпадает с составом
    слайдов доклада один в один, кроме одиннадцатого — служебного.
    """
    prs = Presentation(str(built))
    text = "\n".join(
        shape.text_frame.text for shape in prs.slides[0].shapes
        if shape.has_text_frame)

    for title in ("Потенциал добычи", "Добыча по месторождениям",
                  "Состояние фонда скважин", "Причины текущего простоя",
                  "Поддержание пластового давления", "Резервуарный парк",
                  "Качество товарной нефти", "Попутный нефтяной газ",
                  "Энергетика", "Бурение", "Вывод на режим",
                  "Очистные устройства", "Промышленная безопасность",
                  "Движение фонда"):
        assert title in text, f"на листе нет раздела «{title}»"

    for title in ("Замечания к исходным данным",
                  "Величины, посчитанные программой"):
        assert title not in text, (
            f"на листе оказался служебный раздел «{title}»")


def test_nothing_runs_off_the_sheet(built: Path) -> None:
    """Ни один элемент не выходит за край листа."""
    prs = Presentation(str(built))
    width, height = prs.slide_width, prs.slide_height

    for shape in prs.slides[0].shapes:
        assert shape.left >= -Cm(TOLERANCE), f"«{shape.shape_type}» слева"
        assert shape.top >= -Cm(TOLERANCE), f"«{shape.shape_type}» сверху"
        assert shape.left + shape.width <= width + Cm(TOLERANCE), (
            f"элемент выходит за правый край: {shape.name}")
        assert shape.top + shape.height <= height + Cm(TOLERANCE), (
            f"элемент выходит за нижний край: {shape.name}")


#: Заголовки блоков листа. По ним опознаются подписи среди прочих
#: надписей, чтобы проверить, что таблица их не накрывает.
BLOCK_TITLES = (
    "Потенциал добычи", "Добыча по месторождениям",
    "Состояние фонда скважин", "Причины текущего простоя",
    "Движение фонда", "Поддержание пластового давления",
    "Резервуарный парк", "Качество товарной нефти",
    "Попутный нефтяной газ", "Энергетика", "Бурение", "Вывод на режим",
    "Очистные устройства", "Промышленная безопасность",
)


def _apart(first, second) -> bool:
    """Не пересекаются ли два прямоугольника."""
    return (first[0] + first[2] <= second[0]
            or second[0] + second[2] <= first[0]
            or first[1] + first[3] <= second[1]
            or second[1] + second[3] <= first[1])


def test_tables_do_not_overlap_each_other(built: Path) -> None:
    """Таблицы не накладываются друг на друга.

    Высота таблицы рассчитывается по числу строк. Если содержимое
    ячейки не помещается в строку, PowerPoint её растит, и расчёт
    перестаёт сходиться — блок ниже оказывается накрыт.
    """
    prs = Presentation(str(built))
    boxes = [(shape.left, shape.top, shape.width, shape.height)
             for shape in prs.slides[0].shapes if shape.has_table]

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

    assert len(titles) >= 10, "заголовки блоков не опознаны"
    for title in titles:
        for table in tables:
            assert _apart(title[:4], table), (
                f"таблица накрывает заголовок «{title[4]}»")


# --- перенос строк -----------------------------------------------------------
#: Столбцы, в которые попадают номера скважин и время: их укорачивать
#: нельзя, иначе строка теряет то, чем она опознаётся.
def _cells(path: Path) -> list[tuple]:
    """Ячейки всех таблиц листа вместе с шириной их столбца."""
    prs = Presentation(str(path))
    found = []
    for shape in prs.slides[0].shapes:
        if not shape.has_table:
            continue
        table = shape.table
        widths = [column.width / 360000 for column in table.columns]
        head = table.cell(0, 0).text.strip()[:20]
        for row in range(1, len(table.rows)):
            for col in range(len(table.columns)):
                found.append((head, row, col, widths[col],
                              table.cell(row, col).text.strip()))
    return found


def _sheet_for(path: Path, folder) -> Path:
    """Собрать лист по указанному рапорту."""
    output = folder / f"{path.stem}.pptx"
    sheet.build(load(path), str(output))
    return output


def test_no_data_cell_wraps(report_path: Path, tmp_path) -> None:
    """Значение в ячейке помещается в свой столбец одной строкой.

    Это главная проверка раскладки листа, и заметить нарушение иначе
    нельзя. Не влезшую строку PowerPoint переносит и растит ради неё
    строку таблицы; в самом файле у фигуры при этом остаётся заданная
    высота, поэтому сравнение рамок ничего не находит. Видно только
    при показе — 17.09.2026 так наехали друг на друга таблица бурения
    и промышленная безопасность, а вывод на режим залез в подвал.
    """
    built = _sheet_for(report_path, tmp_path)
    wrapped = [f"«{head}» строка {row} столбец {col} "
               f"({width:.2f} см): {text!r}"
               for head, row, col, width, text in _cells(built)
               if text and not sheet.fits(text, width, sheet.SIZE_TABLE)]

    assert not wrapped, "переносятся: " + "; ".join(wrapped)


def test_nothing_reaches_the_footer(report_path: Path, tmp_path) -> None:
    """Ни одна таблица не доходит до подвала листа."""
    prs = Presentation(str(_sheet_for(report_path, tmp_path)))
    late = [shape for shape in prs.slides[0].shapes
            if shape.has_table
            and (shape.top + shape.height) / 360000 > sheet.FOOTER_TOP]

    assert not late, "таблица уходит в подвал"


def test_columns_do_not_reach_the_bottom_band(report_path: Path,
                                              tmp_path) -> None:
    """Столбцы верхней части не заходят в нижнюю полосу.

    Нижняя полоса стоит на постоянном отступе, и блок, выросший
    сверху, наезжает на неё.
    """
    prs = Presentation(str(_sheet_for(report_path, tmp_path)))
    crossing = [shape for shape in prs.slides[0].shapes
                if shape.has_table
                and shape.top / 360000 < sheet.BAND
                < (shape.top + shape.height) / 360000]

    assert not crossing, "блок заходит в нижнюю полосу"


@pytest.mark.parametrize("text,width,expected", [
    ("11305", 1.35, "11305"),
    ("15.09 15:40", 2.51, "15.09 15:40"),
    ("Смена ГНО", 3.04, "Смена ГНО"),
    ("устранение \nПП 28 из 39", 5.0, "устранение ПП 28 из 39"),
])
def test_fit_keeps_what_already_fits(text: str, width: float,
                                     expected: str) -> None:
    """Номера скважин и время не укорачиваются.

    Оценка ширины по числу знаков резала их: «11305» и «Простой»
    одинаковой длины, но занимают разное место.
    """
    assert sheet.fit(text, width) == expected


def test_fit_shortens_what_does_not() -> None:
    """Длинное название укорачивается с многоточием."""
    result = sheet.fit("Западно-Хоседаюское", 2.2)

    assert result.endswith("…")
    assert sheet.fits(result, 2.2, sheet.SIZE_TABLE)


def test_fit_removes_line_breaks() -> None:
    """Перевод строки внутри значения убирается.

    Такое значение растит строку само по себе, какой бы ширины
    ни был столбец: в графе забоя встречается «устранение\nПП 28 из 39».
    """
    assert "\n" not in sheet.fit("устранение \nПП 28 из 39", 10.0)


def test_long_names_do_not_break_the_layout(report_path: Path,
                                            tmp_path) -> None:
    """Лист выдерживает названия длиннее нынешних.

    Проверка по действующим рапортам показывает лишь то, что раскладка
    сходится на сегодняшних данных. Она и сходилась — пока в графе
    забоя не появилось «устранение ПП 28 из 39» с переводом строки
    внутри. Здесь текстовые поля намеренно растягиваются: месторождения,
    подрядчики, причины, названия участков.
    """
    daily = copy.deepcopy(load(report_path))
    long_name = "Восточно-Северо-Ошкотынское нефтегазоконденсатное"

    for item in daily.stock_by_field:
        item.name = long_name
    daily.production.by_field = [(long_name, value)
                                 for _name, value in daily.production.by_field]
    for item in daily.drilling:
        item.contractor = long_name
        item.field_name = long_name
        item.current_depth_text = "устранение \nприхвата ПП 28 из 39"
    for item in daily.ramp_up:
        item.field_name = long_name
        item.gtm = "смена глубинно-насосного оборудования"
    for item in daily.pigging:
        item.section = "Куст 1 Ю.Сюрхаратинское — СОД Южно-Сюрхаратинское"
    daily.downtime_breakdown = [
        ("текущий простой по ограничению приёма нефти", wells, qo)
        for _reason, wells, qo in daily.downtime_breakdown]

    output = tmp_path / "длинные.pptx"
    sheet.build(daily, str(output))

    wrapped = [f"«{head}» строка {row} столбец {col}: {text!r}"
               for head, row, col, width, text in _cells(output)
               if text and not sheet.fits(text, width, sheet.SIZE_TABLE)]
    assert not wrapped, "переносятся: " + "; ".join(wrapped)

    prs = Presentation(str(output))
    for shape in prs.slides[0].shapes:
        if not shape.has_table:
            continue
        bottom = (shape.top + shape.height) / 360000
        assert bottom <= sheet.FOOTER_TOP, "таблица уходит в подвал"
        assert not (shape.top / 360000 < sheet.BAND < bottom), (
            "блок заходит в нижнюю полосу")
