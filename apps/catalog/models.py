# -*- coding: utf-8 -*-
"""Справочники: месторождения, скважины, объекты и подрядчики.

Названия в рапорте пишут по-разному: месторождение бывает
«Северо-Ошкотынское» в добыче и «С.Ошк» в бурении. Без справочника это
две разные сущности, и история по месторождению разваливается. Поэтому
у каждой записи есть нормализованный ключ, а у месторождений — ещё
и таблица синонимов.

Записи заводятся при загрузке рапорта по принципу «найти или создать»
и помечаются как требующие проверки: администратор просматривает
новичков и либо подтверждает, либо связывает с уже существующей записью.
"""
from __future__ import annotations

import re

from django.db import models

_SPACES = re.compile(r"\s+")
_PUNCT = re.compile(r"[«»\"'()\[\],;:.!?—–-]+")


def normalize(value: str) -> str:
    """Название к виду, пригодному для сравнения.

    Убирает регистр, лишние пробелы, знаки препинания и различие «е/ё» —
    ровно те расхождения, которые в рапорте встречаются постоянно
    и ничего не означают.

    Args:
        value: Название как оно записано в рапорте.

    Returns:
        Нормализованный ключ. Пустая строка, если значимых знаков нет.
    """
    if not value:
        return ""
    text = str(value).replace("­", "").strip().lower().replace("ё", "е")
    text = _PUNCT.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


class Reference(models.Model):
    """Общая часть справочников: название, ключ сравнения и признак проверки."""

    name = models.CharField("Название", max_length=200)
    key = models.CharField("Ключ сравнения", max_length=200, unique=True,
                           editable=False, db_index=True)
    is_active = models.BooleanField("Действующий", default=True)
    needs_review = models.BooleanField(
        "Требует проверки", default=True,
        help_text="Запись создана автоматически при загрузке рапорта "
                  "и ещё не подтверждена администратором.")
    note = models.CharField("Примечание", max_length=300, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ("name",)

    def __str__(self) -> str:
        """Название записи."""
        return self.name

    def save(self, *args, **kwargs) -> None:
        """Сохранить, пересчитав ключ сравнения по названию."""
        self.key = normalize(self.name)
        super().save(*args, **kwargs)


class Field(Reference):
    """Месторождение."""

    short_name = models.CharField("Короткое название", max_length=60,
                                  blank=True)

    class Meta(Reference.Meta):
        verbose_name = "месторождение"
        verbose_name_plural = "месторождения"


class FieldAlias(models.Model):
    """Ещё одно написание месторождения, встречающееся в рапорте.

    Заводится администратором, когда в рапорте обнаружилось сокращение:
    «С.Ошк» рядом с «Северо-Ошкотынским».
    """

    field = models.ForeignKey(Field, on_delete=models.CASCADE,
                              related_name="aliases",
                              verbose_name="Месторождение")
    name = models.CharField("Написание", max_length=200)
    key = models.CharField("Ключ сравнения", max_length=200, unique=True,
                           editable=False, db_index=True)

    class Meta:
        verbose_name = "синоним месторождения"
        verbose_name_plural = "синонимы месторождений"
        ordering = ("field__name", "name")

    def __str__(self) -> str:
        """Написание и месторождение, к которому оно относится."""
        return f"{self.name} → {self.field.name}"

    def save(self, *args, **kwargs) -> None:
        """Сохранить, пересчитав ключ сравнения."""
        self.key = normalize(self.name)
        super().save(*args, **kwargs)


class Well(models.Model):
    """Скважина.

    Номер уникален по компании: он и служит опознанием. Месторождение
    хранится связью — если в рапорте у известной скважины окажется другое
    месторождение, это повод для замечания, а не для новой записи:
    скважины между месторождениями не переезжают.
    """

    class Category(models.TextChoices):
        """Назначение скважины."""

        PRODUCTION = "production", "Добывающая"
        INJECTION = "injection", "Нагнетательная"
        OBSERVATION = "observation", "Наблюдательная"
        UNKNOWN = "unknown", "Не определено"

    number = models.CharField("Номер", max_length=40, unique=True,
                              db_index=True)
    field = models.ForeignKey(Field, on_delete=models.PROTECT,
                              related_name="wells",
                              verbose_name="Месторождение")
    category = models.CharField("Категория", max_length=20,
                                choices=Category.choices,
                                default=Category.UNKNOWN)
    is_active = models.BooleanField("Действующая", default=True)
    needs_review = models.BooleanField("Требует проверки", default=True)
    note = models.CharField("Примечание", max_length=300, blank=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "скважина"
        verbose_name_plural = "скважины"
        ordering = ("field__name", "number")

    def __str__(self) -> str:
        """Номер скважины с месторождением."""
        short = self.field.short_name or self.field.name
        return f"скв. {self.number} ({short})"


class InjectionObject(Reference):
    """Объект поддержания пластового давления: ЦПС, УПСВ-2 и другие."""

    class Meta(Reference.Meta):
        verbose_name = "объект ППД"
        verbose_name_plural = "объекты ППД"


class MeteringNode(Reference):
    """Узел учёта товарной нефти: ОУУН ЦПС, СИКН-438 и другие."""

    class Meta(Reference.Meta):
        verbose_name = "узел учёта"
        verbose_name_plural = "узлы учёта"


class Tank(Reference):
    """Резервуар товарного парка."""

    class Meta(Reference.Meta):
        verbose_name = "резервуар"
        verbose_name_plural = "резервуары"


class Contractor(Reference):
    """Подрядчик: буровой или сервисный."""

    class Meta(Reference.Meta):
        verbose_name = "подрядчик"
        verbose_name_plural = "подрядчики"


class DowntimeReason(Reference):
    """Причина простоя из готовой разбивки рапорта.

    Состав причин меняется: в августе 2026 «Сезонная эксплуатация»
    уступила место «Ожиданию СКО». Новые причины появляются в справочнике
    сами и ждут подтверждения администратора.
    """

    class Meta(Reference.Meta):
        verbose_name = "причина простоя"
        verbose_name_plural = "причины простоя"


class PowerObject(Reference):
    """Объект энергетики: площадка с запасом дизельного топлива."""

    class Meta(Reference.Meta):
        verbose_name = "объект энергетики"
        verbose_name_plural = "объекты энергетики"
