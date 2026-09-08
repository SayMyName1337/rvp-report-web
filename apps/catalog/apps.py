# -*- coding: utf-8 -*-
"""Настройка раздела «Справочники»."""
from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """Справочники: месторождения, скважины, объекты ППД, узлы учёта,
резервуары, подрядчики, причины простоя."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    verbose_name = "Справочники"
