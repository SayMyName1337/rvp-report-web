# -*- coding: utf-8 -*-
"""Поправки к разметке рапорта, сделанные оператором.

Рапорт собирают вручную, и его вёрстку меняют: за август 2026 подписи
поехали дважды. Чтобы каждая такая правка не упиралась в разработчика,
оператор может показать нужную ячейку сам — а система выводит из этого
правило и запоминает его.

Ключевое решение: поправка записывается **синонимом**, а не заменой.
Схема продолжает искать своё название и только потом пробует то, что
указал оператор. Отсюда три следствия: старые файлы не ломаются,
правила не нужно версионировать по датам, и поправка не может испортить
то, что и так находилось.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from rvp_report.excel.spec import Fix


class LayoutFix(models.Model):
    """Одно указание оператора: под каким ещё именем искать показатель."""

    class Kind(models.TextChoices):
        """Каким способом опознаётся ячейка."""

        ROW = "row", "Ещё одно название строки"
        COL = "col", "Ещё одно название столбца"
        ADDRESS = "address", "Прямая привязка к ячейке"

    key = models.CharField(
        "Ключ показателя", max_length=100, db_index=True,
        help_text="Как показатель называется в схеме разбора, "
                  "например forecast_total или stock.in_work.")
    label = models.CharField(
        "Искали подпись", max_length=200,
        help_text="Название, которое схема не смогла найти в файле.")
    kind = models.CharField("Способ", max_length=10, choices=Kind.choices,
                            default=Kind.ROW)
    value = models.CharField(
        "Указано оператором", max_length=200,
        help_text="Новое название подписи либо адрес ячейки вида D564.")

    note = models.TextField("Пояснение", blank=True)
    is_active = models.BooleanField(
        "Действует", default=True,
        help_text="Снимите, чтобы отменить поправку: разбор вернётся "
                  "к прежнему поведению.")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                   on_delete=models.PROTECT,
                                   related_name="layout_fixes",
                                   verbose_name="Кто указал")
    created_at = models.DateTimeField("Когда", auto_now_add=True)

    class Meta:
        verbose_name = "поправка к разметке"
        verbose_name_plural = "поправки к разметке"
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(
            fields=("key", "kind", "value"), name="unique_layout_fix")]

    def __str__(self) -> str:
        """Показатель и то, что для него указали."""
        return f"{self.key}: {self.get_kind_display().lower()} «{self.value}»"

    @property
    def is_address(self) -> bool:
        """Привязана ли поправка к адресу, а не к подписи.

        Привязка к адресу переживает переименование, но не переживает
        вставку строки, поэтому считается временной.
        """
        return self.kind == self.Kind.ADDRESS


def active_fixes() -> dict[str, Fix]:
    """Действующие поправки в виде, понятном движку разбора.

    Поправки одного показателя собираются вместе: подпись могли менять
    не один раз, и каждое из прежних названий должно продолжать
    работать — иначе рапорт за прошлый месяц перестанет разбираться.

    Returns:
        Соответствие «ключ показателя — поправка».
    """
    rows: dict[str, dict] = {}
    for item in LayoutFix.objects.filter(is_active=True).order_by("created_at"):
        entry = rows.setdefault(item.key, {"row": [], "col": [], "addr": ""})
        if item.kind == LayoutFix.Kind.ROW:
            entry["row"].append(item.value)
        elif item.kind == LayoutFix.Kind.COL:
            entry["col"].append(item.value)
        else:
            entry["addr"] = item.value
    return {key: Fix(row_aliases=tuple(entry["row"]),
                     col_aliases=tuple(entry["col"]),
                     address=entry["addr"])
            for key, entry in rows.items()}
