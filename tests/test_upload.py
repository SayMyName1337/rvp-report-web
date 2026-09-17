# -*- coding: utf-8 -*-
"""Проверки формы загрузки суточного рапорта.

Загружает рапорт начальник ЦИТУ, а не разработчик. Поэтому проверяется
не только то, что негодный файл отклонён, но и то, что человеку сказано
понятным языком, чем именно он негоден и что делать.
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User, ensure_roles
from apps.reports import forms
from apps.reports.forms import UploadForm
from apps.reports.models import Report, Upload

from .conftest import report_files

#: Начало книги Excel: это zip-архив.
ZIP_HEAD = b"PK\x03\x04"


def valid_zip() -> bytes:
    """Настоящий zip с внутренностями книги Excel, но без данных."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as book:
        book.writestr("xl/workbook.xml", "<workbook/>")
    return buffer.getvalue()


def upload_file(name: str = "рапорт.xlsx", content: bytes | None = None):
    """Загружаемый файл для формы."""
    return SimpleUploadedFile(name, valid_zip() if content is None
                              else content)


def check(name: str = "рапорт.xlsx", content: bytes | None = None,
          note: str = "") -> list[str]:
    """Ошибки формы по полю файла."""
    form = UploadForm(data={"note": note},
                      files={"file": upload_file(name, content)})
    form.is_valid()
    return [str(error) for error in form.errors.get("file", [])]


@pytest.fixture
def operator(db) -> User:
    """Работник промысла — он и загружает рапорты."""
    groups = ensure_roles()
    user = User.objects.create_user(username="citu", password="x" * 14,
                                    must_change_password=False)
    user.groups.add(groups[Role.FIELD.value])
    return user


@pytest.fixture
def viewer(db) -> User:
    """Руководство — рапорты не загружает."""
    groups = ensure_roles()
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    user.groups.add(groups[Role.MANAGEMENT.value])
    return user


# --- проверка файла ----------------------------------------------------------
@pytest.mark.django_db
def test_file_is_required() -> None:
    """Без файла форма не проходит."""
    form = UploadForm(data={}, files={})
    assert not form.is_valid()
    assert "Выберите файл" in str(form.errors["file"])


@pytest.mark.django_db
def test_old_excel_format_is_explained() -> None:
    """Про старый формат сказано, что с ним делать, а не «неверный файл»."""
    errors = check("рапорт.xls")
    assert errors
    assert "сохраните как" in errors[0].lower()


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["рапорт.pdf", "рапорт.docx", "рапорт"])
def test_other_extensions_are_rejected(name: str) -> None:
    """Файлы с другим расширением отклоняются с указанием имени."""
    errors = check(name)
    assert errors and name in errors[0]


@pytest.mark.django_db
def test_empty_file_is_rejected() -> None:
    """Пустой файл — признак недокачанного, так и сказано."""
    errors = check(content=b"")
    assert errors and "не докачал" in errors[0]


@pytest.mark.django_db
def test_too_large_file_is_rejected(settings) -> None:
    """Слишком большой файл отклоняется с указанием обычного размера."""
    settings.MAX_UPLOAD_SIZE_MB = 1
    errors = check(content=ZIP_HEAD + b"\x00" * (2 * 1024 * 1024))
    assert errors
    assert "300 КБ" in errors[0], "не сказано, сколько весит рапорт обычно"


@pytest.mark.django_db
def test_renamed_file_is_caught_by_signature() -> None:
    """Переименованный файл отсекается по содержимому, а не по имени."""
    errors = check(content=b"%PDF-1.4 and then some text")
    assert errors and "переименовали расширение" in errors[0]


@pytest.mark.django_db
def test_broken_archive_is_caught() -> None:
    """Повреждённая книга отклоняется до разбора."""
    errors = check(content=ZIP_HEAD + b"\x00" * 300)
    assert errors and "повреждена" in errors[0]


