# -*- coding: utf-8 -*-
"""Раздел «Инструкция»."""
from django.apps import AppConfig


class GuideConfig(AppConfig):
    """Руководство по работе с системой."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.guide"
    verbose_name = "Инструкция"
