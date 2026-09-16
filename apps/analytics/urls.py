# -*- coding: utf-8 -*-
"""Адреса раздела «Сводки и дашборд»."""
from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("summary/", views.SummaryView.as_view(), name="summary"),
    path("summary/sheet/", views.SummarySheetView.as_view(),
         name="summary_sheet"),
    path("summary/sheet/<str:fmt>/", views.SummarySheetView.as_view(),
         name="summary_sheet_format"),
    path("quality/", views.QualityView.as_view(), name="quality"),
    path("quality/<int:pk>/reviewed/", views.ReviewView.as_view(),
         name="reviewed"),
]
