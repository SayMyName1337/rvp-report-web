# -*- coding: utf-8 -*-
"""Адрес раздела «Инструкция»."""
from django.urls import path

from . import views

app_name = "guide"

urlpatterns = [
    path("", views.GuideView.as_view(), name="index"),
]
