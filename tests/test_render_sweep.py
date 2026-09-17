# -*- coding: utf-8 -*-
"""Обход всех страниц с проверкой того, что на них не должно попадать.

Остальные проверки ищут на странице нужную строку и потому слепы
к лишнему: на заголовке сводки месяц простоял кусок служебной разметки
шаблона, а проверка сводки всё это время проходила — искомая строка
была на месте.

Здесь наоборот: страница открывается и проверяется на то, чего на ней
быть не может ни при каких данных.
"""
from __future__ import annotations

import re
from datetime import date

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User, ensure_roles
from apps.reports.loader import store
from apps.reports.models import Report

from .conftest import load, report_files

#: Начала конструкций шаблонизатора. Если такое дошло до страницы,
#: значит, разметка не понята и выведена текстом.
MARKERS = ("{%", "{{", "{#")

#: Содержимое <script> из проверки исключается: там лежат данные
#: графиков в формате JSON, и фигурные скобки в них законны.
SCRIPTS = re.compile(r"<script\b.*?</script>", re.DOTALL | re.IGNORECASE)


@pytest.fixture
def admin(db) -> User:
    """Администратор: ему открыты все страницы сразу."""
    groups = ensure_roles()
    user = User.objects.create_user(username="admin", password="x" * 14,
                                    must_change_password=False)
    user.groups.add(groups[Role.ADMIN.value])
    return user


@pytest.fixture
def loaded(db) -> Report:
    """Одни настоящие сутки в базе — чтобы страницы были непустыми."""
    files = report_files()
    if not files:
        pytest.skip("нет рапортов для проверки")
    return store(load(files[0]), [])


def _pages(report: Report) -> list[str]:
    """Адреса страниц, которые обходятся проверкой."""
    well = report.wells.first()
    pages = [
        reverse("analytics:dashboard"),
        reverse("analytics:quality"),
        reverse("reports:list"),
        reverse("reports:upload"),
        reverse("reports:uploads"),
        reverse("reports:wells"),
        reverse("reports:detail", args=[report.date]),
        reverse("reports:sources", args=[report.date]),
        reverse("layout:pending"),
        reverse("layout:journal"),
        reverse("decks:downloads"),
        reverse("guide:index"),
        reverse("accounts:password_change"),
    ]
    if well is not None:
        pages.append(reverse("reports:well", args=[well.well_id]))
    for kind in ("week", "month", "quarter", "half", "year"):
        pages.append(f"{reverse('analytics:summary')}?kind={kind}"
                     f"&on={report.date:%Y-%m-%d}")
    pages.append(f"{reverse('analytics:summary')}"
                 f"?start=2026-08-01&end=2026-08-31")
    # Периоды, которых ещё не было. Такие страницы открывают, просто
    # пролистав вперёд, и данных на них нет ни при каких условиях.
    for kind in ("month", "quarter", "half", "year"):
        pages.append(f"{reverse('analytics:summary')}?kind={kind}&on=2099-01-01")
    pages.append(f"{reverse('analytics:quality')}?kind=month&on=2099-01-01")
    return pages


def _visible(html: str) -> str:
    """Разметка без содержимого <script>."""
    return SCRIPTS.sub("", html)


@pytest.mark.django_db
def test_every_page_opens(client, admin: User, loaded: Report) -> None:
    """Каждая страница открывается без ошибки сервера."""
    client.force_login(admin)
    for url in _pages(loaded):
        response = client.get(url)
        assert response.status_code == 200, f"{url} → {response.status_code}"


@pytest.mark.django_db
def test_no_template_syntax_reaches_the_page(client, admin: User,
                                             loaded: Report) -> None:
    """Разметка шаблона не выходит на страницу текстом.

    Django не считает непонятую конструкцию ошибкой и выводит её как
    обычный текст. Так в заголовок сводки попал комментарий
    «После "из" существительное стоит в одной и той же форме…»:
    комментарий {# … #} Django понимает только однострочным.
    """
    client.force_login(admin)
    for url in _pages(loaded):
        page = _visible(client.get(url).content.decode())
        for marker in MARKERS:
            assert marker not in page, (
                f"{url}: на страницу вышла разметка шаблона «{marker}»")


