# -*- coding: utf-8 -*-
"""Панель управления справочниками.

Главная задача этих страниц — разбор новичков: записи, заведённые
автоматически при загрузке рапорта, ждут подтверждения. Поэтому
признак «требует проверки» вынесен в список и в фильтры, а подтверждение
сделано групповым действием.
"""
from __future__ import annotations

from django.contrib import admin

from .models import (Contractor, DowntimeReason, Field, FieldAlias,
                     InjectionObject, MeteringNode, PowerObject, Tank, Well)


@admin.action(description="Подтвердить: проверка больше не требуется")
def confirm(modeladmin, request, queryset) -> None:
    """Снять признак «требует проверки» с выбранных записей."""
    updated = queryset.update(needs_review=False)
    modeladmin.message_user(request, f"Подтверждено записей: {updated}")


class ReferenceAdmin(admin.ModelAdmin):
    """Общие настройки страниц справочников."""

    list_display = ("name", "needs_review", "is_active", "created_at")
    list_filter = ("needs_review", "is_active")
    search_fields = ("name",)
    actions = [confirm]
    readonly_fields = ("key", "created_at")


class FieldAliasInline(admin.TabularInline):
    """Синонимы написания прямо на странице месторождения."""

    model = FieldAlias
    extra = 1
    readonly_fields = ("key",)


@admin.register(Field)
class FieldAdmin(ReferenceAdmin):
    """Месторождения и их синонимы."""

    list_display = ("name", "short_name", "aliases_display", "needs_review",
                    "is_active")
    inlines = [FieldAliasInline]

    @admin.display(description="Синонимы")
    def aliases_display(self, obj: Field) -> str:
        """Все написания месторождения одной строкой."""
        return ", ".join(alias.name for alias in obj.aliases.all()) or "—"


@admin.register(Well)
class WellAdmin(admin.ModelAdmin):
    """Скважины."""

    list_display = ("number", "field", "category", "needs_review", "is_active")
    list_filter = ("needs_review", "is_active", "category", "field")
    search_fields = ("number",)
    autocomplete_fields = ("field",)
    actions = [confirm]
    readonly_fields = ("created_at",)


for model in (InjectionObject, MeteringNode, Tank, Contractor,
              DowntimeReason, PowerObject):
    admin.site.register(model, ReferenceAdmin)
