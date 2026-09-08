# -*- coding: utf-8 -*-
"""Адреса раздела «Суточные рапорты»."""
from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportListView.as_view(), name="list"),
]
