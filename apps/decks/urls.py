# -*- coding: utf-8 -*-
"""Адреса выдачи презентаций и исходных файлов."""
from django.urls import path

from . import views

app_name = "decks"

urlpatterns = [
    path("downloads/", views.DownloadsView.as_view(), name="downloads"),
    path("<day:day>/pptx/", views.DeckView.as_view(), name="pptx"),
    path("<day:day>/pdf/", views.PdfView.as_view(), name="pdf"),
    path("<day:day>/source/", views.SourceView.as_view(), name="source"),
]
