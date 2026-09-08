# -*- coding: utf-8 -*-
"""Привязка схемы из layout.py к конкретному файлу.

Всё, что найдено по подписи, используется как есть. Всё, что не найдено,
берётся из эталонного адреса и попадает в список degraded — тогда программа
продолжает работать, но честно сообщает, что именно «поехало».
"""
from __future__ import annotations

from openpyxl.utils import (column_index_from_string, coordinate_to_tuple,
                            get_column_letter)

from . import layout as L
from .sheet import Sheet, Span
from .spec import Block, Col, Cross, Find, Resolved, Scalar, Table


def _ref_cell(reference: str) -> tuple[int, int] | None:
    """Координаты ячейки из адреса вида «K28» или None."""
    if not reference:
        return None
    try:
        return coordinate_to_tuple(reference)
    except (ValueError, TypeError):
        return None


def _ref_col(reference: str) -> int | None:
    """Номер столбца из буквы или None."""
    if not reference:
        return None
    try:
        return column_index_from_string(reference)
    except (ValueError, TypeError):
        return None


class Resolver:
    """Привязка схемы рапорта к конкретному листу.

    Каждый элемент схемы ищется по подписи; если подпись не найдена,
    берётся эталонный адрес, а сам факт попадает в список ``degraded``.
    """
    def __init__(self, sheet: Sheet):
        """Args:
        sheet: Лист суточного рапорта.
        """
        self.sheet = sheet
        self.out = Resolved()
        #: На сколько столбцов сдвинута таблица относительно эталона.
        #: Определяется по левым заголовкам и применяется ко всем привязкам,
        #: заданным буквой столбца, — тогда вставка столбца слева не ломает
        #: разбор так же, как его не ломает вставка строк.
        self.col_offset = 0

    # --- сдвиг столбцов ------------------------------------------------------
    def _detect_col_offset(self) -> int:
        """Определить горизонтальный сдвиг листа по левым заголовкам.

        Берётся несколько заголовков разделов, которые всегда стоят
        в самом левом столбце. Их фактическое положение показывает,
        на сколько столбцов сдвинут весь лист. Берётся согласие
        большинства, поэтому переименование одного заголовка сдвиг
        не искажает.

        Returns:
            Сдвиг в столбцах: 0 для неизменённого файла.
        """
        columns: list[int] = []
        for text in L.LEFT_COLUMN_MARKERS:
            span = self.sheet.find(text, mode="starts")
            if span is not None:
                columns.append(span.col)
        if not columns:
            return 0
        base = max(set(columns), key=columns.count)
        return max(0, base - 1)

    def _shift(self, cols: str | None) -> str | None:
        """Сдвинуть окно столбцов на обнаруженную величину.

        Args:
            cols: Ограничение из схемы — «A» или «A:C», либо None.

        Returns:
            Сдвинутое окно; None и уже готовые диапазоны возвращаются
            без изменений.
        """
        if not self.col_offset or not isinstance(cols, str):
            return cols
        shifted = [
            get_column_letter(column_index_from_string(part) + self.col_offset)
            for part in cols.split(":")]
        return ":".join(shifted)

    # --- поиск подписи -------------------------------------------------------
    def _find(self, find: Find, rows: tuple[int, int] | None = None,
              cols: str | tuple[int, int] | None = None) -> Span | None:
        """Найти подпись, перебирая основной вариант и синонимы."""
        window = cols if cols is not None else find.cols
        if isinstance(window, str):
            window = self._shift(window)
        for label in find.labels:
            span = self.sheet.find(label, mode=find.mode, nth=find.nth,
                                   rows=rows, cols=window)
            if span is not None:
                return span
        return None

    # --- разделы -------------------------------------------------------------
    def blocks(self) -> None:
        """Определить строки всех разделов рапорта.

        Раздел заканчивается там, где начинается следующий, поэтому
        границы вычисляются, а не задаются в схеме.
        """
        starts: dict[str, int] = {}
        by_key: dict[str, Block] = {}
        for block in L.BLOCKS:
            by_key[block.key] = block
            span = self._find(block.anchor)
            if span is None:
                starts[block.key] = block.reference_row
                self.out.degraded.append(
                    f"раздел «{block.title}» не найден по заголовку — "
                    f"взята строка {block.reference_row} по эталону")
            else:
                starts[block.key] = span.row
                if span.row != block.reference_row:
                    self.out.notes.append(
                        f"раздел «{block.title}»: строка {span.row} "
                        f"вместо эталонной {block.reference_row}")

        ordered = sorted(set(starts.values()))
        for key, start in starts.items():
            explicit = by_key[key].ends_before
            if explicit and explicit in starts:
                end = starts[explicit] - 1
            else:
                following = [r for r in ordered if r > start]
                end = (following[0] - 1) if following else self.sheet.max_row
            self.out.blocks[key] = (start, max(start, end))

    def _block_rows(self, key: str) -> tuple[int, int] | None:
        """Границы строк блока или None, если блок не задан."""
        return self.out.blocks.get(key) if key else None

    # --- одиночные показатели ------------------------------------------------
    def scalar(self, name: str, item: Scalar) -> None:
        """Привязать одиночный показатель к ячейке листа.

        Args:
            name: Ключ показателя в разрешённой схеме.
            item: Описание показателя из схемы.
        """
        span = self._find(item.find, rows=self._block_rows(item.block))
        if span is not None:
            cell = self._value_cell(span, item)
            if cell is not None:
                self.out.cells[name] = cell
                return
            self.out.degraded.append(
                f"рядом с подписью «{item.find.label}» нет числового значения — "
                f"взята ячейка {item.reference or '—'}")
        self.out.cells[name] = _ref_cell(item.reference)
        self.out.degraded.append(
            f"показатель «{item.find.label}» не найден — "
            f"взята ячейка {item.reference or '—'}")

    def _value_cell(self, span: Span, item: Scalar) -> tuple[int, int] | None:
        """Где лежит значение показателя относительно его подписи."""
        if not item.search:
            return (span.row + item.dr, span.col + item.dc)

        if item.search == "right":
            steps = [(span.row, c)
                     for c in range(span.last_col + 1,
                                    span.last_col + item.within + 1)]
        else:
            steps = [(r, span.col)
                     for r in range(span.last_row + 1,
                                    span.last_row + item.within + 1)]
        for row, col in steps:
            if row > self.sheet.max_row or col > self.sheet.max_col:
                break
            value = self.sheet.value(row, col)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return (row, col)
        return None

    def cross(self, name: str, item: Cross) -> None:
        """Привязать показатель на пересечении строки и столбца.

        Args:
            name: Ключ показателя в разрешённой схеме.
            item: Описание показателя из схемы.
        """
        rows = self._block_rows(item.block)
        row_span = self._find(item.row, rows=rows)
        col_span = self._find(item.col, rows=rows)
        if row_span is not None and col_span is not None:
            self.out.cells[name] = (row_span.row, col_span.col)
            return
        self.out.cells[name] = _ref_cell(item.reference)
        missing = item.row.label if row_span is None else item.col.label
        self.out.degraded.append(
            f"показатель на пересечении «{missing}» не найден — "
            f"взята ячейка {item.reference or '—'}")

    # --- таблицы -------------------------------------------------------------
    def table(self, name: str, table: Table) -> None:
        """Определить столбцы и строки данных таблицы.

        Args:
            name: Ключ таблицы в разрешённой схеме.
            table: Описание таблицы из схемы.
        """
        block_rows = self.out.blocks.get(table.block)
        if block_rows is None:
            block_rows = table.reference_rows
        start, end = block_rows
        header_zone = (start, min(start + table.header_depth, end))

        window = self._shift(table.cols)
        columns: dict[str, int] = {}
        header_rows: list[int] = []
        deferred: list[tuple[str, Col]] = []

        for key, col in table.columns.items():
            if col.anchor_col:
                deferred.append((key, col))
                continue
            span = self._resolve_col(col, header_zone, window)
            if span is None:
                if col.optional:
                    continue
                fallback = _ref_col(col.reference)
                if fallback:
                    columns[key] = fallback
                    self.out.degraded.append(
                        f"{name}: столбец «{col.label or key}» не найден — "
                        f"взят {col.reference} по эталону")
                continue
            base = span.last_col if col.pick == "last" else span.col
            columns[key] = base + col.dc
            header_rows.append(span.last_row)

        header_end = max(header_rows) if header_rows else start
        first_data = header_end + 1

        total_row = None
        if table.total is not None:
            total_span = self._find(table.total, rows=(start, end))
            total_row = total_span.row if total_span else None

        data_end = end
        if total_row is not None and total_row >= first_data:
            # строка ИТОГО бывает и первой (сводка по обществу), и последней
            if total_row == first_data:
                first_data += 1
            else:
                data_end = min(data_end, total_row - 1)

        rows = (first_data, max(first_data, data_end))

        for key, col in deferred:
            found = self.sheet.leftmost_text_col(rows, window)
            columns[key] = found or _ref_col(col.reference) or 1
            if found is None:
                self.out.degraded.append(
                    f"{name}: столбец «{key}» не определён — "
                    f"взят {col.reference} по эталону")

        self.out.columns[name] = columns
        self.out.rows[name] = rows
        self.out.totals[name] = total_row

    def _resolve_col(self, col: Col, header_zone: tuple[int, int],
                     window: str | None) -> Span | None:
        """Найти столбец по шапке, при необходимости сузив поиск родителем."""
        scope: str | tuple[int, int] | None = window
        if col.parent:
            parent = self.sheet.find(col.parent, mode="exact",
                                     rows=header_zone, cols=window)
            if parent is None:
                return None
            scope = (parent.col, parent.last_col)
        for label in col.labels:
            span = self.sheet.find(label, mode=col.mode, nth=col.nth,
                                   rows=header_zone, cols=scope)
            if span is not None:
                return span
        return None

    # --- сборка --------------------------------------------------------------
    def run(self) -> Resolved:
        """Выполнить привязку всей схемы.

        Returns:
            Разрешённую схему со строками разделов, столбцами таблиц
            и списком элементов, взятых по эталону.
        """
        self.col_offset = self._detect_col_offset()
        self.blocks()

        for name, item in {**L.HEADER, **L.PRODUCTION, **L.POWER}.items():
            self.scalar(name, item)
        for name, item in L.DELIVERY.items():
            if isinstance(item, Cross):
                self.cross(name, item)
            else:
                self.scalar(name, item)

        self.scalar("fields_header", L.FIELDS_ROW)
        self.scalar("free_volume_total", L.FREE_VOLUME_TOTAL)
        self.scalar("gas_consumers_total", L.GAS_CONSUMERS_TOTAL)
        self.scalar("diesel_left", L.DIESEL_LEFT)
        self.scalar("diesel_stock", L.DIESEL_STOCK)
        self.scalar("hse_medical", L.HSE_MEDICAL)

        for name, table in TABLES.items():
            self.table(name, table)
        return self.out


