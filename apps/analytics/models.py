# -*- coding: utf-8 -*-
"""Замечания, найденные сравнением суток с соседними."""
from __future__ import annotations

from django.db import models

from apps.reports.models import Report


class CrossCheck(models.Model):
    """Признак неправдоподобия, видимый только рядом с соседними сутками.

    Отличается от замечаний загрузки тем, что рапорт при этом
    непротиворечив сам себе: список сходится с итогом, итог — с фондом.
    Необычным выглядит только сопоставление с прошлыми сутками.

    Замечание не объявляет данные ошибочными. Оно говорит «посмотрите
    сюда», а решает человек.
    """

    class Kind(models.TextChoices):
        """Какое правило сработало."""

        JUMP = "jump", "Резкое изменение"
        LEVEL = "level", "Выход за привычный уровень"
        FROZEN = "frozen", "Значение не меняется"
        CONTRADICTION = "contradiction", "Показатели противоречат друг другу"

    class Severity(models.TextChoices):
        """Насколько замечание настойчиво."""

        INFO = "info", "К сведению"
        WARNING = "warning", "Предупреждение"

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="cross_checks",
                               verbose_name="Сутки")
    kind = models.CharField("Правило", max_length=20, choices=Kind.choices,
                            db_index=True)
    metric = models.CharField("Показатель", max_length=40)
    label = models.CharField("Название показателя", max_length=100)
    message = models.TextField("Замечание")
    value = models.FloatField("Значение", null=True, blank=True)
    baseline = models.FloatField("С чем сравнивали", null=True, blank=True)
    severity = models.CharField("Уровень", max_length=10,
                                choices=Severity.choices,
                                default=Severity.WARNING)
    reviewed = models.BooleanField(
        "Разобрано", default=False,
        help_text="Убирает замечание из списка требующих внимания. "
                  "Само замечание при этом сохраняется.")
    created_at = models.DateTimeField("Найдено", auto_now_add=True)

    class Meta:
        verbose_name = "межсуточное замечание"
        verbose_name_plural = "межсуточные замечания"
        ordering = ("-report__date", "kind", "metric")
        constraints = [models.UniqueConstraint(
            fields=("report", "kind", "metric"), name="unique_cross_check")]

    def __str__(self) -> str:
        """Дата и суть замечания."""
        return f"{self.report.date:%d.%m.%Y}: {self.message[:70]}"
