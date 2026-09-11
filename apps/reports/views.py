# -*- coding: utf-8 -*-
"""Страницы суточных рапортов: список, карточка суток и происхождение цифр."""
from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch, Sum
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, TemplateView

from .models import (DowntimeBreakdownDaily, FieldProductionDaily, GroupEvent,
                     LoadIssue, ProvenanceEntry, Report, StockDaily,
                     WellDaily, WellTotals)

#: Сколько скважин показывать в списках «наибольший вклад».
TOP_ROWS = 8


class ReportListView(LoginRequiredMixin, TemplateView):
    """Список загруженных суток.

    Показывает не только то, что загружено, но и **чего не хватает**:
    пропущенные сутки внутри периода искажают любую сводку, и увидеть
    их надо здесь, а не при разборе, почему месяц не сходится.
    """

    template_name = "reports/list.html"

    def get_context_data(self, **kwargs) -> dict:
        """Собрать перечень суток вперемешку с пропусками."""
        context = super().get_context_data(**kwargs)
        reports = list(
            Report.objects
            .select_related("production", "delivery")
            .prefetch_related(Prefetch(
                "uploads", queryset=Report.uploads.rel.related_model.objects
                .filter(is_current=True).select_related("uploaded_by")))
            .order_by("-date"))

        context["rows"] = _with_gaps(reports)
        context["total"] = len(reports)
        context["missing"] = sum(1 for row in context["rows"]
                                 if row["kind"] == "gap")
        context["needs_review"] = sum(
            1 for report in reports
            if report.status == Report.Status.NEEDS_REVIEW)
        return context


def _with_gaps(reports: list[Report]) -> list[dict]:
    """Перечень суток, в котором пропуски показаны отдельными строками.

    Args:
        reports: Сутки, отсортированные по убыванию даты.

    Returns:
        Строки для таблицы: либо сутки, либо пропуск с числом дней.
    """
    rows: list[dict] = []
    previous: date | None = None
    for report in reports:
        if previous is not None:
            gap = (previous - report.date).days - 1
            if gap > 0:
                rows.append({
                    "kind": "gap", "days": gap,
                    "since": report.date + timedelta(days=1),
                    "until": previous - timedelta(days=1)})
        rows.append({"kind": "report", "report": report,
                     "issues": _issue_counts(report)})
        previous = report.date
    return rows


def _issue_counts(report: Report) -> dict:
    """Сколько замечаний каждого уровня найдено за сутки."""
    counts = {"warning": 0, "error": 0}
    for issue in report.issues.exclude(level=LoadIssue.Level.INFO):
        counts[issue.level] = counts.get(issue.level, 0) + 1
    return counts


class ReportDetailView(LoginRequiredMixin, DetailView):
    """Карточка суток: те же разделы, что в докладе, но как страница."""

    template_name = "reports/detail.html"
    context_object_name = "report"

    def get_object(self, queryset=None) -> Report:
        """Сутки по дате из адреса."""
        return get_object_or_404(
            Report.objects.select_related("production", "delivery", "power",
                                          "hse"),
            date=self.kwargs["day"])

    def get_context_data(self, **kwargs) -> dict:
        """Собрать все разделы карточки."""
        context = super().get_context_data(**kwargs)
        report = self.object

        context["previous"] = (Report.objects.filter(date__lt=report.date)
                               .order_by("-date").first())
        context["next"] = (Report.objects.filter(date__gt=report.date)
                           .order_by("date").first())

        context["totals"] = {item.category: item
                             for item in report.well_totals.all()}
        context["losses"] = _losses(report)
        context["stock_total"] = report.stock.filter(is_total=True).first()

        context["fields"] = (FieldProductionDaily.objects
                             .filter(report=report)
                             .select_related("field")
                             .order_by("-qo"))
        context["fields_total"] = (context["fields"]
                                   .aggregate(s=Sum("qo"))["s"] or 0)

        context["breakdown"] = (DowntimeBreakdownDaily.objects
                                .filter(report=report)
                                .select_related("reason").order_by("-qo"))
        context["top_wells"] = (WellDaily.objects
                                .filter(report=report,
                                        category=WellDaily.Category.DOWNTIME)
                                .select_related("well", "well__field")
                                .order_by("-qo")[:TOP_ROWS])
        context["group_events"] = (GroupEvent.objects.filter(report=report)
                                   .order_by("-qo"))

        context["stock"] = (StockDaily.objects
                            .filter(report=report, is_total=False)
                            .select_related("field").order_by("-in_work"))
        context["injection"] = (report.injection.select_related("object")
                                .order_by("is_total", "-fact_day"))
        context["tanks"] = report.tanks.select_related("tank").all()
        context["quality"] = report.quality.select_related("node").all()
        context["gas"] = report.gas.all()
        context["diesel"] = report.diesel_stock.select_related("object").all()
        context["drilling"] = (report.drilling
                               .select_related("contractor", "field").all())
        context["pigging"] = report.pigging.all()
        context["ramp_up"] = (report.ramp_up
                              .select_related("well", "well__field").all())

        context["issues"] = (report.issues
                             .exclude(level=LoadIssue.Level.INFO)
                             .order_by("level", "where"))
        context["upload"] = report.uploads.filter(
            is_current=True).select_related("uploaded_by").first()
        context["cross_checks"] = report.cross_checks.all()
        return context


def _losses(report: Report) -> dict:
    """Потери добычи за сутки и их слагаемые.

    В рапорте такой цифры нет: это сумма трёх величин, каждая из которых
    в рапорте есть. Поэтому рядом всегда показываются слагаемые —
    величина расчётная и должна раскрываться.

    Args:
        report: Сутки.

    Returns:
        Слагаемые, итог и его долю в добыче.
    """
    totals = {item.category: (item.qo or 0.0)
              for item in report.well_totals.all()}
    parts = [
        ("Текущий простой", totals.get(WellTotals.Category.DOWNTIME, 0.0)),
        ("Бездействие", totals.get(WellTotals.Category.IDLE, 0.0)),
        ("Внутрисменные", totals.get(WellTotals.Category.VSP, 0.0)),
    ]
    total = sum(value for _name, value in parts)
    closed = getattr(report.production, "closed_day", None)
    return {"parts": parts, "total": total,
            "share": (total / closed * 100) if closed else None}


class ReportSourcesView(LoginRequiredMixin, TemplateView):
    """Откуда взялась каждая цифра.

    Требование доклада: любое число можно проверить по рапорту. Здесь
    показано происхождение каждого показателя — адрес ячейки, диапазон
    суммирования или формула расчёта.
    """

    template_name = "reports/sources.html"

    def get_context_data(self, **kwargs) -> dict:
        """Собрать журнал происхождения, разложенный по способам получения."""
        context = super().get_context_data(**kwargs)
        report = get_object_or_404(Report, date=self.kwargs["day"])
        entries = list(ProvenanceEntry.objects.filter(report=report)
                       .order_by("section", "label"))

        context["report"] = report
        context["groups"] = [
            (label, [item for item in entries if item.kind == kind])
            for kind, label in ProvenanceEntry.Kind.choices]
        context["derived"] = [
            item for item in entries
            if item.kind in (ProvenanceEntry.Kind.DERIVED,
                             ProvenanceEntry.Kind.COUNT)]
        context["total"] = len(entries)
        context["upload"] = report.uploads.filter(is_current=True).first()
        return context
