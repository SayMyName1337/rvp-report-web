# -*- coding: utf-8 -*-
"""Настройка раздела «Разметка»."""
from django.apps import AppConfig


class LayoutConfig(AppConfig):
    """Поправки к разметке рапорта, сделанные оператором."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.layout"
    verbose_name = "Разметка рапорта"
