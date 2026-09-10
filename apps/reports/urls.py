# -*- coding: utf-8 -*-
"""Адреса раздела «Суточные рапорты»."""
from django.urls import path, register_converter

from . import views


class DayConverter:
    """Дата в адресе в виде ``2026-08-21``."""

    regex = r"\d{4}-\d{2}-\d{2}"

    def to_python(self, value: str) -> str:
        """Оставить дату строкой: запрос по ней работает как есть."""
        return value

    def to_url(self, value) -> str:
        """Дата в адресе всегда в виде «год-месяц-день»."""
        return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") \
            else str(value)


register_converter(DayConverter, "day")

app_name = "reports"

urlpatterns = [
    path("", views.ReportListView.as_view(), name="list"),
    path("<day:day>/", views.ReportDetailView.as_view(), name="detail"),
    path("<day:day>/sources/", views.ReportSourcesView.as_view(),
         name="sources"),
]
