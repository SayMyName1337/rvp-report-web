# -*- coding: utf-8 -*-
"""Панель управления пользователями.

Учётные записи заводит администратор: самостоятельной регистрации нет.
Поэтому форма создания сразу спрашивает ФИО, должность и роль.
"""
from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Учётные записи работников."""

    list_display = ("username", "short_name", "position", "roles_display",
                    "is_active", "last_login")
    list_filter = ("is_active", "groups", "department")
    search_fields = ("username", "last_name", "first_name", "patronymic",
                     "position", "email")
    ordering = ("last_name", "first_name")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Работник", {"fields": ("last_name", "first_name", "patronymic",
                                 "position", "department", "phone", "email")}),
        ("Доступ", {"fields": ("groups", "is_active", "must_change_password",
                               "is_staff", "is_superuser")}),
        ("Служебное", {"fields": ("last_login", "date_joined"),
                       "classes": ("collapse",)}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "usable_password", "password1", "password2"),
        }),
        ("Работник", {"fields": ("last_name", "first_name", "patronymic",
                                 "position", "department", "phone", "email")}),
        ("Доступ", {"fields": ("groups", "is_active")}),
    )

    @admin.display(description="Роли")
    def roles_display(self, obj: User) -> str:
        """Роли пользователя одной строкой."""
        return ", ".join(obj.roles) or "—"
