# -*- coding: utf-8 -*-
"""Выдача презентаций и исходных рапортов.

Файлы содержат коммерческую тайну, поэтому отдаются не веб-сервером
напрямую, а отсюда: с проверкой прав и записью в журнал выдач.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import TemplateView, View

from apps.reports.models import Report
from config.errors import Missing

from . import services
from .models import Deck, Download

#: Тип содержимого презентации PowerPoint.
PPTX_TYPE = ("application/vnd.openxmlformats-officedocument"
             ".presentationml.presentation")


class DeckView(LoginRequiredMixin, View):
    """Скачивание презентации за сутки.

    Собирается при первом обращении и сохраняется: за одни сутки её
    скачивают несколько человек, пересобирать каждый раз незачем.
    """

    def get(self, request, *args, **kwargs):
        """Отдать презентацию, собрав её при необходимости."""
        report = get_object_or_404(Report, date=kwargs["day"])
        try:
            deck = services.build_deck(report)
        except FileNotFoundError:
            messages.error(
                request,
                "Исходный файл рапорта за эти сутки не сохранён, "
                "собрать презентацию не из чего.")
            return redirect(reverse("reports:detail", args=[report.date]))

        name = services.deck_name(report)
        services.record_download(report, Download.Kind.DECK, name,
                                 request.user)
        return FileResponse(deck.file.open("rb"), as_attachment=True,
                            filename=name, content_type=PPTX_TYPE)


class PdfView(LoginRequiredMixin, View):
    """Скачивание презентации в формате PDF.

    Перевод выполняет LibreOffice. На машине разработки его может
    не быть — тогда об этом говорится прямо, а не молча отдаётся
    пустой файл.
    """

    def get(self, request, *args, **kwargs):
        """Отдать PDF или объяснить, почему его нет."""
        report = get_object_or_404(Report, date=kwargs["day"])
        try:
            deck = services.build_deck(report)
            pdf = services.to_pdf(Path(deck.file.path))
        except FileNotFoundError:
            messages.error(request, "Исходный файл рапорта не сохранён.")
            return redirect(reverse("reports:detail", args=[report.date]))
        except RuntimeError as error:
            messages.warning(request, str(error))
            return redirect(reverse("reports:detail", args=[report.date]))

        name = f"Суточный рапорт {report.date:%Y-%m-%d}.pdf"
        services.record_download(report, Download.Kind.DECK, name,
                                 request.user)
        return FileResponse(BytesIO(pdf), as_attachment=True,
                            filename=name, content_type="application/pdf")


class SourceView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Скачивание исходного рапорта.

    Доступно только работникам промысла и администратору: в исходном
    файле есть сведения, которые в базу намеренно не попадают, —
    фамилии и медицинские подробности из описания происшествия
    и текста обращений в здравпункт.
    """

    def test_func(self) -> bool:
        """Может ли пользователь получить исходный файл."""
        return bool(getattr(self.request.user, "can_upload", False))

    def get(self, request, *args, **kwargs):
        """Отдать исходный файл действующей загрузки."""
        report = get_object_or_404(Report, date=kwargs["day"])
        upload = report.uploads.filter(is_current=True).first()
        if upload is None or not upload.file:
            raise Missing("исходный файл рапорта за эти сутки не сохранён")

        services.record_download(report, Download.Kind.SOURCE,
                                 upload.original_name, request.user)
        return FileResponse(upload.file.open("rb"), as_attachment=True,
                            filename=upload.original_name)


class DownloadsView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Журнал выдач: кто, что и когда скачал."""

    template_name = "decks/downloads.html"

    def test_func(self) -> bool:
        """Журнал доступен тем, кто отвечает за данные."""
        return bool(getattr(self.request.user, "can_upload", False))

    def get_context_data(self, **kwargs) -> dict:
        """Собрать последние записи журнала."""
        context = super().get_context_data(**kwargs)
        context["rows"] = (Download.objects
                           .select_related("user", "report")[:200])
        context["decks"] = Deck.objects.count()
        context["pdf_ready"] = bool(services.soffice())
        return context