TABLES: dict[str, Table] = {
    "hse": L.HSE,
    "stock": L.STOCK,
    "startups": L.STARTUPS,
    "idle": L.IDLE,
    "downtime": L.DOWNTIME,
    "vsp": L.VSP,
    "rampup": L.RAMP_UP,
    "muslyd": L.MUS_LYD,
    "control": L.CONTROL_GTM,
    "injection": L.INJECTION,
    "tanks_left": L.TANKS_LEFT,
    "tanks_right": L.TANKS_RIGHT,
    "quality": L.OIL_QUALITY,
    "gas": L.GAS,
    "pigging": L.PIGGING,
    "drilling": L.DRILLING,
}


def resolve(sheet: Sheet) -> Resolved:
    """Привязать схему рапорта к листу.

    Args:
        sheet: Лист суточного рапорта.

    Returns:
        Разрешённую схему для чтения данных.
    """
    return Resolver(sheet).run()


def describe(resolved: Resolved) -> str:
    """Человекочитаемая карта привязки — для режима --check."""
    lines = ["Разделы:"]
    for block in L.BLOCKS:
        rows = resolved.blocks.get(block.key)
        if rows:
            mark = " " if rows[0] == block.reference_row else "!"
            lines.append(f" {mark} {block.title:<24} строки {rows[0]}–{rows[1]}"
                         f"   (эталон {block.reference_row})")
    lines.append("")
    lines.append("Таблицы:")
    for name in TABLES:
        rows = resolved.rows.get(name)
        cols = resolved.columns.get(name, {})
        if not rows:
            continue
        letters = " ".join(f"{k}={get_column_letter(v)}"
                           for k, v in sorted(cols.items()))
        lines.append(f"   {name:<12} данные {rows[0]}–{rows[1]}")
        lines.append(f"                {letters}")
    return "\n".join(lines)
