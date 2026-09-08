# -*- coding: utf-8 -*-
"""Чтение суточного рапорта из книги Excel.

Разделы и столбцы отыскиваются по подписям в самом файле, поэтому
вставка строк или столбцов в шаблон не нарушает разбор. Схема описана
в :mod:`layout`, привязка к конкретному файлу — в :mod:`resolve`.
"""

from .reader import ReportReader, layout_report, read_report

__all__ = ["ReportReader", "read_report", "layout_report"]
