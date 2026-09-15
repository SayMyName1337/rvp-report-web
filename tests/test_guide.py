# -*- coding: utf-8 -*-
"""Проверки страницы инструкции.

Инструкция лежит в репозитории рядом с кодом, чтобы не расходиться
с системой. Проверки следят за тем, чтобы она не разошлась молча:
каждая ссылка оглавления должна вести в существующий раздел, а всё,
о чём инструкция рассказывает, — существовать в системе.
"""
from __future__ import annotations

import re

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User, ensure_roles


@pytest.fixture
def viewer(db) -> User:
    """Руководство: инструкция нужна и ему."""
    groups = ensure_roles()
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    user.groups.add(groups[Role.MANAGEMENT.value])
    return user


@pytest.mark.django_db
def test_guide_opens(client, viewer: User) -> None:
    """Инструкция доступна любому, кто вошёл."""
    client.force_login(viewer)
    response = client.get(reverse("guide:index"))

    assert response.status_code == 200
    assert "Загрузка суточного рапорта" in response.content.decode()


@pytest.mark.django_db
def test_guide_requires_login(client) -> None:
    """Посторонним инструкция не показывается: в ней устройство системы."""
    response = client.get(reverse("guide:index"))

    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


@pytest.mark.django_db
def test_every_contents_link_leads_somewhere(client, viewer: User) -> None:
    """Каждая ссылка оглавления ведёт в существующий раздел.

    Разделы переименовываются, а оглавление правят не всегда.
    """
    client.force_login(viewer)
    page = client.get(reverse("guide:index")).content.decode()

    anchors = set(re.findall(r'<section class="card section" id="([^"]+)"',
                             page))
    links = set(re.findall(r'href="#([^"]+)"', page))

    assert links, "оглавление пустое"
    assert not links - anchors, f"ссылки в никуда: {sorted(links - anchors)}"
    assert not anchors - links, f"раздел вне оглавления: {sorted(anchors - links)}"


@pytest.mark.django_db
def test_guide_is_linked_from_every_page(client, viewer: User) -> None:
    """Кнопка «Инструкция» есть в меню, а не только по прямой ссылке."""
    client.force_login(viewer)
    page = client.get(reverse("analytics:dashboard")).content.decode()

    assert reverse("guide:index") in page


#: Формы обращения ко второму лицу. Руководство — сдаточный документ,
#: и изложение в нём безличное: «файл выбирается», «следует нажать».
SECOND_PERSON = re.compile(
    r"\b(вы|вам|вами|вас|ваш|ваша|ваше|ваши|вашего|вашей|вашему|вашим|"
    r"ваших|вашими|вашу)\b", re.IGNORECASE)

#: Цитаты интерфейсных сообщений в кавычках-ёлочках. Сообщения
#: приводятся дословно, иначе администратор не опознает их по рассказу
#: пользователя, — поэтому из проверки изложения они исключаются.
QUOTED = re.compile(r"«[^»]*»")


@pytest.mark.django_db
def test_guide_is_written_impersonally(client, viewer: User) -> None:
    """В руководстве нет обращения к читателю на «вы».

    Требование к сдаточной документации: официальное техническое
    изложение. Цитаты сообщений интерфейса из проверки исключены —
    они приводятся так, как выводятся на экран.
    """
    client.force_login(viewer)
    page = client.get(reverse("guide:index")).content.decode()

    text = QUOTED.sub("", re.sub(r"<[^>]+>", " ", page))
    found = SECOND_PERSON.findall(text)

    assert not found, f"обращение на «вы»: {sorted(set(found))}"


@pytest.mark.django_db
def test_guide_does_not_promise_what_was_removed(client,
                                                 viewer: User) -> None:
    """Инструкция не обещает того, чего в системе нет.

    Очередь фоновых задач убрана; если инструкция начнёт про неё
    рассказывать, проверка об этом скажет.
    """
    client.force_login(viewer)
    page = client.get(reverse("guide:index")).content.decode().lower()

    for gone in ("очередь задач", "qcluster", "django-q"):
        assert gone not in page, f"инструкция обещает убранное: {gone}"
