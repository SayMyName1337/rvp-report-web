# -*- coding: utf-8 -*-
"""Обёртка над листом Excel: поиск по подписям вместо адресов ячеек.

Рапорт свёрстан объединёнными ячейками и многоярусными шапками, поэтому
адрес ячейки — ненадёжная привязка: достаточно вставить строку, и всё съедет.
Здесь лист индексируется по тексту, а объединения разворачиваются, так что
значение можно взять по любой ячейке диапазона.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

# Слова, которые в подписях ничего не различают, но мешают сравнению
_PUNCT = re.compile(r"[«»\"'()\[\],;:.!?]+")
_SPACES = re.compile(r"[\s   ]+")


def norm(value) -> str:
    """Подпись к сравнимому виду: регистр, пробелы, переносы, ё, пунктуация."""
    if value is None:
        return ""
    text = str(value).replace("­", "")
    text = _SPACES.sub(" ", text).strip().lower().replace("ё", "е")
    text = _PUNCT.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


@dataclass(frozen=True)
class Span:
    """Прямоугольник ячейки с учётом объединения."""
    row: int
    col: int
    last_row: int
    last_col: int

    @property
    def rows(self) -> range:
        """Строки, входящие в диапазон."""
        return range(self.row, self.last_row + 1)

    @property
    def cols(self) -> range:
        """Столбцы, входящие в диапазон."""
        return range(self.col, self.last_col + 1)

    @property
    def address(self) -> str:
        """Адрес левой верхней ячейки диапазона, например «K28»."""
        return f"{get_column_letter(self.col)}{self.row}"


class Sheet:
    """Доступ к листу по подписям, с разворачиванием объединённых ячеек."""

    def __init__(self, ws: Worksheet):
        """Построить индекс листа: объединения и подписи.

        Args:
            ws: Лист книги Excel, открытой со значениями формул.
        """
        self.ws = ws
        self.max_row = ws.max_row
        self.max_col = ws.max_column

        # (строка, столбец) → диапазон объединения, в который она входит
        self._span: dict[tuple[int, int], Span] = {}
        for merged in ws.merged_cells.ranges:
            span = Span(merged.min_row, merged.min_col,
                        merged.max_row, merged.max_col)
            for r in span.rows:
                for c in span.cols:
                    self._span[(r, c)] = span

        # нормализованный текст → координаты всех ячеек с этим текстом
        self._index: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for row in ws.iter_rows(min_row=1, max_row=self.max_row,
                                max_col=self.max_col):
            for cell in row:
                if isinstance(cell.value, str):
                    key = norm(cell.value)
                    if key:
                        self._index[key].append((cell.row, cell.column))
        self._keys = sorted(self._index)

    # --- доступ к значениям --------------------------------------------------
    def span(self, row: int, col: int) -> Span:
        """Диапазон объединения, в который входит ячейка.

        Одиночная ячейка возвращается как диапазон из самой себя,
        поэтому вызывающему коду не нужно различать эти случаи.
        """
        return self._span.get((row, col), Span(row, col, row, col))

    def raw(self, row: int, col: int):
        """Значение ячейки без учёта объединения."""
        if row < 1 or col < 1:
            return None
        return self.ws.cell(row=row, column=col).value

    def value(self, row: int, col: int):
        """Значение с учётом объединения: любая ячейка диапазона даёт значение."""
        span = self.span(row, col)
        return self.raw(span.row, span.col)

    def text(self, row: int, col: int) -> str:
        """Значение ячейки в виде строки без окружающих пробелов."""
        value = self.value(row, col)
        return "" if value is None else str(value).strip()

    # --- поиск подписей ------------------------------------------------------
    def has_label(self, label: str, mode: str = "starts") -> bool:
        """Есть ли на листе такая подпись. Используется для опознания листа."""
        key = norm(label)
        if not key:
            return False
        if mode == "exact":
            return key in self._index
        return any(existing.startswith(key) for existing in self._keys)

    def find_all(self, label: str, *, mode: str = "exact",
                 rows: tuple[int, int] | None = None,
                 cols: tuple[int, int] | str | None = None) -> list[Span]:
        """Все ячейки с подписью label. mode: exact | starts | contains."""
        if mode not in ("exact", "starts", "contains"):
            raise ValueError(f"неизвестный режим поиска: {mode}")
        key = norm(label)
        if not key:
            return []
        if mode == "exact":
            candidates = self._index.get(key, [])
        else:
            matched: list[tuple[int, int]] = []
            for existing in self._keys:
                if (existing.startswith(key) if mode == "starts"
                        else key in existing):
                    matched.extend(self._index[existing])
            candidates = sorted(matched)

        lo_col, hi_col = _col_bounds(cols)
        out: list[Span] = []
        for row, col in candidates:
            if rows and not (rows[0] <= row <= rows[1]):
                continue
            if not (lo_col <= col <= hi_col):
                continue
            out.append(self.span(row, col))
        # один объединённый диапазон не должен попасть в результат дважды
        unique: list[Span] = []
        for span in out:
            if span not in unique:
                unique.append(span)
        return unique

    def find(self, label: str, *, mode: str = "exact", nth: int = 0,
             rows: tuple[int, int] | None = None,
             cols: tuple[int, int] | str | None = None) -> Span | None:
        """Первая подпись, удовлетворяющая условиям поиска.

        Args:
            label: Искомый текст.
            mode: ``exact``, ``starts`` или ``contains``.
            nth: Номер совпадения, если их несколько.
            rows: Ограничение по строкам.
            cols: Ограничение по столбцам: «A» или «A:C».

        Returns:
            Диапазон найденной ячейки или None.
        """
        found = self.find_all(label, mode=mode, rows=rows, cols=cols)
        return found[nth] if len(found) > nth else None

    # --- работа со строками --------------------------------------------------
    def numbers_right(self, row: int, col: int, limit: int = 3,
                      within: int = 12) -> list[float]:
        """Первые числа правее ячейки. Нужно там, где значения не выровнены
        по столбцам шапки — например, в строках подытогов и разбивок.
        """
        out: list[float] = []
        for c in range(col + 1, min(col + within, self.max_col) + 1):
            value = self.raw(row, c)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                out.append(float(value))
                if len(out) >= limit:
                    break
        return out

    def leftmost_text_col(self, rows: tuple[int, int],
                          cols: tuple[int, int] | str | None = None) -> int | None:
        """Левый столбец, в котором у строк данных есть текст.

        Значения берутся без учёта объединений: подпись блока, растянутая
        на весь столбец A, не должна выдавать себя за столбец с данными.
        """
        lo, hi = _col_bounds(cols)
        hi = min(hi, self.max_col)
        for col in range(max(lo, 1), hi + 1):
            for row in range(rows[0], rows[1] + 1):
                value = self.raw(row, col)
                if isinstance(value, str) and value.strip() not in ("", "-", "—"):
                    return col
        return None


def _col_bounds(cols: tuple[int, int] | str | None) -> tuple[int, int]:
    """Границы столбцов из «A», «A:C» или пары номеров."""
    if cols is None:
        return 1, 16384
    if isinstance(cols, str):
        letters = cols.split(":")
        lo = column_index_from_string(letters[0])
        hi = column_index_from_string(letters[-1])
        return lo, hi
    return cols