@pytest.mark.django_db
def test_zip_without_excel_parts_is_rejected() -> None:
    """Обычный архив книгой Excel не считается."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "не книга")
    errors = check(content=buffer.getvalue())
    assert errors and "не книга Excel" in errors[0]


@pytest.mark.django_db
def test_duplicate_upload_warns_without_note(operator: User) -> None:
    """Повтор ровно того же файла требует пояснения.

    Загрузка идемпотентна, поэтому повтор не опасен. Но чаще всего он
    означает, что человек ошибся файлом.
    """
    content = valid_zip()
    Upload.objects.create(
        uploaded_by=operator, original_name="рапорт.xlsx", size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        status=Upload.Status.LOADED)

    errors = check(content=content)
    assert errors and "уже загружали" in errors[0]


@pytest.mark.django_db
def test_duplicate_warning_names_the_local_time(operator: User) -> None:
    """Час загрузки называется по московскому времени, а не по Гринвичу.

    Время хранится в UTC. Без перевода сообщение называло час на три
    раньше, чем было на самом деле, — в системе, которая живёт вокруг
    совещания в девять утра, путать их нельзя.
    """
    content = valid_zip()
    upload = Upload.objects.create(
        uploaded_by=operator, original_name="рапорт.xlsx", size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        status=Upload.Status.LOADED)

    local = timezone.localtime(upload.uploaded_at)
    assert local.strftime("в %H:%M") in check(content=content)[0]
    assert local.strftime("%d.%m.%Y %H:%M") in str(upload)


@pytest.mark.django_db
def test_note_allows_deliberate_duplicate(operator: User) -> None:
    """С пояснением повтор разрешён: человек знает, что делает."""
    content = valid_zip()
    Upload.objects.create(
        uploaded_by=operator, original_name="рапорт.xlsx", size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        status=Upload.Status.LOADED)

    assert not check(content=content, note="загружаю намеренно")


# --- доступ ------------------------------------------------------------------
@pytest.mark.django_db
def test_viewer_cannot_open_upload_page(client, viewer: User) -> None:
    """Руководство рапорты не загружает."""
    client.force_login(viewer)
    assert client.get(reverse("reports:upload")).status_code == 403


@pytest.mark.django_db
def test_operator_can_open_upload_page(client, operator: User) -> None:
    """Работнику промысла страница доступна."""
    client.force_login(operator)
    response = client.get(reverse("reports:upload"))
    assert response.status_code == 200
    assert "Перетащите" in response.content.decode()


@pytest.mark.django_db
def test_upload_requires_login(client) -> None:
    """Посторонние загрузить рапорт не могут."""
    response = client.get(reverse("reports:upload"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


# --- полный путь -------------------------------------------------------------
@pytest.fixture
def sample() -> Path:
    """Настоящий суточный рапорт."""
    files = report_files()
    if not files:
        pytest.skip("нет рапортов для проверки")
    return files[0]


@pytest.mark.django_db
def test_real_report_is_loaded(client, operator: User, sample: Path) -> None:
    """Настоящий рапорт загружается и попадает в базу."""
    client.force_login(operator)
    with open(sample, "rb") as handle:
        response = client.post(reverse("reports:upload"),
                               {"file": SimpleUploadedFile(sample.name,
                                                           handle.read())})

    assert response.status_code == 302
    upload = Upload.objects.get()
    assert upload.status == Upload.Status.LOADED
    assert upload.is_current is True
    assert upload.report is not None
    assert Report.objects.count() == 1
    assert "Отчётная дата" in upload.log


@pytest.mark.django_db
def test_second_upload_reports_replacement(client, operator: User,
                                           sample: Path) -> None:
    """О замене данных за дату сказано прямо, а не молча."""
    client.force_login(operator)
    content = sample.read_bytes()

    for note in ("", "исправлены данные"):
        client.post(reverse("reports:upload"),
                    {"file": SimpleUploadedFile(sample.name, content),
                     "note": note})

    latest = Upload.objects.order_by("-uploaded_at").first()
    assert "заменены" in latest.log
    assert Upload.objects.filter(is_current=True).count() == 1, (
        "действующей должна остаться одна загрузка")
    assert Upload.objects.count() == 2, "история загрузок не сохранилась"


@pytest.mark.django_db
def test_unparsable_file_keeps_user_on_the_page(client,
                                                operator: User) -> None:
    """Книга, которая не рапорт, даёт ошибку на той же странице.

    Файл при этом сохраняется: по нему потом разбираются, что пошло не так.
    """
    client.force_login(operator)
    response = client.post(reverse("reports:upload"),
                           {"file": upload_file()})

    assert response.status_code == 200
    assert "разобрать его как суточный рапорт" in response.content.decode()

    upload = Upload.objects.get()
    assert upload.status == Upload.Status.FAILED
    assert Report.objects.count() == 0, "негодный файл попал в данные"


@pytest.mark.django_db
def test_result_page_shows_protocol(client, operator: User,
                                    sample: Path) -> None:
    """Протокол разбора виден после загрузки."""
    client.force_login(operator)
    with open(sample, "rb") as handle:
        client.post(reverse("reports:upload"),
                    {"file": SimpleUploadedFile(sample.name, handle.read())})

    upload = Upload.objects.get()
    page = client.get(reverse("reports:upload_result",
                              args=[upload.pk])).content.decode()
    assert "Отчётная дата" in page
    assert upload.original_name in page


@pytest.mark.django_db
def test_history_lists_uploads(client, operator: User, sample: Path) -> None:
    """История загрузок показывает, кто и когда загружал."""
    client.force_login(operator)
    with open(sample, "rb") as handle:
        client.post(reverse("reports:upload"),
                    {"file": SimpleUploadedFile(sample.name, handle.read())})

    page = client.get(reverse("reports:uploads")).content.decode()
    assert sample.name in page
    assert "действующая" in page


@pytest.mark.django_db
def test_book_that_unpacks_too_far_is_refused(operator, client) -> None:
    """Книга, неправдоподобно большая в развёрнутом виде, не принимается.

    Книга .xlsx — это zip-архив, и объём после распаковки ничем
    не связан с объёмом файла: хорошо сжимаемый XML разворачивается
    в сотни раз. Проверка читает оглавление архива, распаковки
    не требует, и потому не зависит от того, сколько памяти есть
    на узле.

    Предел занижается на время проверки: строить настоящую «бомбу»
    ради этого не нужно — проверяется сработает ли правило, а не
    выдержит ли узел.
    """
    files = report_files()
    if not files:
        pytest.skip("нет рапортов для проверки")

    client.force_login(operator)
    with mock.patch.object(forms, "MAX_UNPACKED_MB", 1):
        with open(files[0], "rb") as handle:
            response = client.post(
                reverse("reports:upload"),
                {"file": SimpleUploadedFile(files[0].name, handle.read())})

    assert response.status_code == 200, "файл приняли"
    assert "развёрнутом виде" in response.content.decode()


@pytest.mark.django_db
def test_ordinary_report_passes_the_unpacked_check(operator, client) -> None:
    """Обычный рапорт проверку размера в развёрнутом виде проходит."""
    files = report_files()
    if not files:
        pytest.skip("нет рапортов для проверки")

    with open(files[0], "rb") as handle:
        form = UploadForm(
            files={"file": SimpleUploadedFile(files[0].name, handle.read())},
            data={"note": "проверка"})

    assert form.is_valid(), form.errors
