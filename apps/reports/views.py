# -*- coding: utf-8 -*-
"""Страницы суточных рапортов: список, карточка суток и происхождение цифр."""
from __future__ import annotations

from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import (LoginRequiredMixin,
                                        UserPassesTestMixin)
from django.db.models import Count, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import DetailView, FormView, TemplateView

from apps.catalog.models import Field, Well

from . import services, wells as wells_service
from .forms import UploadForm
from .loader import LoadError
from .models import (DowntimeBreakdownDaily, FieldProductionDaily,
                     GroupEvent, LoadIssue, ProvenanceEntry, Report,
                     StockDaily, Upload, WellDaily, WellTotals)

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
        # Замечания считаются одним запросом, а не по запросу на сутки:
        # список растёт на 365 строк в год, и запрос на строку
        # превратился бы в тысячи запросов на одну страницу. По той же
        # причине `well_totals` берутся заранее — из них считаются
        # потери в столбце.
        reports = list(
            Report.objects
            .select_related("production", "delivery")
            .annotate(
                warnings=Count("issues",
                               filter=Q(issues__level=LoadIssue.Level.WARNING)),
                errors=Count("issues",
                             filter=Q(issues__level=LoadIssue.Level.ERROR)))
            .prefetch_related("well_totals", Prefetch(
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
                     "issues": {"warning": report.warnings,
                                "error": report.errors}})
        previous = report.date
    return rows


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


class WellListView(LoginRequiredMixin, TemplateView):
    """Скважины, упорядоченные по накопленным потерям.

    Суточный рапорт отвечает на вопрос «что стоит сегодня». Эта
    страница отвечает на другой: «какие скважины обходятся дороже
    всего за всё время наблюдения».
    """

    template_name = "reports/wells.html"

    def get_context_data(self, **kwargs) -> dict:
        """Собрать перечень скважин с отбором по месторождению и номеру."""
        context = super().get_context_data(**kwargs)
        search = self.request.GET.get("q", "").strip()
        field_id = self.request.GET.get("field", "")

        context["rows"] = wells_service.ranking(
            field_id=int(field_id) if field_id.isdigit() else None,
            search=search)
        context["fields"] = Field.objects.order_by("name")
        context["search"] = search
        context["field_id"] = field_id
        return context


class WellDetailView(LoginRequiredMixin, TemplateView):
    """История одной скважины: отрезки простоя, причины, ремонты."""

    template_name = "reports/well.html"

    def get_context_data(self, **kwargs) -> dict:
        """Собрать историю скважины."""
        context = super().get_context_data(**kwargs)
        well = get_object_or_404(
            Well.objects.select_related("field"), pk=self.kwargs["pk"])
        context.update(wells_service.history(well))
        return context


class UploadView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    """Загрузка суточного рапорта.

    Разбор выполняется прямо в запросе: он занимает несколько секунд,
    а загрузка происходит раз в сутки. Фоновая задача ради этого
    добавила бы опрос состояния и новый способ сломаться — «задача
    зависла в очереди», — ничего не дав взамен.
    """

    template_name = "reports/upload.html"
    form_class = UploadForm

    def test_func(self) -> bool:
        """Загружать рапорты вправе работник промысла и администратор."""
        return bool(getattr(self.request.user, "can_upload", False))

    def get_context_data(self, **kwargs) -> dict:
        """Добавить историю последних загрузок."""
        context = super().get_context_data(**kwargs)
        context["recent"] = (Upload.objects.select_related("uploaded_by",
                                                           "report")
                             .order_by("-uploaded_at")[:10])
        return context

    def form_valid(self, form: UploadForm):
        """Сохранить файл, разобрать его и записать данные.

        Ошибку разбора показываем на той же странице: человек должен
        видеть, что именно не вышло, а не получать пустой результат.
        """
        upload = services.accept(form.cleaned_data["file"], self.request.user,
                                 form.cleaned_data.get("note", ""))
        try:
            report = services.process(upload)
        except LoadError as error:
            form.add_error(
                "file",
                f"Файл сохранён, но разобрать его как суточный рапорт "
                f"не удалось: {error}")
            return self.form_invalid(form)

        messages.success(
            self.request,
            f"Рапорт за {report.date:%d.%m.%Y} загружен.")
        return redirect(reverse("reports:upload_result", args=[upload.pk]))


class UploadResultView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Протокол разбора загруженного файла."""

    template_name = "reports/upload_result.html"

    def test_func(self) -> bool:
        """Протокол доступен тем же, кто вправе загружать."""
        return bool(getattr(self.request.user, "can_upload", False))

    def get_context_data(self, **kwargs) -> dict:
        """Собрать сведения о загрузке и её итогах."""
        context = super().get_context_data(**kwargs)
        upload = get_object_or_404(
            Upload.objects.select_related("uploaded_by", "report"),
            pk=self.kwargs["pk"])
        context["upload"] = upload
        report = upload.report
        context["report"] = report
        if report is not None:
            context["issues"] = (report.issues
                                 .exclude(level=LoadIssue.Level.INFO)
                                 .order_by("level", "where"))
            context["gaps"] = report.gaps.all()
            context["cross"] = report.cross_checks.all()
        return context


class UploadHistoryView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """История загрузок: кто, когда и каким файлом."""

    template_name = "reports/uploads.html"

    def test_func(self) -> bool:
        """История доступна тем же, кто вправе загружать."""
        return bool(getattr(self.request.user, "can_upload", False))

    def get_context_data(self, **kwargs) -> dict:
        """Собрать последние загрузки."""
        context = super().get_context_data(**kwargs)
        context["rows"] = (Upload.objects
                           .select_related("uploaded_by", "report")
                           .order_by("-uploaded_at")[:200])
        return context
