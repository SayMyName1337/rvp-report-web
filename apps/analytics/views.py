# -*- coding: utf-8 -*-
"""Сводки за период и дашборд руководства."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.reports.models import Report

from . import periods, summary


def _parse_day(value: str) -> date | None:
    """Дата из строки вида ``2026-08-21`` или None."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


class DashboardView(LoginRequiredMixin, TemplateView):
    """Главная страница: последние сутки и ссылка на сводки."""

    template_name = "analytics/dashboard.html"

    def get_context_data(self, **kwargs) -> dict:
        """Собрать сведения о последних загруженных сутках."""
        context = super().get_context_data(**kwargs)
        latest = (Report.objects.select_related("production", "delivery",
                                                "power", "hse")
                  .order_by("-date").first())
        context["latest"] = latest
        context["total"] = Report.objects.count()
        if latest is not None:
            context["month"] = periods.period_of("month", latest.date)
        return context


class SummaryView(LoginRequiredMixin, TemplateView):
    """Сводка за неделю, месяц, квартал, полугодие, год или свой период."""

    template_name = "analytics/summary.html"

    def get_context_data(self, **kwargs) -> dict:
        """Собрать сводку и данные для графиков."""
        context = super().get_context_data(**kwargs)
        period = self._period()
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

    def _period(self) -> periods.Period:
        """Период из адресной строки.

        Умолчание — месяц последних загруженных суток: сводка за месяц,
        в котором ещё нет данных, никому не нужна.
        """
        start = _parse_day(self.request.GET.get("start", ""))
        end = _parse_day(self.request.GET.get("end", ""))
        if start and end:
            return periods.custom(start, end)

        kind = self.request.GET.get("kind", "month")
        if kind not in dict(periods.KINDS):
            kind = "month"
        anchor = _parse_day(self.request.GET.get("on", ""))
        if anchor is None:
            last = Report.objects.order_by("-date").first()
            anchor = last.date if last else date.today()
        return periods.period_of(kind, anchor)

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
