# -*- coding: utf-8 -*-
"""Настройка раздела «Пользователи»."""
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Учётные записи и роли."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Пользователи и роли"
