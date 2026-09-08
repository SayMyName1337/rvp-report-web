# -*- coding: utf-8 -*-
"""Отрисовка логотипа из SVG в растр без сторонних библиотек.

Ни Tkinter, ни python-pptx не умеют показывать SVG, а конвертер вроде
cairosvg — это ещё одна зависимость с бинарными компонентами в аудите
информационной безопасности. Фирменный знак состоит только из отрезков
и кубических кривых, поэтому разбирается здесь и рисуется средствами
matplotlib, который в проекте уже используется для диаграмм.

Поддерживаются команды M, L, H, V, C, Z в обоих регистрах. Дуги (A)
не поддерживаются: в логотипе их нет.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path as FilePath

import matplotlib

matplotlib.use("Agg")   # без графической подсистемы: только файлы

import matplotlib.pyplot as plt              # noqa: E402
from matplotlib.patches import PathPatch     # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402

SVG_NS = "{http://www.w3.org/2000/svg}"
_TOKENS = re.compile(r"[MmLlHhVvCcZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")

#: Цвета из логотипа, которые перекрашиваются на тёмной подложке.
BRAND_GRAPHITE = "#393536"
BRAND_GREY = "#4F4C4D"


class UnsupportedPathCommand(ValueError):
    """В контуре встретилась команда, которую разборщик не поддерживает."""


def _tokenize(data: str) -> list[str]:
    """Разбить атрибут ``d`` на команды и числа."""
    return _TOKENS.findall(data)


def _parse_path(data: str) -> MplPath:
    """Атрибут ``d`` контура SVG → путь matplotlib.

    Составные контуры (буквы с внутренними просветами) собираются
    в один путь: каждый подконтур начинается с MOVETO и закрывается
    CLOSEPOLY, за счёт чего просветы отрисовываются корректно.
    """
    vertices: list[tuple[float, float]] = []
    codes: list[int] = []
    tokens = _tokenize(data)

    index = 0
    command = ""
    current = (0.0, 0.0)
    start = (0.0, 0.0)

    def take(count: int) -> list[float]:
        """Взять очередные count чисел из потока."""
        nonlocal index
        values = [float(t) for t in tokens[index:index + count]]
        index += count
        return values

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            command = token
            index += 1
            if command in "Zz":
                vertices.append(start)
                codes.append(MplPath.CLOSEPOLY)
                current = start
                continue
        relative = command.islower()
        upper = command.upper()

        if upper == "M":
            x, y = take(2)
            if relative:
                x, y = current[0] + x, current[1] + y
            current = start = (x, y)
            vertices.append(current)
            codes.append(MplPath.MOVETO)
            # последующие пары координат после M трактуются как L
            command = "l" if relative else "L"
        elif upper == "L":
            x, y = take(2)
            if relative:
                x, y = current[0] + x, current[1] + y
            current = (x, y)
            vertices.append(current)
            codes.append(MplPath.LINETO)
        elif upper == "H":
            (x,) = take(1)
            x = current[0] + x if relative else x
            current = (x, current[1])
            vertices.append(current)
            codes.append(MplPath.LINETO)
        elif upper == "V":
            (y,) = take(1)
            y = current[1] + y if relative else y
            current = (current[0], y)
            vertices.append(current)
            codes.append(MplPath.LINETO)
        elif upper == "C":
            x1, y1, x2, y2, x, y = take(6)
            if relative:
                x1, y1 = current[0] + x1, current[1] + y1
                x2, y2 = current[0] + x2, current[1] + y2
                x, y = current[0] + x, current[1] + y
            vertices.extend([(x1, y1), (x2, y2), (x, y)])
            codes.extend([MplPath.CURVE4] * 3)
            current = (x, y)
        else:
            raise UnsupportedPathCommand(
                f"команда «{command}» в контуре логотипа не поддерживается")

    return MplPath(vertices, codes)


def _read_svg(path: str | FilePath) -> tuple[float, float, list[tuple[MplPath, str]]]:
    """Размер холста и список пар «контур — цвет заливки»."""
    root = ET.parse(str(path)).getroot()

    viewbox = root.get("viewBox")
    if viewbox:
        _, _, width, height = (float(v) for v in viewbox.replace(",", " ").split())
    else:
        width = float(root.get("width", 100))
        height = float(root.get("height", 100))

    shapes: list[tuple[MplPath, str]] = []
    for element in root.iter(f"{SVG_NS}path"):
        data = element.get("d")
        if not data:
            continue
        fill = element.get("fill", "#000000")
        if fill.lower() in ("none", "transparent"):
            continue
        shapes.append((_parse_path(data), fill))
    return width, height, shapes


#: Разбор знака на части. Границы взяты из геометрии контуров:
#: капля занимает левые 100 единиц холста, слоган — нижнюю полосу.
MARK_MAX_X = 105.0
TAGLINE_MIN_Y = 100.0

PART_FULL = "full"          # капля, название и слоган
PART_LOGO = "logo"          # капля и название, без слогана
PART_MARK = "mark"          # только капля
PART_WORDMARK = "wordmark"  # только название

#: Перекраска для тёмной подложки: графит становится белым, зелёный
#: и янтарный сохраняются — так знак остаётся узнаваемым.
ON_DARK = {
    BRAND_GRAPHITE.lower(): "#FFFFFF",
    BRAND_GREY.lower(): "#C9C6C7",
}


def _classify(shapes: list[tuple[MplPath, str]], part: str
              ) -> list[tuple[MplPath, str]]:
    """Оставить контуры, относящиеся к запрошенной части знака."""
    if part == PART_FULL:
        return shapes
    selected = []
    for path, fill in shapes:
        box = path.get_extents()
        is_mark = box.x1 <= MARK_MAX_X
        is_tagline = box.y0 >= TAGLINE_MIN_Y
        if part == PART_MARK and is_mark:
            selected.append((path, fill))
        elif part == PART_WORDMARK and not is_mark and not is_tagline:
            selected.append((path, fill))
        elif part == PART_LOGO and not is_tagline:
            selected.append((path, fill))
    return selected


def _viewport(shapes: list[tuple[MplPath, str]], pad: float,
              square: bool) -> tuple[float, float, float, float]:
    """Границы отрисовки по фактическим контурам, а не по холсту SVG.

    Так знак не обрезается и вокруг него не остаётся лишних полей,
    откуда бы ни начинались контуры выбранной части.
    """
    x0 = min(p.get_extents().x0 for p, _ in shapes)
    y0 = min(p.get_extents().y0 for p, _ in shapes)
    x1 = max(p.get_extents().x1 for p, _ in shapes)
    y1 = max(p.get_extents().y1 for p, _ in shapes)
    margin = max(x1 - x0, y1 - y0) * pad
    x0, y0, x1, y1 = x0 - margin, y0 - margin, x1 + margin, y1 + margin
    if square:
        side = max(x1 - x0, y1 - y0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        x0, x1 = cx - side / 2, cx + side / 2
        y0, y1 = cy - side / 2, cy + side / 2
    return x0, y0, x1, y1


def render(svg_path: str | FilePath, png_path: str | FilePath,
           height_px: int = 160, part: str = PART_FULL,
           recolor: dict[str, str] | None = None,
           pad: float = 0.0, square: bool = False) -> str:
    """Отрисовать знак или его часть в PNG с прозрачным фоном.

    Args:
        svg_path: Файл фирменного знака в формате SVG.
        png_path: Куда сохранить растр.
        height_px: Высота растра; ширина подбирается по пропорциям.
        part: ``full``, ``logo``, ``mark`` или ``wordmark``.
        recolor: Замена цветов заливки, например :data:`ON_DARK`.
        pad: Поля вокруг знака в долях его большей стороны.
        square: Дополнить кадр до квадрата — нужно для значка окна.

    Returns:
        Путь к созданному файлу.

    Raises:
        ValueError: Если в знаке нет запрошенной части.
        UnsupportedPathCommand: Если контур содержит дугу.
    """
    _width, _height, shapes = _read_svg(svg_path)
    shapes = _classify(shapes, part)
    if not shapes:
        raise ValueError(f"в логотипе нет части «{part}»")

    palette = {key.lower(): value for key, value in (recolor or {}).items()}
    x0, y0, x1, y1 = _viewport(shapes, pad, square)
    view_w, view_h = x1 - x0, y1 - y0

    scale = height_px / view_h
    figure = plt.figure(figsize=(view_w * scale / 100, height_px / 100),
                        dpi=100)
    axes = figure.add_axes((0, 0, 1, 1))
    axes.set_xlim(x0, x1)
    axes.set_ylim(y1, y0)             # ось Y в SVG направлена вниз
    axes.axis("off")
    figure.patch.set_alpha(0)

    for path, fill in shapes:
        color = palette.get(fill.lower(), fill)
        axes.add_patch(PathPatch(path, facecolor=color, edgecolor="none",
                                 linewidth=0))

    png_path = FilePath(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png_path, dpi=100, transparent=True)
    plt.close(figure)
    return str(png_path)


def cached(svg_path: str | FilePath, cache_dir: str | FilePath,
           height_px: int = 160, part: str = PART_FULL,
           recolor: dict[str, str] | None = None,
           pad: float = 0.0, square: bool = False) -> str:
    """То же, что :func:`render`, но с кэшированием по содержимому файла.

    Логотип нужен и окну программы, и каждой презентации, а разбор SVG
    хоть и быстрый, но повторять его на каждый запуск незачем.
    """
    svg_path = FilePath(svg_path)
    key = f"{height_px}|{part}|{sorted((recolor or {}).items())}|{pad}|{square}"
    digest = hashlib.sha1(svg_path.read_bytes() + key.encode()).hexdigest()[:12]
    png_path = FilePath(cache_dir) / f"logo-{digest}.png"
    if png_path.exists():
        return str(png_path)
    return render(svg_path, png_path, height_px, part, recolor, pad, square)
