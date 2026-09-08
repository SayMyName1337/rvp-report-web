# -*- coding: utf-8 -*-
"""Дашборд руководства. Наполняется данными на седьмом этапе."""
from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class DashboardView(LoginRequiredMixin, TemplateView):
    """Главная страница: показатели за последние сутки и графики."""

    template_name = "analytics/dashboard.html"
