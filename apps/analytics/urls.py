# -*- coding: utf-8 -*-
"""Адреса раздела «Сводки и дашборд»."""
from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
]
