# -*- coding: utf-8 -*-
"""Страницы редактора разметки.

Отдельного раздела меню у редактора нет по замыслу: он появляется сам,
когда показатель не нашёлся, и только для этого показателя. Здесь три
страницы — перечень неподтверждённого, подтверждение одного показателя
и журнал поправок.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Max, Min
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import TemplateView, View

from apps.reports.models import LayoutGap, Report, Upload
from config.errors import Missing
from rvp_report.excel.sheet import Sheet

from . import services
from .models import LayoutFix


class OperatorRequired(LoginRequiredMixin, UserPassesTestMixin):
    """Доступ только тем, кто вправе загружать и править данные."""

    def test_func(self) -> bool:
        """Может ли пользователь менять разметку."""
        return bool(getattr(self.request.user, "can_upload", False))


class PendingView(OperatorRequired, TemplateView):
    """Показатели, которые ждут подтверждения оператором.

    Одна и та же поломка повторяется каждые сутки, поэтому список
    сгруппирован по показателю: одна карточка на проблему, а не
    тридцать одинаковых.
    """

    template_name = "layout/pending.html"

    def get_context_data(self, **kwargs) -> dict:
        """Собрать перечень неподтверждённых показателей."""
        context = super().get_context_data(**kwargs)
        context["groups"] = list(
            LayoutGap.objects.values("key", "label", "part", "message",
                                     "reference", "block")
            .annotate(days=Count("report", distinct=True),
                      since=Min("report__date"), until=Max("report__date"))
            .order_by("-days", "key"))
        context["fixes"] = LayoutFix.objects.filter(is_active=True).count()
        return context


class ConfirmView(OperatorRequired, TemplateView):
    """Подтверждение одного показателя: догадки и выбор ячейки вручную."""

    template_name = "layout/confirm.html"

    def get_context_data(self, **kwargs) -> dict:
        """Собрать кусок листа, догадки и сведения о показателе."""
        context = super().get_context_data(**kwargs)
        gap = self._gap()
        sheet, upload = self._sheet(gap.report)

        reference = self._reference(gap)
        row, col = reference if reference else (1, 1)
        block = self._block(gap)

        context["gap"] = gap
        context["upload"] = upload
        context["days"] = LayoutGap.objects.filter(key=gap.key).count()
        context["candidates"] = services.candidates(sheet, gap.label,
                                                    reference, block)
        context["fragment"] = services.fragment(sheet, row, col, reference)
        context["current"] = LayoutFix.objects.filter(key=gap.key,
                                                      is_active=True)
        return context

    def _gap(self) -> LayoutGap:
        """Пробел разметки по ключу и дате из адреса."""
        return get_object_or_404(
            LayoutGap.objects.select_related("report"),
            key=self.kwargs["key"], report__date=self.kwargs["day"])

    def _sheet(self, report: Report) -> tuple[Sheet, Upload]:
        """Лист рапорта из действующей загрузки.

        Raises:
            Missing: Если файл рапорта не сохранён или недоступен.
        """
        upload = report.uploads.filter(is_current=True).first()
        if upload is None or not upload.file:
            raise Missing("файл рапорта за эти сутки не сохранён")
        return services.open_report(upload.file.path), upload

    def _reference(self, gap: LayoutGap) -> tuple[int, int] | None:
        """Координаты эталонной ячейки или None."""
        from openpyxl.utils import coordinate_to_tuple

        if not gap.reference:
            return None
        try:
            return coordinate_to_tuple(gap.reference)
        except (ValueError, TypeError):
            return None

    #: В скольких строках вокруг прежнего места искать похожие подписи.
    #: Шире брать нельзя: подпись «Всего» есть почти в каждом разделе,
    #: и на пятнадцати строках к прогнозу сдачи уже примешивались «Всего»
    #: из расхода газа. Десять строк перекрывают любой блок рапорта.
    SEARCH_REACH = 10

    def _block(self, gap: LayoutGap) -> tuple[int, int] | None:
        """Строки, в которых имеет смысл искать похожие подписи."""
        reference = self._reference(gap)
        if reference is None:
            return None
        row = reference[0]
        return (max(1, row - self.SEARCH_REACH), row + self.SEARCH_REACH)


class ApplyView(OperatorRequired, View):
    """Запись поправки по указанной оператором ячейке."""

    def post(self, request, *args, **kwargs):
        """Вывести правило из выбранной клетки и сохранить его."""
        gap = get_object_or_404(
            LayoutGap.objects.select_related("report"),
            key=kwargs["key"], report__date=kwargs["day"])

        try:
            row = int(request.POST.get("row", ""))
            col = int(request.POST.get("col", ""))
        except ValueError:
            messages.error(request, "Не понял, какая клетка выбрана.")
            return redirect(self._back(gap))

        upload = gap.report.uploads.filter(is_current=True).first()
        if upload is None or not upload.file:
            messages.error(request, "Файл рапорта за эти сутки не сохранён.")
            return redirect(self._back(gap))

        sheet = services.open_report(upload.file.path)
        # Клетка обязана лежать в пределах листа. Номера приходят полем
        # формы, а не только щелчком по таблице: за пределами листа
        # openpyxl бросает исключение, а отрицательная строка ошибки
        # не вызывает — из неё выводится и запоминается правило вида
        # «E-1», которое не совпадёт уже никогда.
        if not (1 <= row <= sheet.max_row and 1 <= col <= sheet.max_col):
            messages.error(
                request, "Эта клетка вне листа рапорта: на листе "
                f"{sheet.max_row} строк и {sheet.max_col} столбцов. "
                "Выберите клетку в таблице.")
            return redirect(self._back(gap))

        block_top = max(1, row - 40)
        kind, value = services.derive_rule(sheet, row, col, gap.part,
                                           block_top)

        note = request.POST.get("note", "")[:1000]
        self._remember(gap.key, gap.label, kind, value, note, request.user)

        # Одна и та же подпись обычно держит несколько показателей: убрали
        # строку «Всего» — отвалились и прогноз сдачи, и откачка. Прямая
        # привязка к адресу так не переносится: адрес у каждого свой.
        together = 0
        if kind != LayoutFix.Kind.ADDRESS:
            for other in self._siblings(gap):
                self._remember(other, gap.label, kind, value, note,
                               request.user)
                together += 1

        if kind == LayoutFix.Kind.ADDRESS:
            messages.warning(
                request,
                f"Запомнил привязку к ячейке {value}. Подписи рядом нет, "
                "поэтому правило переживёт переименование, но не переживёт "
                "вставку строки — при следующей загрузке проверьте ещё раз.")
        else:
            also = (f" Та же подпись держала ещё {together} показател"
                    + ("ь." if together == 1 else "я.")) if together else ""
            messages.success(
                request,
                f"Запомнил: «{value}» — ещё одно название для «{gap.label}»."
                + also
                + " Загрузите рапорты заново, чтобы поправка применилась "
                  "к уже разобранным суткам.")
        return redirect(reverse("layout:pending"))

    def _remember(self, key: str, label: str, kind: str, value: str,
                  note: str, user) -> None:
        """Записать поправку, не создавая повторов.

        Args:
            key: Ключ показателя в схеме.
            label: Подпись, которую искали.
            kind: Вид правила.
            value: Новое название подписи или адрес ячейки.
            note: Пояснение оператора.
            user: Кто указал.
        """
        fix, created = LayoutFix.objects.get_or_create(
            key=key, kind=kind, value=value,
            defaults={"label": label, "created_by": user, "note": note})
        if not created and not fix.is_active:
            fix.is_active = True
            fix.save(update_fields=["is_active"])

    def _siblings(self, gap: LayoutGap) -> list[str]:
        """Другие показатели, отвалившиеся из-за той же подписи.

        Args:
            gap: Показатель, который сейчас подтверждают.

        Returns:
            Ключи показателей с той же подписью, разделом и частью.
        """
        return list(
            LayoutGap.objects
            .filter(label=gap.label, block=gap.block, part=gap.part)
            .exclude(key=gap.key)
            .values_list("key", flat=True).distinct())

    def _back(self, gap: LayoutGap) -> str:
        """Адрес страницы подтверждения этого показателя."""
        return reverse("layout:confirm", args=[gap.report.date, gap.key])


class JournalView(OperatorRequired, TemplateView):
    """Журнал поправок: что, кем и когда указано, и как это отменить."""

    template_name = "layout/journal.html"

    def get_context_data(self, **kwargs) -> dict:
        """Собрать все поправки, включая отменённые."""
        context = super().get_context_data(**kwargs)
        context["fixes"] = (LayoutFix.objects.select_related("created_by")
                            .order_by("-is_active", "-created_at"))
        return context


class ToggleView(OperatorRequired, View):
    """Включение и отмена поправки."""

    def post(self, request, *args, **kwargs):
        """Переключить действие поправки.

        Отмена возвращает разбор к прежнему поведению: показатель снова
        начнёт попадать в неподтверждённые.
        """
        fix = get_object_or_404(LayoutFix, pk=kwargs["pk"])
        fix.is_active = not fix.is_active
        fix.save(update_fields=["is_active"])
        messages.success(
            request,
            f"Поправка «{fix.value}» "
            + ("снова действует." if fix.is_active else "отменена."))
        return redirect(reverse("layout:journal"))
