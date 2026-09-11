# -*- coding: utf-8 -*-
"""Приём файла рапорта: от загруженного файла до записи в базе.

Отделено от :mod:`apps.reports.loader`, который занимается только
перекладкой уже разобранного рапорта. Здесь — работа с файлом:
проверка, сохранение, вызов разбора и отметка результата в загрузке.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.files import File

from .loader import LoadError, digest, read_file, store
from .models import Report, Upload

#: Первые байты файла .xlsx: это zip-архив.
ZIP_SIGNATURE = b"PK\x03\x04"


def check_file(name: str, size: int, head: bytes) -> str:
    """Проверить файл до того, как он попадёт в обработку.

    Args:
        name: Имя файла.
        size: Размер в байтах.
        head: Первые байты файла.

    Returns:
        Текст ошибки или пустую строку, если файл пригоден.
    """
    if not name.lower().endswith(".xlsx"):
        return "Суточный рапорт — это файл .xlsx"
    limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if size > limit:
        return (f"Файл больше {settings.MAX_UPLOAD_SIZE_MB} МБ. "
                "Проверьте, что это суточный рапорт")
    if not size:
        return "Файл пустой"
    if not head.startswith(ZIP_SIGNATURE):
        return "Файл не похож на книгу Excel: не совпадает сигнатура"
    return ""


def accept(uploaded, user, note: str = "") -> Upload:
    """Принять файл, пришедший из формы загрузки.

    Args:
        uploaded: Загруженный файл.
        user: Кто загружает.
        note: Пояснение, если рапорт загружают повторно.

    Returns:
        Созданную запись загрузки с сохранённым файлом.
    """
    uploaded.seek(0)
    upload = Upload(uploaded_by=user, original_name=uploaded.name[:255],
                    sha256=digest(uploaded), size=uploaded.size,
                    status=Upload.Status.PARSING, log=note)
    uploaded.seek(0)
    upload.file.save(uploaded.name, uploaded, save=False)
    upload.save()
    return upload


def register_upload(path: Path, user, original_name: str = "") -> Upload:
    """Завести запись загрузки для файла с диска.

    Используется командой массовой загрузки архива. Файл копируется
    в хранилище приложения, чтобы его можно было перечитать после
    улучшения разбора.

    Args:
        path: Файл рапорта на диске.
        user: Кто загружает.
        original_name: Имя, под которым файл показывать.

    Returns:
        Созданную запись загрузки.
    """
    upload = Upload(uploaded_by=user, original_name=original_name or path.name,
                    sha256=digest(path), size=path.stat().st_size,
                    status=Upload.Status.PARSING)
    with open(path, "rb") as handle:
        upload.file.save(path.name, File(handle), save=False)
    upload.save()
    return upload


def process(upload: Upload) -> Report:
    """Разобрать файл загрузки и записать данные в базу.

    Args:
        upload: Запись загрузки с сохранённым файлом.

    Returns:
        Сутки с записанными данными.

    Raises:
        LoadError: Если файл не удалось прочитать как суточный рапорт.
    """
    upload.status = Upload.Status.PARSING
    upload.save(update_fields=["status"])
    try:
        daily, degraded = read_file(upload.file.path)
    except LoadError as error:
        upload.status = Upload.Status.FAILED
        upload.log = str(error)
        upload.save(update_fields=["status", "log"])
        raise

    # Замена данных за уже загруженные сутки — обычное дело: рапорт
    # присылают с исправлениями. Но сказать об этом нужно прямо.
    replaced = (Upload.objects
                .filter(report__date=daily.report_date, is_current=True)
                .exclude(pk=upload.pk)
                .select_related("uploaded_by").first())

    report = store(daily, degraded, upload)

    # Сверка с соседними сутками — уже после записи: ей нужна история.
    # Импорт здесь, а не наверху: раздел сводок сам обращается к рапортам.
    from apps.analytics.services import recheck

    recheck(report)

    upload.log = _summary(report, degraded, replaced, upload.log)
    upload.save(update_fields=["log"])
    return report


def _summary(report: Report, degraded: list, replaced=None,
             note: str = "") -> str:
    """Протокол разбора для страницы загрузки.

    Args:
        report: Записанные сутки.
        degraded: Показатели, взятые по эталонному адресу.
        replaced: Прежняя действующая загрузка за эту дату, если она была.
        note: Пояснение, оставленное при загрузке.

    Returns:
        Текст протокола.
    """
    lines = []
    if note:
        lines += [f"Пояснение: {note}", ""]
    if replaced is not None:
        who = (replaced.uploaded_by.short_name
               or replaced.uploaded_by.get_username())
        lines += [
            f"Данные за эти сутки заменены. Прежняя загрузка — "
            f"«{replaced.original_name}» от "
            f"{replaced.uploaded_at:%d.%m.%Y %H:%M}, {who}; "
            "она сохранена в истории.",
            ""]
    lines += [
        f"Отчётная дата: {report.date:%d.%m.%Y}",
        f"Скважин в списках: {report.wells.count()}",
        f"Месторождений: {report.field_production.count()}",
        f"Показателей с записанным происхождением: "
        f"{report.provenance.count()}",
        f"Замечаний к данным: {report.issues.count()}",
    ]
    if degraded:
        lines.append("")
        lines.append("Взято по эталонному адресу — требует подтверждения:")
        lines += [f"  • {item}" for item in degraded]
    return "\n".join(lines)
