# -*- coding: utf-8 -*-
"""Язык описания рапорта: чем является блок, а не где он лежит.

Схема в layout.py пишется в этих терминах, resolve.py привязывает её
к конкретному файлу и выдаёт готовые номера строк и столбцов.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Find:
    """Как найти подпись на листе."""
    label: str
    mode: str = "exact"                        # exact | starts | contains
    cols: str | None = None                    # «A» или «A:C» — сузить поиск
    nth: int = 0
    alt: tuple[str, ...] = ()                  # синонимы на случай переименования

    @property
    def labels(self) -> list[str]:
        """Основная подпись и её синонимы для поиска."""
        return [self.label, *self.alt]


@dataclass(frozen=True)
class Block:
    """Раздел рапорта. Заканчивается там, где начинается следующий."""
    key: str
    title: str
    anchor: Find
    reference_row: int                         # эталон по файлам 21–25.07.2026
    ends_before: str | None = None             # явный конец: ключ другого блока


@dataclass(frozen=True)
class Col:
    """Столбец таблицы, найденный по тексту шапки."""
    label: str = ""                            # пустой — столбец без заголовка
    parent: str = ""                           # заголовок верхнего яруса, сужает поиск
    mode: str = "starts"
    nth: int = 0
    alt: tuple[str, ...] = ()
    dc: int = 0                                # сдвиг от найденного заголовка
    # first | last — какой столбец брать, если шапка объединена
    pick: str = "first"
    # столбец без шапки: определяется по данным как левый текстовый
    anchor_col: bool = False
    optional: bool = False                     # в этой таблице столбца может не быть
    reference: str = ""                        # буква столбца по эталону

    @property
    def labels(self) -> list[str]:
        """Основная подпись столбца и её синонимы."""
        return [self.label, *self.alt]


@dataclass(frozen=True)
class Table:
    """Таблица внутри блока: шапка сверху, строки данных, иногда строка ИТОГО."""
    block: str
    columns: dict[str, Col]
    key_column: str                            # по нему строка считается заполненной
    require: tuple[str, ...] = ()              # без этих столбцов строка — подытог
    require_text: tuple[str, ...] = ()         # значение должно быть текстом, не числом
    require_number: tuple[str, ...] = ()       # значение должно быть числом
    total: Find | None = None                  # строка ИТОГО внутри блока
    cols: str | None = None                    # окно столбцов, если в блоке две таблицы
    header_depth: int = 4                      # сколько строк под якорем считать шапкой
    reference_rows: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class Scalar:
    """Одиночный показатель, привязанный к собственной подписи.

    Либо фиксированное смещение (dr/dc), либо поиск ближайшего числа:
    search="right" — правее подписи, search="down" — ниже неё. Поиск
    надёжнее там, где между подписью и значением бывают пустые строки.
    """
    find: Find
    dr: int = 0
    dc: int = 0
    search: str = ""                           # "" | right | down
    within: int = 6                            # сколько ячеек просматривать
    block: str = ""                            # искать только внутри этого блока
    reference: str = ""


@dataclass(frozen=True)
class Cross:
    """Показатель на пересечении подписи строки и заголовка столбца."""
    row: Find
    col: Find
    block: str = ""
    reference: str = ""


@dataclass(frozen=True)
class Fix:
    """Поправка к разметке, сделанная оператором.

    Синоним **добавляется** к подписям схемы, а не заменяет их: основной
    поиск идёт первым, поэтому поправка не может испортить то, что и так
    находилось, а старые файлы продолжают разбираться по-старому.

    Прямая привязка к адресу этим свойством не обладает и применяется
    только там, где опознать ячейку по подписи невозможно.

    Синонимов у показателя может накопиться несколько: подпись меняли
    не один раз. Все они пробуются по очереди, поэтому рапорт за любой
    прошлый месяц продолжает разбираться правильно.
    """
    row_aliases: tuple[str, ...] = ()   # ещё названия строки или подписи
    col_aliases: tuple[str, ...] = ()   # ещё названия заголовка столбца
    address: str = ""                   # прямая привязка, например «D564»


@dataclass(frozen=True)
class Gap:
    """Показатель, который не удалось найти по подписи.

    В отличие от сообщения для человека, несёт ключ показателя и то,
    что именно искали: этого достаточно, чтобы предложить оператору
    указать нужную ячейку.
    """
    key: str                 # ключ показателя в схеме, напр. «forecast_total»
    label: str               # подпись, которую искали
    part: str = "row"        # что не нашлось: row | col
    message: str = ""        # пояснение для человека
    reference: str = ""      # эталонный адрес, взятый взамен
    block: str = ""          # раздел рапорта, в котором шёл поиск


@dataclass
class Resolved:
    """Схема, привязанная к конкретному файлу."""
    blocks: dict[str, tuple[int, int]] = field(default_factory=dict)
    cells: dict[str, tuple[int, int] | None] = field(default_factory=dict)
    columns: dict[str, dict[str, int]] = field(default_factory=dict)
    rows: dict[str, tuple[int, int]] = field(default_factory=dict)
    totals: dict[str, int | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)      # что найдено не по схеме
    degraded: list[str] = field(default_factory=list)   # что взято из эталона
    gaps: list[Gap] = field(default_factory=list)       # то же, но разобранное
    applied: list[str] = field(default_factory=list)    # сработавшие поправки

    def cell(self, key: str) -> tuple[int, int] | None:
        """Координаты показателя или None, если он не найден."""
        return self.cells.get(key)

    def col(self, table: str, name: str) -> int | None:
        """Номер столбца таблицы или None, если столбец не найден."""
        return self.columns.get(table, {}).get(name)
