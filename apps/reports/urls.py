# -*- coding: utf-8 -*-
"""Адреса раздела «Суточные рапорты».

Преобразователь ``day`` объявлен в :mod:`config.urls`: он нужен и здесь,
и в редакторе разметки, а регистрируется один раз на проект.
"""
from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportListView.as_view(), name="list"),
    path("wells/", views.WellListView.as_view(), name="wells"),
    path("wells/<int:pk>/", views.WellDetailView.as_view(), name="well"),
    path("<day:day>/", views.ReportDetailView.as_view(), name="detail"),
    path("<day:day>/sources/", views.ReportSourcesView.as_view(),
         name="sources"),
]
