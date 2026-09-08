# -*- coding: utf-8 -*-
"""Настройка раздела «Суточные рапорты»."""
from django.apps import AppConfig


class ReportsConfig(AppConfig):
    """Суточные рапорты: загрузка файла, разбор, хранение данных за сутки
и журнал происхождения показателей."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reports"
    verbose_name = "Суточные рапорты"
