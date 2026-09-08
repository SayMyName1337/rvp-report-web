# -*- coding: utf-8 -*-
"""Низкоуровневые примитивы вёрстки слайда поверх python-pptx.

Здесь нет ничего про суточный рапорт — только «плитка», «таблица», «заголовок».
"""
from __future__ import annotations

import struct

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Cm, Pt

from . import logo as logo_render, theme as T

#: Запасные пропорции знака на случай, если растр прочитать не удалось.
LOGO_ASPECT = 470 / 135

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(path: str) -> tuple[int, int] | None:
    """Размер PNG в пикселях из заголовка файла.

    Определять пропорции нужно, чтобы вписывать снимки экрана в макет;
    ради одной этой задачи подключать библиотеку обработки изображений
    не хочется.
    """
    try:
        with open(path, "rb") as stream:
            header = stream.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != _PNG_SIGNATURE:
        return None
    width, height = struct.unpack(">II", header[16:24])
    return width, height


class Deck:
    """Презентация и примитивы вёрстки поверх python-pptx.

    Args:
        template: Корпоративный шаблон .pptx/.potx. Без него берётся
            пустая презентация с размерами из :mod:`theme`.
        assets_dir: Каталог для кэша растрового логотипа. Если не задан,
            логотип на слайды не выводится.
    """

    def __init__(self, template: str | None = None,
                 assets_dir: str | None = None):
        """Args:
        template: Корпоративный шаблон .pptx/.potx.
        assets_dir: Каталог для кэша растрового логотипа.
        """
        self.prs = Presentation(template) if template else Presentation()
        if template is None:
            self.prs.slide_width = Cm(T.SLIDE_W_CM)
            self.prs.slide_height = Cm(T.SLIDE_H_CM)
        self._blank = self.prs.slide_layouts[6]  # пустой макет
        self._assets = assets_dir
        self._logo_cache: dict[bool, str | None] = {}

    # --- фирменный знак ------------------------------------------------------
    def logo_png(self, on_dark: bool = False) -> str | None:
        """Путь к растру знака или None, если знак недоступен.

        На слайды выносится капля с названием, без строки «совместная
        компания»: в мелком масштабе она нечитаема. Для тёмной подложки
        графитовые элементы перекрашиваются в белый.
        """
        if on_dark in self._logo_cache:
            return self._logo_cache[on_dark]
        result: str | None = None
        if self._assets and T.LOGO_SVG.exists():
            try:
                result = logo_render.cached(
                    T.LOGO_SVG, self._assets, height_px=400,
                    part=logo_render.PART_LOGO,
                    recolor=logo_render.ON_DARK if on_dark else None)
            except Exception:                                  # noqa: BLE001
                result = None      # без логотипа презентация всё равно нужна
        self._logo_cache[on_dark] = result
        return result

    def logo_aspect(self, on_dark: bool = False) -> float:
        """Отношение ширины знака к высоте для расчёта места на слайде."""
        path = self.logo_png(on_dark)
        size = png_size(path) if path else None
        return (size[0] / size[1]) if size else LOGO_ASPECT

    def place_logo(self, slide, x: float, y: float, height: float,
                   on_dark: bool = False):
        """Разместить знак заданной высоты, ширина — по пропорциям файла."""
        path = self.logo_png(on_dark)
        if path is None:
            return None
        width = height * self.logo_aspect(on_dark)
        return slide.shapes.add_picture(path, Cm(x), Cm(y),
                                        Cm(width), Cm(height))

    def place_logo_right(self, slide, y: float, height: float,
                         on_dark: bool = False):
        """Прижать знак к правому полю слайда."""
        width = height * self.logo_aspect(on_dark)
        return self.place_logo(slide, T.SLIDE_W_CM - T.MARGIN_CM - width,
                               y, height, on_dark)

    # --- слайд ---------------------------------------------------------------
    def slide(self, title: str = "", subtitle: str = ""):
        """Добавить слайд с заголовком, подзаголовком и знаком.

        Args:
            title: Заголовок слайда. Пустой — слайд без шапки.
            subtitle: Пояснение под заголовком.

        Returns:
            Созданный слайд.
        """
        s = self.prs.slides.add_slide(self._blank)
        if title:
            self._title(s, title, subtitle)
            self.place_logo_right(s, 1.05, T.LOGO_HEIGHT_CM)
        self._footer(s)
        return s

    def section_title(self, slide, y: float, title: str,
                      subtitle: str = "") -> float:
        """Заголовок раздела в произвольном месте слайда.

        Нужен там, где над разделом стоит титульная плашка и заголовок
        не может занимать своё обычное место наверху.

        Args:
            slide: Слайд размещения.
            y: Отступ сверху, см.
            title: Заголовок раздела.
            subtitle: Пояснение под заголовком.

        Returns:
            Нижнюю границу заголовка вместе с отбивкой, см.
        """
        width = T.SLIDE_W_CM - 2 * T.MARGIN_CM
        self.write(self.textbox(slide, T.MARGIN_CM, y, width - 5.5, 1.5),
                   title, size=T.SIZE_TITLE, bold=True, color=T.BRAND)
        if subtitle:
            self.write(self.textbox(slide, T.MARGIN_CM, y + 1.3, width, 0.8),
                       subtitle, size=T.SIZE_SUBTITLE, color=T.MUTED)
        bottom = y + 2.1
        self.line(slide, T.MARGIN_CM, bottom, width)
        return bottom

    def _title(self, slide, title: str, subtitle: str) -> None:
        """Нарисовать заголовок, подзаголовок и отбивку."""
        box = self.textbox(slide, T.MARGIN_CM, 0.95,
                           T.SLIDE_W_CM - 2 * T.MARGIN_CM - 5.5, 1.5)
        self.write(box, title, size=T.SIZE_TITLE, bold=True, color=T.BRAND)
        if subtitle:
            sub = self.textbox(slide, T.MARGIN_CM, 2.25,
                               T.SLIDE_W_CM - 2 * T.MARGIN_CM, 0.8)
            self.write(sub, subtitle, size=T.SIZE_SUBTITLE, color=T.MUTED)
        self.line(slide, T.MARGIN_CM, 3.05, T.SLIDE_W_CM - 2 * T.MARGIN_CM)

    def _footer(self, slide) -> None:
        """Проставить гриф в нижнем колонтитуле."""
        box = self.textbox(slide, T.MARGIN_CM, T.FOOTER_TOP_CM,
                           T.SLIDE_W_CM - 2 * T.MARGIN_CM, 0.6)
        self.write(box, T.CONFIDENTIALITY, size=T.SIZE_FOOTER, color=T.LINE)

    # --- примитивы -----------------------------------------------------------
    def textbox(self, slide, x: float, y: float, w: float, h: float):
        """Добавить текстовое поле без внутренних полей и с переносом слов."""
        box = slide.shapes.add_textbox(Cm(x), Cm(y), Cm(w), Cm(h))
        frame = box.text_frame
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = 0
        frame.margin_top = frame.margin_bottom = 0
        return box

    def write(self, box, text: str, size=T.SIZE_BODY, bold: bool = False,
              color: RGBColor = T.INK, align=PP_ALIGN.LEFT,
              font: str = T.FONT, line_spacing: float | None = None):
        """Заполнить текстовое поле, разбив текст на абзацы по переводам строк.

        Args:
            box: Текстовое поле.
            text: Текст; каждая строка становится абзацем.
            size: Размер шрифта.
            bold: Полужирное начертание.
            color: Цвет текста.
            align: Выравнивание абзаца.
            font: Гарнитура.
            line_spacing: Межстрочный интервал.

        Returns:
            То же текстовое поле — для сцепления вызовов.
        """
        frame = box.text_frame
        for i, chunk in enumerate(str(text).split("\n")):
            para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
            para.alignment = align
            if line_spacing:
                para.line_spacing = line_spacing
            run = para.add_run()
            run.text = chunk
            run.font.size = size
            run.font.bold = bold
            run.font.name = font
            run.font.color.rgb = color
        return box

    def rect(self, slide, x: float, y: float, w: float, h: float,
             fill: RGBColor | None = T.PANEL, border: RGBColor | None = None,
             rounded: bool = False):
        """Добавить прямоугольник заливки или подложку.

        Args:
            x: Отступ слева, см.
            y: Отступ сверху, см.
            w: Ширина, см.
            h: Высота, см.
            fill: Цвет заливки; None — без заливки.
            border: Цвет рамки; None — без рамки.
            rounded: Скруглить углы.

        Returns:
            Созданную фигуру.
        """
        shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
        shape = slide.shapes.add_shape(shape_type, Cm(x), Cm(y), Cm(w), Cm(h))
        if rounded:
            shape.adjustments[0] = 0.06
        if fill is None:
            shape.fill.background()
        else:
            shape.fill.solid()
            shape.fill.fore_color.rgb = fill
        if border is None:
            shape.line.fill.background()
        else:
            shape.line.color.rgb = border
            shape.line.width = Pt(0.75)
        shape.shadow.inherit = False
        shape.text_frame.text = ""
        return shape

    def line(self, slide, x: float, y: float, w: float,
             color: RGBColor = T.LINE, weight: float = 1.0):
        """Провести горизонтальную линию-отбивку."""
        shape = self.rect(slide, x, y, w, 0.045, fill=color)
        shape.line.fill.background()
        return shape

    # --- составные элементы --------------------------------------------------
    def kpi(self, slide, x: float, y: float, w: float, h: float,
            label: str, value: str, note: str = "",
            value_color: RGBColor = T.INK, accent: RGBColor | None = None,
            note_color: RGBColor = T.MUTED, mark: str = ""):
        """Плитка «подпись — большое число — комментарий».

        Значение остаётся нейтральным, статус несут цветная полоса слева
        и цвет подписи — иначе каждый второй крупный показатель красный.

        Args:
            label: Подпись показателя.
            value: Значение крупным шрифтом.
            note: Пояснение под значением.
            value_color: Цвет значения.
            accent: Цвет полосы слева; None — полосы нет.
            note_color: Цвет пояснения.
            mark: Пометка в углу плитки. Отличает расчётные величины
                от значений, взятых из рапорта напрямую.
        """
        self.rect(slide, x, y, w, h, fill=T.PANEL, rounded=True)
        if accent is not None:
            self.rect(slide, x, y, 0.14, h, fill=accent)
        if mark:
            self.write(self.textbox(slide, x + w - 2.2, y + 0.32, 1.8, 0.6),
                       mark, size=T.SIZE_FOOTER, color=T.MUTED,
                       align=PP_ALIGN.RIGHT)
        pad = 0.45
        # длинная подпись переносится на вторую строку, поэтому значение
        # опускается ниже — иначе они накладываются друг на друга
        label_h = 0.95 if len(label) > T.KPI_LABEL_WRAP else 0.6
        self.write(self.textbox(slide, x + pad, y + 0.35, w - 2 * pad, label_h),
                   label.upper(), size=T.SIZE_KPI_LABEL, color=T.MUTED,
                   bold=True)
        self.write(self.textbox(slide, x + pad, y + 0.35 + label_h,
                                w - 2 * pad, 1.3),
                   value, size=T.SIZE_KPI, bold=True, color=value_color)
        if note:
            self.write(self.textbox(slide, x + pad, y + h - 1.0, w - 2 * pad, 0.8),
                       note, size=T.SIZE_KPI_LABEL, color=note_color)

    def table(self, slide, x: float, y: float, w: float,
              headers: list[str], rows: list[list], widths: list[float] | None = None,
              row_h: float = 0.72, head_h: float = 0.78,
              aligns: list | None = None,
              cell_colors: dict[tuple[int, int], RGBColor] | None = None):
        """Таблица. cell_colors — {(строка, столбец): цвет текста} для светофора."""
        cols = len(headers)
        height = head_h + row_h * max(len(rows), 1)
        shape = slide.shapes.add_table(len(rows) + 1, cols, Cm(x), Cm(y),
                                       Cm(w), Cm(height))
        table = shape.table
        table.first_row = True
        table.horz_banding = True

        if widths:
            total = sum(widths)
            for i, part in enumerate(widths):
                table.columns[i].width = Cm(w * part / total)
        table.rows[0].height = Cm(head_h)
        for i in range(len(rows)):
            table.rows[i + 1].height = Cm(row_h)

        aligns = aligns or [PP_ALIGN.LEFT] + [PP_ALIGN.RIGHT] * (cols - 1)
        if len(aligns) != cols:
            raise ValueError(
                f"выравниваний {len(aligns)}, а столбцов {cols}")
        if widths and len(widths) != cols:
            raise ValueError(
                f"ширин {len(widths)}, а столбцов {cols}")

        for c, head in enumerate(headers):
            self._cell(table.cell(0, c), head, bold=True, size=T.SIZE_TABLE_HEAD,
                       color=T.CANVAS, fill=T.BRAND, align=aligns[c])
        for r, row in enumerate(rows, start=1):
            fill = T.CANVAS if r % 2 else T.PANEL
            for c, value in enumerate(row):
                color = (cell_colors or {}).get((r - 1, c), T.INK)
                self._cell(table.cell(r, c), value, size=T.SIZE_TABLE,
                           color=color, fill=fill, align=aligns[c])
        return shape

    def _cell(self, cell, text, bold=False, size=T.SIZE_TABLE,
              color=T.INK, fill=T.CANVAS, align=PP_ALIGN.LEFT):
        """Заполнить ячейку таблицы с заданным оформлением."""
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill
        cell.margin_left = cell.margin_right = Cm(0.18)
        cell.margin_top = cell.margin_bottom = Cm(0.05)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        frame = cell.text_frame
        frame.word_wrap = True
        para = frame.paragraphs[0]
        para.alignment = align
        run = para.add_run()
        run.text = "" if text is None else str(text)
        run.font.size = size
        run.font.bold = bold
        run.font.name = T.FONT
        run.font.color.rgb = color

    def column_chart(self, slide, x: float, y: float, w: float, h: float,
                     categories: list[str], values: list[float | None],
                     colors: list[RGBColor] | None = None):
        """Добавить столбчатую диаграмму средствами PowerPoint.

        В отличие от растровой картинки такая диаграмма остаётся
        редактируемой: перед докладом можно поправить подпись или цвет
        прямо в PowerPoint, не пересобирая презентацию.

        Args:
            slide: Слайд размещения.
            x: Отступ слева, см.
            y: Отступ сверху, см.
            w: Ширина, см.
            h: Высота, см.
            categories: Подписи столбцов.
            values: Значения столбцов.
            colors: Цвет каждого столбца; короткий список повторяется.

        Returns:
            Созданную диаграмму.
        """
        data = CategoryChartData()
        data.categories = categories
        data.add_series("", values)

        frame = slide.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED, Cm(x), Cm(y), Cm(w), Cm(h), data)
        chart = frame.chart
        chart.has_legend = False
        chart.has_title = False
        chart.font.size = T.SIZE_TABLE
        chart.font.name = T.FONT
        chart.font.color.rgb = T.MUTED

        plot = chart.plots[0]
        plot.gap_width = 60
        plot.has_data_labels = True
        labels = plot.data_labels
        labels.number_format = "# ##0"
        labels.number_format_is_linked = False
        labels.position = XL_LABEL_POSITION.OUTSIDE_END
        labels.font.size = T.SIZE_TABLE
        labels.font.bold = True
        labels.font.name = T.FONT
        labels.font.color.rgb = T.INK

        palette = colors or [T.BRAND]
        for index, point in enumerate(plot.series[0].points):
            point.format.fill.solid()
            point.format.fill.fore_color.rgb = palette[index % len(palette)]

        value_axis = chart.value_axis
        value_axis.has_major_gridlines = True
        value_axis.major_gridlines.format.line.color.rgb = T.LINE
        value_axis.format.line.color.rgb = T.LINE
        value_axis.tick_labels.font.size = T.SIZE_FOOTER
        value_axis.tick_labels.font.color.rgb = T.MUTED

        category_axis = chart.category_axis
        category_axis.format.line.color.rgb = T.LINE
        category_axis.tick_labels.font.size = T.SIZE_FOOTER
        category_axis.tick_labels.font.color.rgb = T.MUTED
        return chart

    def picture(self, slide, path: str, x: float, y: float,
                w: float | None = None, h: float | None = None):
        """Вставить изображение с явными размерами."""
        return slide.shapes.add_picture(
            path, Cm(x), Cm(y),
            Cm(w) if w else None, Cm(h) if h else None)

    def picture_fit(self, slide, path: str, x: float, y: float,
                    max_w: float, max_h: float, center: bool = True,
                    border: RGBColor | None = None):
        """Вписать изображение в прямоугольник, сохранив пропорции."""
        size = png_size(path)
        if size is None:
            return self.picture(slide, path, x, y, w=max_w)
        width_px, height_px = size
        scale = min(max_w / width_px, max_h / height_px)
        width, height = width_px * scale, height_px * scale
        left = x + (max_w - width) / 2 if center else x
        top = y + (max_h - height) / 2 if center else y
        if border is not None:
            self.rect(slide, left - 0.06, top - 0.06,
                      width + 0.12, height + 0.12, fill=border)
        return self.picture(slide, path, left, top, w=width, h=height)

    def note(self, slide, x: float, y: float, w: float, text: str,
             color: RGBColor = T.MUTED, size=T.SIZE_FOOTER):
        """Добавить мелкую поясняющую подпись."""
        return self.write(self.textbox(slide, x, y, w, 1.2), text,
                          size=size, color=color, line_spacing=1.15)

    def save(self, path: str) -> None:
        """Сохранить презентацию в файл."""
        self.prs.save(path)
