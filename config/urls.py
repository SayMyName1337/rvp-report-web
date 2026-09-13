# -*- coding: utf-8 -*-
"""Корневая таблица адресов.

Разделы приложения подключаются своими наборами адресов, чтобы состав
страниц был виден в одном месте.
"""
from django.contrib import admin
from django.urls import include, path, register_converter

from .converters import DayConverter

register_converter(DayConverter, "day")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("reports/", include("apps.reports.urls")),
    path("layout/", include("apps.layout.urls")),
    path("decks/", include("apps.decks.urls")),
    path("", include("apps.analytics.urls")),
]

#: Своя страница «не найдено». Остальные Django берёт по имени шаблона:
#: ``400.html``, ``403.html``, ``403_csrf.html``, ``500.html``.
handler404 = "config.errors.not_found"

admin.site.site_header = "Суточный рапорт — управление"
admin.site.site_title = "Суточный рапорт"
admin.site.index_title = "Справочники и пользователи"
