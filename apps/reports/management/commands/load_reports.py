# -*- coding: utf-8 -*-
"""Массовая загрузка суточных рапортов из каталога.

Нужна для двух случаев: залить накопленный архив при вводе системы
в работу и перечитать его заново после того, как разбор улучшили.
"""
from __future__ import annotations

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.reports.loader import LoadError
from apps.reports.models import Upload
from apps.reports.services import process, register_upload


class Command(BaseCommand):
    """Загрузить все рапорты из каталога."""

    help = "Загрузить суточные рапорты .xlsx из каталога в базу"

    def add_arguments(self, parser) -> None:
        """Описать аргументы командной строки."""
        parser.add_argument("folder", help="каталог с файлами .xlsx")
        parser.add_argument("--user", default="",
                            help="имя пользователя, от чьего имени "
                                 "выполняется загрузка")
        parser.add_argument("--skip-loaded", action="store_true",
                            help="пропускать файлы, уже загруженные "
                                 "с той же контрольной суммой")

    def handle(self, *args, **options) -> None:
        """Разобрать и записать каждый файл каталога.

        Raises:
            CommandError: Если каталог пуст или не найден пользователь.
        """
        folder = Path(options["folder"])
        if not folder.is_dir():
            raise CommandError(f"каталог не найден: {folder}")

        files = sorted(path for path in folder.glob("*.xlsx")
                       if not path.name.startswith("~$"))
        if not files:
            raise CommandError(f"в каталоге нет файлов .xlsx: {folder}")

        user = self._user(options["user"])
        loaded = failed = skipped = 0

        for path in files:
            if options["skip_loaded"] and self._already_loaded(path):
                skipped += 1
                self.stdout.write(f"  пропущен  {path.name}")
                continue
            upload = register_upload(path, user)
            try:
                report = process(upload)
            except LoadError as error:
                failed += 1
                self.stdout.write(self.style.ERROR(
                    f"  ОШИБКА    {path.name}: {error}"))
                continue
            loaded += 1
            issues = report.issues.exclude(level="info").count()
            note = f", замечаний: {issues}" if issues else ""
            self.stdout.write(
                f"  загружен  {path.name} → {report.date:%d.%m.%Y}{note}")

        self.stdout.write("")
        summary = f"Загружено: {loaded}"
        if skipped:
            summary += f", пропущено: {skipped}"
        if failed:
            summary += f", с ошибками: {failed}"
        style = self.style.ERROR if failed else self.style.SUCCESS
        self.stdout.write(style(summary))

    def _user(self, username: str):
        """Пользователь, от чьего имени выполняется загрузка.

        Raises:
            CommandError: Если пользователь не найден и нет ни одного
                администратора.
        """
        model = get_user_model()
        if username:
            found = model.objects.filter(username=username).first()
            if found is None:
                raise CommandError(f"пользователь не найден: {username}")
            return found
        found = model.objects.filter(is_superuser=True).order_by("pk").first()
        if found is None:
            raise CommandError(
                "не найден ни один администратор — укажите --user")
        return found

    def _already_loaded(self, path: Path) -> bool:
        """Загружался ли уже файл с такой же контрольной суммой."""
        from apps.reports.loader import digest

        return Upload.objects.filter(sha256=digest(path),
                                     status=Upload.Status.LOADED).exists()