@pytest.mark.django_db
def test_login_and_error_pages_are_clean(client) -> None:
    """Страницы, доступные без входа, проверяются отдельно.

    Их не видит ни одна проверка с пользователем, а показываются они
    чаще прочих: форму входа видят все и каждый день.
    """
    for url in (reverse("accounts:login"), "/такой-страницы-нет/"):
        page = _visible(client.get(url).content.decode())
        for marker in MARKERS:
            assert marker not in page, (
                f"{url}: на страницу вышла разметка шаблона «{marker}»")


@pytest.mark.django_db
def test_empty_base_pages_are_clean(client, admin: User) -> None:
    """Страницы пустой базы тоже обходятся.

    Ветки «данных нет» показываются реже прочих и потому реже
    проверяются, а видит их в первую очередь тот, кто только
    установил систему.
    """
    client.force_login(admin)
    for url in (reverse("analytics:dashboard"), reverse("reports:list"),
                reverse("reports:wells"), reverse("analytics:quality"),
                reverse("decks:downloads"), reverse("layout:pending"),
                f"{reverse('analytics:summary')}?kind=month&on=2026-08-01"):
        response = client.get(url)
        assert response.status_code == 200, f"{url} → {response.status_code}"
        page = _visible(response.content.decode())
        for marker in MARKERS:
            assert marker not in page, (
                f"{url}: на страницу вышла разметка шаблона «{marker}»")


@pytest.mark.django_db
def test_no_python_values_leak_into_the_text(client, admin: User,
                                             loaded: Report) -> None:
    """В текст страницы не попадают None и True из Python.

    Отсутствующее значение показывается прочерком, а признак — словом.
    Слово «None» на странице означает, что значение подставлено мимо
    фильтра.
    """
    client.force_login(admin)
    forbidden = re.compile(r">\s*(None|True|False)\s*<")
    for url in _pages(loaded):
        page = _visible(client.get(url).content.decode())
        found = forbidden.search(page)
        assert found is None, (
            f"{url}: в текст страницы попало «{found.group(1)}»")


@pytest.mark.django_db
def test_day_without_data_does_not_break_its_card(client, admin: User) -> None:
    """Карточка суток без показателей открывается, а не падает.

    Такие сутки появляются при загрузке рапорта, который разобрался
    лишь частично.
    """
    report = Report.objects.create(date=date(2026, 1, 15))
    client.force_login(admin)

    response = client.get(reverse("reports:detail", args=[report.date]))
    assert response.status_code == 200
    page = _visible(response.content.decode())
    for marker in MARKERS:
        assert marker not in page


#: Негодные значения параметров адреса. Такое приходит не от человека,
#: а от сканера безопасности или из ошибочной ссылки, но отвечать
#: на это система обязана страницей, а не ошибкой сервера.
JUNK = [
    "/reports/wells/?q=%00",
    "/reports/wells/?q=abc%00def",
    "/reports/wells/?q=" + "я" * 4000,
    "/reports/wells/?field=99999999999999999999999",
    "/reports/wells/?field=-1",
    "/reports/wells/?field=abc",
    "/summary/?kind=выдумка&on=2026-08-01",
    "/summary/?on=не-дата",
    "/summary/?start=2026-08-31&end=2026-08-01",
    "/summary/?start=0001-01-01&end=9999-12-31",
    "/quality/?start=2026-13-40&end=2026-08-01",
    "/summary/sheet/выдумка/?kind=month&on=2026-08-01",
]


@pytest.mark.django_db
@pytest.mark.parametrize("url", JUNK)
def test_junk_parameters_do_not_break_pages(client, admin: User,
                                            url: str) -> None:
    """Негодный параметр адреса даёт страницу, а не ошибку сервера.

    Параметры адреса приходят в представление, минуя форму, и потому
    минуя проверки Django. Нулевой байт в строке поиска по скважинам
    отвечал ошибкой сервера: PostgreSQL не принимает его в текстовом
    поле вовсе.
    """
    client.force_login(admin)
    response = client.get(url)

    assert response.status_code < 500, f"{url} → {response.status_code}"
    if hasattr(response, "streaming_content"):
        b"".join(response.streaming_content)
        response.close()
