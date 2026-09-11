# -*- coding: utf-8 -*-
"""Собранные презентации и учёт их выдачи."""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.reports.models import Report, Upload


class Deck(models.Model):
    """Презентация, собранная по суточному рапорту.

    Хранится, чтобы не пересобирать одно и то же: за одни сутки её
    скачивают несколько человек. Привязана к загрузке, из которой
    собрана, — если рапорт прислали с исправлениями и данные заменили,
    прежняя презентация перестаёт быть действующей и собирается заново.
    """

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="decks", verbose_name="Сутки")
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE,
                               related_name="decks",
                               verbose_name="Из какой загрузки")
    file = models.FileField("Файл презентации", upload_to="decks/%Y/%m")
    built_at = models.DateTimeField("Собрана", auto_now_add=True)

    class Meta:
        verbose_name = "презентация"
        verbose_name_plural = "презентации"
        ordering = ("-built_at",)
        constraints = [models.UniqueConstraint(
            fields=("upload",), name="unique_deck_per_upload")]

    def __str__(self) -> str:
        """Дата рапорта, по которому собрана презентация."""
        return f"Презентация за {self.report.date:%d.%m.%Y}"


class Download(models.Model):
    """Запись о выдаче файла.

    Презентации и исходные рапорты содержат коммерческую тайну, поэтому
    отдаются не веб-сервером напрямую, а представлением с проверкой прав
    и записью сюда. Из интерфейса эти записи не удаляются.
    """

    class Kind(models.TextChoices):
        """Что именно скачали."""

        DECK = "deck", "Презентация"
        SOURCE = "source", "Исходный рапорт"

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="downloads", verbose_name="Сутки")
    kind = models.CharField("Что скачано", max_length=10,
                            choices=Kind.choices)
    name = models.CharField("Имя файла", max_length=255)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.PROTECT,
                             related_name="downloads", verbose_name="Кто")
    at = models.DateTimeField("Когда", auto_now_add=True)

    class Meta:
        verbose_name = "выдача файла"
        verbose_name_plural = "выдачи файлов"
        ordering = ("-at",)

    def __str__(self) -> str:
        """Кто, что и когда скачал."""
        return f"{self.user} — {self.get_kind_display()} {self.name}"
