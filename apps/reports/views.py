# -*- coding: utf-8 -*-
"""Страницы суточных рапортов. Наполняются на третьем и четвёртом этапах."""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class ReportListView(LoginRequiredMixin, TemplateView):
    """Список загруженных суточных рапортов."""

    template_name = "reports/list.html"
