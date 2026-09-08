# -*- coding: utf-8 -*-
"""Диаграммы matplotlib → PNG для вставки в слайд.

Только то, чего нет в штатных диаграммах PowerPoint: waterfall, Парето,
горизонтальные бары с подписями значений, прогресс-бары бурения.
"""
from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")   # без графической подсистемы: только файлы

import matplotlib.pyplot as plt              # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from . import theme as T                     # noqa: E402
from .fmt import num                         # noqa: E402

DPI = 200
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": [T.FONT, "DejaVu Sans"],
    "axes.edgecolor": T.hex_of(T.LINE),
    "axes.labelcolor": T.hex_of(T.MUTED),
    "text.color": T.hex_of(T.INK),
    "xtick.color": T.hex_of(T.MUTED),
    "ytick.color": T.hex_of(T.MUTED),
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})

_THOUSANDS = FuncFormatter(lambda v, _: num(v, 0))

#: Надпись на месте диаграммы, для которой нет данных.
NO_DATA = "Нет данных за отчётные сутки"


def _finish(fig, path: str) -> str:
    """Сохранить рисунок в PNG и освободить память matplotlib."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", pad_inches=0.05,
                transparent=False)
    plt.close(fig)
    return path


def _empty(path: str, size: tuple[float, float],
           text: str = NO_DATA) -> str:
    """Заглушка вместо диаграммы: показателей за сутки не было.

    Пустой список — законная ситуация (например, за сутки не запускали
    ни одной скважины), поэтому программа не должна падать.
    """
    fig, ax = plt.subplots(figsize=size)
    ax.axis("off")
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=11,
            color=T.hex_of(T.MUTED), transform=ax.transAxes)
    return _finish(fig, path)


def _top(values, factor: float = 1.15, floor: float = 1.0) -> float:
    """Верхняя граница оси. Никогда не ноль: иначе шкала вырождается."""
    top = max(values, default=0.0) * factor
    return top if top > 0 else floor


def _strip(ax, keep_x: bool = True) -> None:
    """Убрать рамку и засечки, оставив только горизонтальную сетку."""
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_visible(keep_x)
    ax.tick_params(length=0)
    ax.grid(axis="y", color=T.hex_of(T.LINE), linewidth=0.7, alpha=0.8)
    ax.set_axisbelow(True)


def waterfall(path: str, start_label: str, start: float,
              steps: list[tuple[str, float]], end_label: str, end: float,
              size=(9.2, 4.0)) -> str:
    """От плана к факту: как сложилось отклонение."""
    fig, ax = plt.subplots(figsize=size)
    labels = [start_label] + [s[0] for s in steps] + [end_label]
    running = start
    positions = range(len(labels))

    ax.bar(0, start, color=T.hex_of(T.MUTED), width=0.62)
    ax.text(0, start, num(start), ha="center", va="bottom",
            fontsize=9, fontweight="bold")

    for i, (_, delta) in enumerate(steps, start=1):
        color = T.hex_of(T.GOOD if delta >= 0 else T.BAD)
        bottom = running if delta >= 0 else running + delta
        ax.bar(i, abs(delta), bottom=bottom, color=color, width=0.62)
        ax.text(i, bottom + abs(delta),
                ("+" if delta >= 0 else "−") + num(abs(delta), 1),
                ha="center", va="bottom", fontsize=9, fontweight="bold",
                color=color)
        running += delta

    ax.bar(len(labels) - 1, end, color=T.hex_of(T.BRAND), width=0.62)
    ax.text(len(labels) - 1, end, num(end), ha="center", va="bottom",
            fontsize=9, fontweight="bold", color=T.hex_of(T.BRAND))

    ax.set_xticks(list(positions))
    ax.set_xticklabels(labels, fontsize=9)
    ax.yaxis.set_major_formatter(_THOUSANDS)
    # шкала обрезана, поэтому оставляем воздух под «плавающими» столбцами,
    # иначе промежуточный шаг читается как столбец от нуля
    floor = min(start, end, running)
    ceiling = max(start, end, running)
    margin = (ceiling - floor) * 0.28 or max(abs(ceiling) * 0.1, 1.0)
    ax.set_ylim(floor - margin, ceiling + margin * 0.2)
    _strip(ax)
    return _finish(fig, path)


def hbar(path: str, items: list[tuple[str, float]], unit: str = "т",
         color=None, size=(9.0, 6.4), highlight_top: int = 3) -> str:
    """Горизонтальные бары, отсортированы по убыванию, значения подписаны."""
    if not items:
        return _empty(path, size)
    items = sorted(items, key=lambda x: x[1], reverse=True)
    names = [i[0] for i in items][::-1]
    values = [i[1] for i in items][::-1]
    base = T.hex_of(color or T.BRAND_LIGHT)
    colors = [base] * len(values)
    for i in range(1, min(highlight_top, len(values)) + 1):
        colors[-i] = T.hex_of(T.BRAND)

    fig, ax = plt.subplots(figsize=size)
    bars = ax.barh(names, values, color=colors, height=0.68)
    span = _top(values, 1.0)
    for bar, value in zip(bars, values):
        ax.text(bar.get_width() + span * 0.012,
                bar.get_y() + bar.get_height() / 2,
                f"{num(value, 0)} {unit}", va="center", fontsize=9,
                fontweight="bold")
    ax.set_xlim(0, span * 1.16)
    ax.set_xticks([])
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0, labelsize=9.5)
    return _finish(fig, path)


def pareto(path: str, items: list[tuple[str, float]], unit: str = "т",
           size=(9.2, 4.6)) -> str:
    """Столбцы по убыванию + накопленная доля."""
    items = [i for i in sorted(items, key=lambda x: x[1], reverse=True)
             if i[1] > 0]
    if not items:
        return _empty(path, size)
    names = [i[0] for i in items]
    values = [i[1] for i in items]
    total = sum(values) or 1.0

    fig, ax = plt.subplots(figsize=size)
    bars = ax.bar(names, values, color=T.hex_of(T.BRAND), width=0.6)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value,
                f"{num(value, 0)}", ha="center", va="bottom",
                fontsize=9.5, fontweight="bold")
    ax.set_ylabel(unit, fontsize=9)
    ax.yaxis.set_major_formatter(_THOUSANDS)
    ax.set_ylim(0, _top(values, 1.22))
    _strip(ax)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([n.replace(" ", "\n", 1) for n in names], fontsize=9)

    cumulative, share = [], 0.0
    for value in values:
        share += value / total * 100
        cumulative.append(share)
    ax2 = ax.twinx()
    ax2.plot(names, cumulative, color=T.hex_of(T.WARN), marker="o",
             markersize=5, linewidth=2)
    for x, y in zip(names, cumulative):
        ax2.annotate(f"{y:.0f} %", (x, y), textcoords="offset points",
                     xytext=(0, 9), ha="center", fontsize=8.5,
                     color=T.hex_of(T.WARN), fontweight="bold")
    ax2.set_ylim(0, 118)
    ax2.set_yticks([])
    for side in ("top", "right", "left"):
        ax2.spines[side].set_visible(False)
    return _finish(fig, path)


def plan_fact(path: str, items: list[tuple[str, float, float]],
              unit: str = "м³", size=(9.0, 3.4)) -> str:
    """Парные столбцы «режим / факт»."""
    if not items:
        return _empty(path, size)
    names = [i[0] for i in items]
    plan = [i[1] or 0 for i in items]
    fact = [i[2] or 0 for i in items]
    positions = range(len(names))
    width = 0.36

    fig, ax = plt.subplots(figsize=size)
    ax.bar([p - width / 2 for p in positions], plan, width,
           label="Режим", color=T.hex_of(T.MUTED))
    ax.bar([p + width / 2 for p in positions], fact, width,
           label="Факт", color=T.hex_of(T.BRAND))
    for p, (pl, fc) in enumerate(zip(plan, fact)):
        ax.text(p - width / 2, pl, num(pl), ha="center", va="bottom", fontsize=8.5)
        ax.text(p + width / 2, fc, num(fc), ha="center", va="bottom",
                fontsize=8.5, fontweight="bold", color=T.hex_of(T.BRAND))
    ax.set_xticks(list(positions))
    ax.set_xticklabels(names, fontsize=9)
    ax.set_ylabel(unit, fontsize=9)
    ax.yaxis.set_major_formatter(_THOUSANDS)
    ax.set_ylim(0, _top(plan + fact, 1.2))
    ax.legend(frameon=False, fontsize=9, loc="upper left", ncols=2)
    _strip(ax)
    return _finish(fig, path)


def stock_funnel(path: str, stages: list[tuple[str, float]],
                 size=(9.0, 3.2)) -> str:
    """Фонд скважин: общий → эксплуатационный → в работе."""
    if not stages:
        return _empty(path, size)
    names = [s[0] for s in stages]
    values = [s[1] for s in stages]
    fig, ax = plt.subplots(figsize=size)
    colors = [T.hex_of(c) for c in T.SERIES[: len(values)]]
    bars = ax.barh(range(len(values))[::-1], values, color=colors, height=0.62)
    for bar, value, name in zip(bars, values, names):
        ax.text(bar.get_width() * 0.02, bar.get_y() + bar.get_height() / 2,
                f"  {name}", va="center", fontsize=10.5, color="white",
                fontweight="bold")
        ax.text(bar.get_width() + _top(values, 0.012),
                bar.get_y() + bar.get_height() / 2, num(value),
                va="center", fontsize=11, fontweight="bold")
    ax.set_xlim(0, _top(values, 1.12))
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)
    return _finish(fig, path)


def drilling_progress(path: str, items: list[tuple[str, float, float]],
                      size=(9.0, 3.6)) -> str:
    """Забой относительно проектной глубины."""
    if not items:
        return _empty(path, size)
    names = [i[0] for i in items][::-1]
    target = [i[1] for i in items][::-1]
    current = [i[2] for i in items][::-1]
    fig, ax = plt.subplots(figsize=size)
    ax.barh(names, target, color=T.hex_of(T.LINE), height=0.6)
    bars = ax.barh(names, current, color=T.hex_of(T.BRAND), height=0.6)
    for bar, cur, tgt in zip(bars, current, target):
        share = cur / tgt * 100 if tgt else 0
        ax.text(max(tgt, 1.0) * 1.01, bar.get_y() + bar.get_height() / 2,
                f"{num(cur)} / {num(tgt)} м  ·  {share:.0f} %",
                va="center", fontsize=9)
    ax.set_xlim(0, _top(target, 1.32))
    ax.set_xticks([])
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0, labelsize=9.5)
    return _finish(fig, path)
