# -*- coding: utf-8 -*-
"""Панель управления поправками к разметке."""
from django.contrib import admin

from .models import LayoutFix


@admin.register(LayoutFix)
class LayoutFixAdmin(admin.ModelAdmin):
    """Поправки, указанные оператором."""

    list_display = ("key", "label", "kind", "value", "is_active",
                    "created_by", "created_at")
    list_filter = ("is_active", "kind")
    search_fields = ("key", "label", "value")
    readonly_fields = ("created_at",)
