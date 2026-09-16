# -*- coding: utf-8 -*-
"""Проверки листа А3.

Лист собирается тем же разбором, что и презентация доклада, поэтому
проверяется не арифметика, а вёрстка: размер листа, полнота состава
и то, что блоки не наезжают друг на друга. Последнее особенно важно:
PowerPoint растит строку таблицы, если содержимое в неё не помещается,
и расчёт высоты блока перестаёт сходиться незаметно.
"""
from __future__ import annotations

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
    одиннадцати слайдов один в один.
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
                  "Движение фонда", "Замечания к исходным данным",
                  "Величины, посчитанные программой"):
        assert title in text, f"на листе нет раздела «{title}»"


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


def test_blocks_do_not_overlap_tables(built: Path) -> None:
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
            apart = (first[0] + first[2] <= second[0]
                     or second[0] + second[2] <= first[0]
                     or first[1] + first[3] <= second[1]
                     or second[1] + second[3] <= first[1])
            assert apart, f"таблицы перекрываются: {first} и {second}"
