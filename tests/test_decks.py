# -*- coding: utf-8 -*-
"""Проверки выдачи презентаций и защиты персональных данных."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from django.db import models
from django.urls import reverse

from apps.accounts.models import Role, User, ensure_roles
from apps.decks import services
from apps.decks.models import Deck, Download
from apps.reports.loader import read_file, store
from apps.reports.models import IncidentDaily, Report, Upload
from apps.reports.services import process, register_upload

from .conftest import load, report_files

#: Сутки, в которых происшествие записано с объединённым комментарием.
INCIDENT_DAY = "Суточный рапорт 23.08.26.xlsx"


def _find(name: str) -> Path | None:
    """Файл рапорта по имени или None, если рапортов нет."""
    for path in report_files():
        if path.name == name:
            return path
    return None


@pytest.fixture
def operator(db) -> User:
    """Работник промысла — ему доступен исходный файл."""
    groups = ensure_roles()
    user = User.objects.create_user(username="citu", password="x" * 14)
    user.groups.add(groups[Role.FIELD.value])
    return user


@pytest.fixture
def viewer(db) -> User:
    """Руководство — только просмотр и презентации."""
    groups = ensure_roles()
    user = User.objects.create_user(username="chief", password="x" * 14)
    user.groups.add(groups[Role.MANAGEMENT.value])
    return user


@pytest.fixture
def loaded(operator: User) -> Report:
    """Сутки, загруженные вместе с сохранённым исходным файлом."""
    files = report_files()
    if not files:
        pytest.skip("нет рапортов для проверки")
    path = _find(INCIDENT_DAY) or files[0]
    upload = register_upload(path, operator)
    daily, gaps = read_file(upload.file.path)
    report = store(daily, gaps, upload)
    return report


# --- персональные данные -----------------------------------------------------
def test_incident_model_has_no_free_text() -> None:
    """В происшествии не должно быть полей со свободным текстом.

    В рапорте за 23.08.2026 графа «Описание происшествия» содержит
    фамилию с инициалами и медицинские подробности — ту же специальную
    категорию персональных данных, что и текст здравпункта. В базе
    остаются только обезличенные признаки.
    """
    forbidden = {"description", "consequences", "comments", "text", "note"}
    names = {field.name for field in IncidentDaily._meta.get_fields()}
    assert not names & forbidden, (
        "в происшествие добавлено поле со свободным текстом: "
        + ", ".join(sorted(names & forbidden)))

    for field in IncidentDaily._meta.get_fields():
        if isinstance(field, models.TextField):
            raise AssertionError(
                f"поле «{field.name}» хранит произвольный текст — "
                "в происшествии таких быть не должно")


@pytest.mark.django_db
def test_incident_details_are_not_stored(loaded: Report) -> None:
    """Подробности происшествия не попадают в базу ни в каком виде."""
    for incident in loaded.incidents.all():
        for field in ("company", "field_text", "area", "kind"):
            value = getattr(incident, field)
            assert "обратил" not in value.lower(), (
                f"в поле «{field}» просочилось описание происшествия")


# --- разбор ------------------------------------------------------------------
def test_merged_comment_does_not_double_incidents() -> None:
    """Объединённый комментарий не должен удваивать число происшествий.

    В рапорте за 23.08.2026 комментарий объединён на две строки,
    и вторая из них считалась вторым происшествием: на слайде стояло
    «Происшествий: 2» там, где оно одно.
    """
    path = _find(INCIDENT_DAY)
    if path is None:
        pytest.skip("нет рапорта за 23.08.2026")
    daily = load(path)
    assert len(daily.hse.incidents) == 1


# --- сборка презентации ------------------------------------------------------
@pytest.mark.django_db
def test_deck_is_built_and_reused(loaded: Report) -> None:
    """Презентация собирается один раз и потом отдаётся готовой."""
    first = services.build_deck(loaded)
    assert first.file and first.file.size > 10_000

    second = services.build_deck(loaded)
    assert second.pk == first.pk, "презентацию пересобрали без нужды"
    assert Deck.objects.count() == 1


@pytest.mark.django_db
def test_deck_is_rebuilt_after_new_upload(loaded: Report,
                                          operator: User) -> None:
    """После повторной загрузки рапорта презентация собирается заново.

    Иначе за сутки с исправленными данными отдавалась бы прежняя.
    """
    services.build_deck(loaded)
    path = _find(INCIDENT_DAY) or report_files()[0]

    again = register_upload(path, operator)
    daily, gaps = read_file(again.file.path)
    report = store(daily, gaps, again)

    assert services.current_deck(report) is None, (
        "к новой загрузке подтянулась старая презентация")


@pytest.mark.django_db
def test_replacing_a_report_removes_the_old_presentation(
        loaded: Report, operator: User) -> None:
    """Исправление рапорта убирает прежнюю презентацию вместе с файлом.

    Она больше не соответствует данным и никогда не будет отдана,
    а файл без уборки остался бы в хранилище навсегда: по презентации
    на каждое исправление.
    """
    old = services.build_deck(loaded)
    old_path = Path(old.file.path)
    assert old_path.exists()

    path = _find(INCIDENT_DAY) or report_files()[0]
    again = register_upload(path, operator)
    process(again)

    assert not Deck.objects.filter(pk=old.pk).exists(), "запись осталась"
    assert not old_path.exists(), "файл презентации остался в хранилище"


@pytest.mark.django_db
def test_download_is_recorded(client, loaded: Report,
                              viewer: User) -> None:
    """Каждая выдача файла попадает в журнал."""
    client.force_login(viewer)
    response = client.get(reverse("decks:pptx", args=[loaded.date]))
    assert response.status_code == 200

    # Обращения к базе — до закрытия ответа: закрытие потокового ответа
    # посылает request_finished, и соединение с базой закрывается вместе
    # с ним, а в тесте это рвёт и саму проверочную транзакцию.
    record = Download.objects.get()
    assert record.user == viewer
    assert record.kind == Download.Kind.DECK
    assert record.report == loaded
    response.close()


@pytest.mark.django_db
def test_source_file_is_closed_to_viewers(client, loaded: Report,
                                          viewer: User) -> None:
    """Исходный рапорт руководству не выдаётся.

    В файле есть то, чего нет в базе: фамилии и медицинские
    подробности. Доступ к нему уже, чем к данным.
    """
    client.force_login(viewer)
    assert client.get(
        reverse("decks:source", args=[loaded.date])).status_code == 403


@pytest.mark.django_db
def test_source_file_is_open_to_operator(client, loaded: Report,
                                         operator: User) -> None:
    """Работник промысла может получить исходный файл."""
    client.force_login(operator)
    response = client.get(reverse("decks:source", args=[loaded.date]))
    assert response.status_code == 200
    assert Download.objects.filter(kind=Download.Kind.SOURCE).exists()
    response.close()


@pytest.mark.django_db
def test_missing_source_is_explained(client, viewer: User) -> None:
    """Без исходного файла программа объясняет, а не отдаёт пустоту."""
    report = Report.objects.create(date="2026-01-01")
    client.force_login(viewer)
    response = client.get(reverse("decks:pptx", args=[report.date]))
    assert response.status_code == 302
    assert Deck.objects.count() == 0


@pytest.mark.django_db
def test_pdf_absence_is_stated_plainly(client, loaded: Report,
                                       viewer: User) -> None:
    """Если LibreOffice нет, об этом говорится, а не отдаётся битый файл."""
    if services.soffice():
        pytest.skip("LibreOffice установлен — проверять нечего")
    client.force_login(viewer)
    response = client.get(reverse("decks:pdf", args=[loaded.date]))
    assert response.status_code == 302


@pytest.mark.django_db
def test_pdf_leaves_nothing_in_the_temporary_folder(loaded: Report, tmp_path,
                                                    monkeypatch) -> None:
    """Перевод в PDF не оставляет за собой временных файлов.

    В презентации есть и коммерческая тайна, и фамилии из описания
    происшествия. Забытый в системном каталоге PDF — это утечка,
    за которой никто не следит, поэтому каталог убирается при любом
    исходе, включая отсутствие LibreOffice.
    """
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    deck = services.build_deck(loaded)
    try:
        content = services.to_pdf(Path(deck.file.path))
    except RuntimeError:
        content = None                      # LibreOffice не установлен

    assert not list(tmp_path.iterdir()), "после перевода остался мусор"
    if content is not None:
        assert content.startswith(b"%PDF"), "вернулся не PDF"


@pytest.mark.django_db
def test_upload_without_file_does_not_break_deck(operator: User) -> None:
    """Сутки без сохранённого файла дают понятную ошибку, а не падение."""
    report = Report.objects.create(date="2026-02-02")
    Upload.objects.create(report=report, uploaded_by=operator,
                          original_name="нет.xlsx", sha256="c" * 64, size=1,
                          is_current=True)
    with pytest.raises(FileNotFoundError):
        services.build_deck(report)
