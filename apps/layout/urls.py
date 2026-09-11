# -*- coding: utf-8 -*-
"""Адреса редактора разметки."""
from django.urls import path

from . import views

app_name = "layout"

urlpatterns = [
    path("", views.PendingView.as_view(), name="pending"),
    path("journal/", views.JournalView.as_view(), name="journal"),
    path("fix/<int:pk>/toggle/", views.ToggleView.as_view(), name="toggle"),
    path("<day:day>/<str:key>/", views.ConfirmView.as_view(), name="confirm"),
    path("<day:day>/<str:key>/apply/", views.ApplyView.as_view(),
         name="apply"),
]
