# -*- coding: utf-8 -*-
"""Настройка раздела «Сводки и дашборд»."""
from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """Сводки за период и дашборд руководства: агрегаты по суткам
с контролем полноты данных."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analytics"
    verbose_name = "Сводки и дашборд"
