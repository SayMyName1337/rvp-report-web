# -*- coding: utf-8 -*-
"""Построение презентации PowerPoint.

Слой знает про оформление и вёрстку, но не про то, откуда взялись данные:
на вход подаётся готовая модель :class:`~rvp_report.domain.model.DailyReport`.
"""

from .slides import build

__all__ = ["build"]
