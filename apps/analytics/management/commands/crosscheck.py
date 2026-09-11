# -*- coding: utf-8 -*-
"""Пересчёт межсуточных проверок за отрезок дат."""
from __future__ import annotations

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.analytics.models import CrossCheck
from apps.analytics.services import recheck_range


class Command(BaseCommand):
    """Сверить сутки с соседними и записать замечания."""

    help = "Пересчитать межсуточные проверки за указанный отрезок дат"

    def add_arguments(self, parser) -> None:
        """Описать аргументы командной строки."""
        parser.add_argument("--from", dest="start", default="",
                            help="первая дата в виде 2026-08-01")
        parser.add_argument("--to", dest="end", default="",
                            help="последняя дата в виде 2026-08-31")

    def handle(self, *args, **options) -> None:
        """Выполнить пересчёт и показать, что найдено.

        Raises:
            CommandError: Если дата записана не в том виде.
        """
        start = self._day(options["start"])
        end = self._day(options["end"])
        days, total = recheck_range(start, end)

        self.stdout.write(f"Проверено суток: {days}")
        if not total:
            self.stdout.write(self.style.SUCCESS(
                "Ничего необычного по сравнению с соседними сутками."))
            return

        rows = (CrossCheck.objects.select_related("report")
                .filter(reviewed=False).order_by("report__date"))
        if start is not None:
            rows = rows.filter(report__date__gte=start)
        if end is not None:
            rows = rows.filter(report__date__lte=end)

        for item in rows:
            mark = "!" if item.severity == CrossCheck.Severity.WARNING else " "
            self.stdout.write(
                f" {mark} {item.report.date:%d.%m} {item.message}")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING(f"Найдено замечаний: {total}"))

    def _day(self, value: str):
        """Дата из строки или None.

        Raises:
            CommandError: Если строка не разбирается как дата.
        """
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as error:
            raise CommandError(
                f"дата должна быть вида 2026-08-01, а не «{value}»") from error
