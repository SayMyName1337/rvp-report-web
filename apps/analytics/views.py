# -*- coding: utf-8 -*-
"""Сводки за период и дашборд руководства."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from django.contrib.auth.mixins import (LoginRequiredMixin,
                                        UserPassesTestMixin)
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import TemplateView, View

from apps.reports.models import Report

from . import dashboard, periods, summary
from .models import CrossCheck


def _parse_day(value: str) -> date | None:
    """Дата из строки вида ``2026-08-21`` или None."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


class DashboardView(LoginRequiredMixin, TemplateView):
    """Дашборд руководства: последние сутки, ход месяца и доверие к данным."""

    template_name = "analytics/dashboard.html"

    def get_context_data(self, **kwargs) -> dict:
        """Собрать показатели, динамику и оговорки к цифрам."""
        context = super().get_context_data(**kwargs)
        context.update(dashboard.build())
        return context


class QualityView(LoginRequiredMixin, TemplateView):
    """Качество исходных данных: что нашли внутри суток и между сутками."""

    template_name = "analytics/quality.html"

    def get_context_data(self, **kwargs) -> dict:
        """Собрать замечания обоих видов за выбранный период."""
        context = super().get_context_data(**kwargs)
        period = _period_from(self.request, "month")
        rows = (CrossCheck.objects
                .filter(report__date__range=(period.start, period.end))
                .select_related("report")
                .order_by("-report__date", "kind"))

        context["period"] = period
        context["kinds"] = periods.KINDS
        context["previous"] = periods.shift(period, -1)
        context["next"] = periods.shift(period, 1)
        context["cross"] = rows
        context["pending"] = rows.filter(reviewed=False).count()
        names = dict(CrossCheck.Kind.choices)
        context["by_kind"] = [
            {"label": names.get(item["kind"], item["kind"]),
             "count": item["count"]}
            for item in rows.values("kind").annotate(count=Count("id"))
            .order_by("-count")]
        context["issues"] = summary.quality(period)
        context["completeness"] = summary.completeness(period)
        return context


class ReviewView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Отметка межсуточного замечания как разобранного."""

    def test_func(self) -> bool:
        """Разбирать замечания вправе тот, кто отвечает за данные."""
        return bool(getattr(self.request.user, "can_upload", False))

    def post(self, request, *args, **kwargs):
        """Переключить отметку «разобрано».

        Замечание при этом не удаляется: история того, что система
        замечала, остаётся.
        """
        check = get_object_or_404(CrossCheck, pk=kwargs["pk"])
        check.reviewed = not check.reviewed
        check.save(update_fields=["reviewed"])
        return redirect(_back(request, reverse("analytics:quality")))


def _back(request, fallback: str) -> str:
    """Адрес, с которого пришли, если он ведёт на этот же сайт.

    Заголовок ``Referer`` присылает браузер, и доверять ему как адресу
    перехода нельзя: иначе страница становится переадресатором на любой
    внешний адрес.

    Args:
        request: Запрос.
        fallback: Куда идти, если вернуться некуда.

    Returns:
        Безопасный адрес перехода.
    """
    referer = request.META.get("HTTP_REFERER", "")
    if url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()},
                                       require_https=request.is_secure()):
        return referer
    return fallback


def _period_from(request, default: str) -> periods.Period:
    """Период из адресной строки с умолчанием на последние сутки."""
    start = _parse_day(request.GET.get("start", ""))
    end = _parse_day(request.GET.get("end", ""))
    if start and end:
        return periods.custom(start, end)

    kind = request.GET.get("kind", default)
    if kind not in dict(periods.KINDS):
        kind = default
    anchor = _parse_day(request.GET.get("on", ""))
    if anchor is None:
        last = Report.objects.order_by("-date").first()
        anchor = last.date if last else timezone.localdate()
    return periods.period_of(kind, anchor)


class SummaryView(LoginRequiredMixin, TemplateView):
    """Сводка за неделю, месяц, квартал, полугодие, год или свой период."""

    template_name = "analytics/summary.html"

    def get_context_data(self, **kwargs) -> dict:
        """Собрать сводку и данные для графиков."""
        context = super().get_context_data(**kwargs)
        period = _period_from(self.request, "month")
        data = summary.build(period)

        context.update(data)
        context["kinds"] = periods.KINDS
        if period.kind != "custom":
            context["previous"] = periods.shift(period, -1)
            context["next"] = periods.shift(period, 1)
        # Данные графиков уходят в шаблон объектами: их сериализует
        # фильтр json_script, экранируя всё, что нужно экранировать.
        context["chart_daily"] = self._daily(data)
        context["chart_fields"] = self._rows(data["fields"], "field__name")
        context["chart_reasons"] = self._rows(data["reasons"], "reason__name")
        return context

    def _daily(self, data: dict) -> dict:
        """Ряд суточной добычи вместе с пропусками — для графика.

        Пропущенные сутки передаются как ``null``: Chart.js рисует
        на их месте разрыв, а не соединяет соседние столбцы. Молчаливое
        сглаживание дыры в данных — ровно то, чего здесь быть не должно.
        """
        by_day = {row["date"]: row for row in data["series"]}
        period = data["period"]
        last = min(period.end, data["completeness"]["last"] or period.end)

        labels, fact, plan = [], [], []
        day = period.start
        while day <= last:
            row = by_day.get(day)
            labels.append(day.strftime("%d.%m"))
            fact.append(row["production__closed_day"] if row else None)
            plan.append(row["production__plan_bp_day"] if row else None)
            day += timedelta(days=1)
        return {"labels": labels, "fact": fact, "plan": plan}

    def _rows(self, rows: list[dict], key: str) -> dict:
        """Названия и значения для горизонтальной диаграммы."""
        chosen = [row for row in rows if row.get("qo")][:12]
        return {"labels": [str(row[key]) for row in chosen],
                "values": [round(row["qo"], 1) for row in chosen]}
