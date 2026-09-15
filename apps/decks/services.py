# -*- coding: utf-8 -*-
"""Сборка презентации и перевод её в PDF.

Презентация собирается **из исходного файла рапорта**, а не из базы,
и это осознанное решение, а не экономия сил.

Во-первых, доклад идёт по слайдам, состав которых согласован
с начальником ЦИТУ, и расхождение между слайдом и рапортом недопустимо:
разбор одного и того же файла тем же кодом даёт ровно тот результат,
который проверяли.

Во-вторых, в описании происшествия рапорт содержит фамилии и
медицинские подробности — специальную категорию персональных данных.
На слайде они нужны, в базе их быть не должно. Собирая презентацию
напрямую из файла, мы не проводим эти сведения через хранилище:
в базу попадают только обезличенные признаки происшествия.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from django.core.files import File

from apps.layout.models import active_fixes
from apps.reports.models import Report, Upload
from rvp_report.excel.reader import ReportReader
from rvp_report.render.slides import build

from .models import Deck

#: Сколько ждать перевода в PDF, секунд.
PDF_TIMEOUT = 120

#: Где искать LibreOffice. На сервере он ставится в образ; на машине
#: разработки его может не быть, и это не ошибка — PDF просто недоступен.
SOFFICE_NAMES = ("soffice", "libreoffice")


def deck_name(report: Report) -> str:
    """Имя файла презентации по дате рапорта."""
    return f"Суточный рапорт {report.date:%Y-%m-%d}.pptx"


def current_deck(report: Report) -> Deck | None:
    """Действующая презентация суток или None, если её надо собрать.

    Действующей считается собранная из той же загрузки, что и данные:
    после повторной загрузки исправленного рапорта прежняя устаревает.

    Args:
        report: Сутки.

    Returns:
        Презентацию или None.
    """
    upload = report.uploads.filter(is_current=True).first()
    if upload is None:
        return None
    return Deck.objects.filter(report=report, upload=upload).first()


def build_deck(report: Report) -> Deck:
    """Собрать презентацию по суткам, если её ещё нет.

    Args:
        report: Сутки, за которые нужна презентация.

    Returns:
        Готовую презентацию.

    Raises:
        FileNotFoundError: Если исходный файл рапорта не сохранён.
    """
    existing = current_deck(report)
    if existing is not None and existing.file:
        return existing

    upload = report.uploads.filter(is_current=True).first()
    if upload is None or not upload.file:
        raise FileNotFoundError("исходный файл рапорта не сохранён")

    daily = ReportReader(upload.file.path, fixes=active_fixes()).read()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / deck_name(report)
        build(daily, str(path))
        deck = Deck(report=report, upload=upload)
        with open(path, "rb") as handle:
            deck.file.save(path.name, File(handle), save=False)
        deck.save()
    return deck


def soffice() -> str:
    """Путь к LibreOffice или пустая строка, если его нет.

    Returns:
        Имя исполняемого файла, пригодное для запуска.
    """
    for name in SOFFICE_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return ""


def to_pdf(source: Path) -> bytes:
    """Перевести презентацию в PDF средствами LibreOffice.

    Возвращается содержимое файла, а не путь к нему: временный каталог
    удаляется здесь же, при любом исходе. Иначе каждый перевод оставлял
    бы в системном каталоге временных файлов PDF с коммерческой тайной
    и персональными данными, за которыми никто не следит. Файл невелик
    (порядка мегабайта), а переводов бывает несколько в сутки.

    Args:
        source: Файл презентации.

    Returns:
        Содержимое созданного PDF.

    Raises:
        RuntimeError: Если LibreOffice недоступен или перевод не удался.
    """
    program = soffice()
    if not program:
        raise RuntimeError(
            "LibreOffice на сервере не установлен, перевод в PDF недоступен. "
            "Скачайте презентацию в формате PowerPoint.")

    with tempfile.TemporaryDirectory() as folder:
        try:
            subprocess.run(
                [program, "--headless", "--convert-to", "pdf",
                 "--outdir", folder, str(source)],
                check=True, capture_output=True, timeout=PDF_TIMEOUT)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("перевод в PDF занял слишком много времени") \
                from error
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"перевод в PDF не удался: {error.stderr[:200]!r}") from error

        result = Path(folder) / (source.stem + ".pdf")
        if not result.exists():
            raise RuntimeError("LibreOffice не создал файл PDF")
        return result.read_bytes()


def record_download(report: Report, kind: str, name: str, user) -> None:
    """Записать факт выдачи файла.

    Args:
        report: Сутки, к которым относится файл.
        kind: Что выдано — см. :class:`Download.Kind`.
        name: Имя выданного файла.
        user: Кому выдано.
    """
    from .models import Download

    Download.objects.create(report=report, kind=kind, name=name, user=user)


def stale_decks(upload: Upload) -> int:
    """Убрать презентации, собранные из устаревших загрузок этих суток.

    Args:
        upload: Действующая загрузка.

    Returns:
        Сколько презентаций удалено.
    """
    outdated = Deck.objects.filter(report=upload.report).exclude(upload=upload)
    count = outdated.count()
    outdated.delete()
    return count
