# -*- coding: utf-8 -*-
"""Проверки страниц ошибок.

Страницу ошибки видит не разработчик, а начальник ЦИТУ или главный
инженер, и обычно в неудачную минуту. Поэтому проверяется не только код
ответа, но и то, что на странице написано по-русски, что именно
случилось и что делать дальше.
"""
from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role, User, ensure_roles
from config.errors import Missing, not_found


@pytest.fixture
def viewer(db) -> User:
    """Руководство: смотрит сводки, но ничего не загружает."""
    groups = ensure_roles()
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    position="Главный инженер")
    user.groups.add(groups[Role.MANAGEMENT.value])
    return user


# --- 404 ---------------------------------------------------------------------
@pytest.mark.django_db
def test_unknown_address_gives_russian_page(client) -> None:
    """Несуществующий адрес отдаёт свою страницу, а не строку Django."""
    response = client.get("/такого-раздела-нет/")
    page = response.content.decode()

    assert response.status_code == 404
    assert "Такой страницы нет" in page
    assert "Not Found" not in page


@pytest.mark.django_db
def test_reason_is_shown_when_written_for_a_human(rf) -> None:
    """Пояснение, написанное для пользователя, попадает на страницу.

    В коде оно пишется со строчной буквы — как часть сообщения
    об ошибке; на странице это отдельное предложение, поэтому
    первая буква заглавная.
    """
    request = rf.get("/decks/2026-08-15/source/")
    request.user = AnonymousUser()

    response = not_found(request, Missing("файл рапорта за эти сутки "
                                          "не сохранён"))

    assert response.status_code == 404
    assert "Файл рапорта за эти сутки не сохранён." in response.content.decode()


@pytest.mark.django_db
def test_service_message_is_not_shown(rf) -> None:
    """Служебный текст Django на страницу не выводится.

    `get_object_or_404` подставляет английское сообщение с именем
    модели — пользователю оно ничего не говорит и выдаёт устройство
    базы.
    """
    request = rf.get("/reports/2026-08-15/")
    request.user = AnonymousUser()

    response = not_found(request,
                         Http404("No Report matches the given query."))
    page = response.content.decode()

    assert "No Report" not in page
    assert "Такой страницы нет" in page


@pytest.mark.django_db
@pytest.mark.parametrize("day", ["2026-13-40", "2026-02-31", "2026-00-10"])
def test_impossible_date_is_not_found(client, day: str) -> None:
    """Несуществующая дата в адресе — это «не найдено», а не сбой.

    Выражение в адресе считает цифры и пропускает такие даты дальше;
    раньше они доходили до запроса к базе и оборачивались ошибкой
    приложения.
    """
    response = client.get(f"/reports/{day}/")

    assert response.status_code == 404


# --- 403 ---------------------------------------------------------------------
@pytest.mark.django_db
def test_forbidden_page_explains_rights(client, viewer: User) -> None:
    """Отказ в доступе объясняет, что права назначены по должности."""
    client.force_login(viewer)
    response = client.get(reverse("reports:upload"))
    page = response.content.decode()

    assert response.status_code == 403
    assert "должности" in page
    assert "Главный инженер" in page, "не сказано, под кем выполнен вход"
    assert "Forbidden" not in page


@pytest.mark.django_db
def test_csrf_failure_page_is_about_the_session(db) -> None:
    """Отказ по метке формы объясняется истёкшим сеансом.

    Обычный случай — форма загрузки, простоявшая открытой с вечера.
    """
    client = Client(enforce_csrf_checks=True)
    response = client.post(reverse("accounts:login"),
                           {"username": "citu", "password": "x" * 14})
    page = response.content.decode()

    assert response.status_code == 403
    assert "Сеанс истёк" in page
    assert "CSRF" not in page


# --- 500 ---------------------------------------------------------------------
def test_server_error_page_needs_no_context() -> None:
    """Страница сбоя рисуется без запроса и без контекста.

    Django отдаёт её именно так. Шаблон, которому нужен `request`
    или процессоры контекста, сломался бы ровно в тот момент,
    когда он нужен.
    """
    page = render_to_string("500.html")

    assert "Сбой в приложении" in page
    assert "Данные не испорчены" in page


def test_server_error_page_does_not_depend_on_static() -> None:
    """Страница сбоя не тянет ни стилей, ни картинок со стороны.

    Если сбой в самой раздаче статики, страница об этом должна
    отрисоваться всё равно.
    """
    page = render_to_string("500.html")

    assert "/static/" not in page
    assert "<img" not in page
