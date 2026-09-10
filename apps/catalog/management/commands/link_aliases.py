# -*- coding: utf-8 -*-
"""Связывание сокращённых названий месторождений с полными.

Загрузка заводит незнакомое написание как новое месторождение и пишет
подсказку, если оно похоже на сокращение уже известного. Эта команда
показывает такие догадки и, по явному указанию, применяет их.

По умолчанию команда ничего не меняет: сначала посмотреть, потом
применить. Догадка может быть и неверной, решение остаётся за человеком.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Field
from apps.catalog.services import suggest_fields


class Command(BaseCommand):
    """Показать и применить догадки о сокращениях месторождений."""

    help = ("Связать сокращённые названия месторождений с полными. "
            "Без --apply только показывает, что будет сделано.")

    def add_arguments(self, parser) -> None:
        """Описать аргументы командной строки."""
        parser.add_argument("--apply", action="store_true",
                            help="применить догадки, а не только показать")

    def handle(self, *args, **options) -> None:
        """Найти сокращения, показать их и при необходимости применить."""
        pairs = self._pairs()
        if not pairs:
            self.stdout.write("Сокращений, требующих связывания, не найдено.")
            return

        self.stdout.write("Похоже на сокращения:")
        for short, candidates in pairs:
            names = ", ".join(f"«{item.name}»" for item in candidates)
            mark = "→" if len(candidates) == 1 else "?"
            self.stdout.write(f"  {mark} «{short.name}» {names} "
                              f"(скважин: {short.wells.count()})")

        clear = [(short, found[0]) for short, found in pairs if len(found) == 1]
        unclear = len(pairs) - len(clear)
        if unclear:
            self.stdout.write(self.style.WARNING(
                f"Неоднозначных догадок: {unclear} — их свяжите вручную "
                "в панели управления."))

        if not options["apply"]:
            self.stdout.write("")
            self.stdout.write("Ничего не изменено. Чтобы применить: "
                              "manage.py link_aliases --apply")
            return

        removed = self._apply(clear)
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Связано названий: {removed}"))
        self.stdout.write(
            "Суточные данные этих месторождений удалены вместе с записями. "
            "Загрузите рапорты заново: manage.py load_reports <каталог>")

    def _pairs(self) -> list[tuple[Field, list[Field]]]:
        """Месторождения, похожие на сокращения, и их кандидаты."""
        out = []
        for field in Field.objects.filter(needs_review=True).order_by("name"):
            candidates = [item for item in suggest_fields(field.name)
                          if item.pk != field.pk]
            if candidates:
                out.append((field, candidates))
        return out

    @transaction.atomic
    def _apply(self, pairs: list[tuple[Field, Field]]) -> int:
        """Записать синонимы и убрать месторождения-двойники.

        Суточные строки двойника удаляются: восстановить их правильно
        проще повторной загрузкой рапортов, чем сшивать записи вручную,
        а загрузка идемпотентна по дате.

        Args:
            pairs: Пары «сокращение, полное название».

        Returns:
            Сколько названий связано.
        """
        from apps.reports.models import (DrillingDaily, FieldProductionDaily,
                                         GroupEvent, RampUpDaily, StockDaily,
                                         WellDaily)

        for short, target in pairs:
            target.aliases.get_or_create(name=short.name)
            wells = list(short.wells.all())
            WellDaily.objects.filter(well__in=wells).delete()
            RampUpDaily.objects.filter(well__in=wells).delete()
            for model in (FieldProductionDaily, StockDaily, DrillingDaily,
                          GroupEvent):
                model.objects.filter(field=short).delete()
            short.wells.all().delete()
            short.delete()
        return len(pairs)
