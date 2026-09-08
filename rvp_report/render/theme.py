# -*- coding: utf-8 -*-
"""Оформление презентации.

Палитра взята из корпоративного брендбука (`Brand book`, раздел «Фирменная
цветовая палитра»). Основные цвета — тёмно-синий ZN_01 и зелёный ZN_06,
вспомогательные ZN_02…ZN_09 используются для рядов диаграмм и оттенков.
Правится только этот файл — логика слайдов остаётся прежней.
"""
from __future__ import annotations

from pathlib import Path

from pptx.dml.color import RGBColor
from pptx.util import Pt

# --- Основные цвета брендбука ------------------------------------------------
BLUE = RGBColor(0x00, 0x32, 0x6E)       # ZN_01 DarkBlue main, RAL 5003
GREEN = RGBColor(0x4B, 0xAF, 0x46)      # ZN_06 Green main, RAL 6018
WHITE = RGBColor(0xFF, 0xFF, 0xFF)      # белый
BLACK = RGBColor(0x00, 0x00, 0x00)      # чёрный
GREY = RGBColor(0x6E, 0x6E, 0x6E)       # ZN_10, RAL 7022

# --- Вспомогательная палитра брендбука ---------------------------------------
BLUE_DEEP = RGBColor(0x00, 0x19, 0x46)    # ZN_02
BLUE_MID = RGBColor(0x00, 0x55, 0x91)     # ZN_03
BLUE_LIGHT = RGBColor(0x00, 0x78, 0xAF)   # ZN_04
GREEN_DARK = RGBColor(0x0A, 0x8F, 0x2D)   # ZN_05
GREEN_LIGHT = RGBColor(0x9B, 0xC8, 0x55)  # ZN_07
LIME = RGBColor(0xD2, 0xDC, 0x78)         # ZN_08
LIME_PALE = RGBColor(0xEB, 0xF0, 0xD7)    # ZN_09

#: Янтарный из знака «Русвьетпетро». В брендбуке нет цвета предупреждения,
#: а зелёным и синим отклонение не покажешь; взят цвет капли, который и так
#: присутствует на каждом слайде в логотипе.
AMBER = RGBColor(0xFA, 0xB2, 0x0B)

# --- Нейтральные оттенки -----------------------------------------------------
# Брендбук задаёт двенадцать цветов; фон, рамки и заливки выведены из них:
# нейтрали построены на сером ZN_10 и синем ZN_01, чтобы не появлялось
# посторонних тёплых оттенков.
INK = BLACK                             # основной текст
MUTED = GREY                            # подписи, второстепенное
LINE = RGBColor(0xD5, 0xDA, 0xE1)       # разделители, рамки
CANVAS = WHITE                          # фон слайда
PANEL = RGBColor(0xF1, 0xF4, 0xF8)      # фон плиток и чётных строк таблиц

BRAND = BLUE                            # заголовки слайдов, шапки таблиц
BRAND_LIGHT = BLUE_LIGHT                # второстепенные столбцы, акценты плиток
ACCENT = GREEN
ACCENT_SOFT = LIME_PALE                 # светлая заливка под акцент

GOOD = GREEN_DARK                       # план выполнен; ZN_05 читаем на белом
WARN = AMBER                            # внимание: заливки и акцентные полосы
WARN_TEXT = RGBColor(0xB8, 0x82, 0x0A)  # тот же янтарный, читаемый на белом
BAD = RGBColor(0xC0, 0x39, 0x2B)        # отставание, превышение норматива

#: Цвета рядов диаграмм, используются циклически. Порядок — от основного
#: синего к светлому зелёному, чтобы соседние ряды отличались и в печати.
SERIES = [BLUE, BLUE_LIGHT, GREEN_DARK, GREEN, GREEN_LIGHT, GREY]

# --- Типографика -------------------------------------------------------------
FONT = "Segoe UI"           # заменить на корпоративный при получении шрифтов

SIZE_TITLE = Pt(28)         # заголовок слайда
SIZE_SUBTITLE = Pt(13)
SIZE_KPI = Pt(30)           # число в плитке
SIZE_KPI_LABEL = Pt(10)
SIZE_BODY = Pt(12)
SIZE_TABLE = Pt(10.5)
SIZE_TABLE_HEAD = Pt(9.5)
SIZE_FOOTER = Pt(8.5)

#: Длина подписи плитки, после которой она занимает две строки.
KPI_LABEL_WRAP = 32

#: Высота, на которой печатается примечание под таблицей качества нефти.
QUALITY_NOTE_TOP = 15.2

# --- Геометрия слайда 16:9 (в сантиметрах) -----------------------------------
SLIDE_W_CM = 33.87
SLIDE_H_CM = 19.05
MARGIN_CM = 1.4
CONTENT_TOP_CM = 3.3        # первая строка контента под заголовком
FOOTER_TOP_CM = 17.9

# --- Фирменный знак ----------------------------------------------------------
LOGO_SVG = (Path(__file__).resolve().parents[2] / "assets" / "rvp-logo.svg")
LOGO_HEIGHT_CM = 1.15       # высота логотипа в углу слайда

# --- Гриф --------------------------------------------------------------------
COMPANY = "ООО «СК Русвьетпетро»"
CONFIDENTIALITY = f"Коммерческая тайна. {COMPANY}"


def hex_of(color: RGBColor) -> str:
    """RGBColor → строка «#rrggbb» для matplotlib."""
    return "#" + str(color)


def status_color(deviation: float | None, invert: bool = False) -> RGBColor:
    """Цвет по знаку отклонения.

    Args:
        deviation: Отклонение от плана. None означает «нет данных».
        invert: ``True``, если рост показателя — это плохо, например
            объём газа на факеле.

    Returns:
        Зелёный при неотрицательном отклонении, красный при
        отрицательном, серый при отсутствии данных.
    """
    if deviation is None:
        return MUTED
    if invert:
        deviation = -deviation
    return GOOD if deviation >= 0 else BAD
