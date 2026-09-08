# -*- coding: utf-8 -*-
"""Настройка раздела «Презентации»."""
from django.apps import AppConfig


class DecksConfig(AppConfig):
    """Сборка презентации PowerPoint по данным суток."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.decks"
    verbose_name = "Презентации"
