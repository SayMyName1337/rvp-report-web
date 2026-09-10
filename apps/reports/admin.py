# -*- coding: utf-8 -*-
"""Панель управления суточными данными.

Ежедневная работа идёт через страницы приложения, а не здесь: эти
страницы нужны администратору для разбирательств — посмотреть, что
записано за конкретные сутки, откуда взята цифра и какой файл был
загружен. Поэтому всё открыто только на чтение: править суточные данные
руками нельзя, их источник — рапорт.
"""
from __future__ import annotations

from django.contrib import admin

from .models import (DowntimeBreakdownDaily, LoadIssue, ProvenanceEntry,
                     Report, Upload, WellDaily)


class ReadOnlyInline(admin.TabularInline):
    """Вложенная таблица только для чтения."""

    extra = 0
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None) -> bool:
        """Добавлять строки руками нельзя: источник данных — рапорт."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Править строки руками нельзя: источник данных — рапорт."""
        return False


class IssueInline(ReadOnlyInline):
    """Замечания к данным за эти сутки."""

    model = LoadIssue
    fields = ("level", "where", "message")
    readonly_fields = fields


class BreakdownInline(ReadOnlyInline):
    """Разбивка простоя по причинам за эти сутки."""

    model = DowntimeBreakdownDaily
    fields = ("reason", "wells_count", "qo")
    readonly_fields = fields


class UploadInline(ReadOnlyInline):
    """История загрузок за эти сутки."""

    model = Upload
    fields = ("original_name", "uploaded_by", "uploaded_at", "status",
              "is_current")
    readonly_fields = fields


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """Суточные рапорты."""

    list_display = ("date", "status", "issues_count", "updated_at")
    list_filter = ("status",)
    date_hierarchy = "date"
    ordering = ("-date",)
    inlines = [UploadInline, BreakdownInline, IssueInline]
    readonly_fields = ("date", "temperature", "wind", "gas_utilization_pct",
                       "free_volume_total_m3", "created_at", "updated_at")

    @admin.display(description="Замечаний")
    def issues_count(self, obj: Report) -> int:
        """Сколько замечаний к данным найдено при загрузке."""
        return obj.issues.count()

    def has_add_permission(self, request) -> bool:
        """Сутки создаются загрузкой рапорта, а не вручную."""
        return False


@admin.register(Upload)
class UploadAdmin(admin.ModelAdmin):
    """Загруженные файлы рапортов."""

    list_display = ("original_name", "report", "uploaded_by", "uploaded_at",
                    "status", "is_current")
    list_filter = ("status", "is_current")
    search_fields = ("original_name", "sha256")
    readonly_fields = ("sha256", "size", "uploaded_at", "log")

    def has_add_permission(self, request) -> bool:
        """Файлы загружаются через страницу загрузки."""
        return False


@admin.register(ProvenanceEntry)
class ProvenanceAdmin(admin.ModelAdmin):
    """Происхождение показателей: откуда взялась каждая цифра."""

    list_display = ("report", "section", "label", "value", "kind", "origin")
    list_filter = ("kind", "section")
    search_fields = ("label", "origin")

    def has_add_permission(self, request) -> bool:
        """Записи создаются при разборе рапорта."""
        return False


@admin.register(WellDaily)
class WellDailyAdmin(admin.ModelAdmin):
    """Скважины по суткам."""

    list_display = ("report", "well", "category", "qo", "reason")
    list_filter = ("category",)
    search_fields = ("well__number", "reason")
    autocomplete_fields = ("well",)

    def has_add_permission(self, request) -> bool:
        """Записи создаются при разборе рапорта."""
        return False
