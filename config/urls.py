# -*- coding: utf-8 -*-
"""Корневая таблица адресов.

Разделы приложения подключаются своими наборами адресов, чтобы состав
страниц был виден в одном месте.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("reports/", include("apps.reports.urls")),
    path("", include("apps.analytics.urls")),
]

admin.site.site_header = "Суточный рапорт — управление"
admin.site.site_title = "Суточный рапорт"
admin.site.index_title = "Справочники и пользователи"
