# -*- coding: utf-8 -*-
"""Панель управления презентациями и журналом выдач."""
from django.contrib import admin

from .models import Deck, Download


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    """Собранные презентации."""

    list_display = ("report", "upload", "built_at")
    readonly_fields = ("built_at",)

    def has_add_permission(self, request) -> bool:
        """Презентации собираются по запросу, а не заводятся руками."""
        return False


@admin.register(Download)
class DownloadAdmin(admin.ModelAdmin):
    """Журнал выдач файлов. Записи не редактируются и не удаляются."""

    list_display = ("at", "user", "kind", "name", "report")
    list_filter = ("kind",)
    search_fields = ("name", "user__username")
    readonly_fields = ("report", "kind", "name", "user", "at")

    def has_add_permission(self, request) -> bool:
        """Записи создаёт только выдача файла."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Журнал выдач не чистится: в этом его смысл."""
        return False
