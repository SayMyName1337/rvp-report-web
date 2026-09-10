# -*- coding: utf-8 -*-
"""Доступ к страницам: анонимных пользователей в системе быть не должно."""
from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User, ensure_roles

#: Страницы, которые обязаны требовать входа.
PROTECTED = ["analytics:dashboard", "reports:list"]


@pytest.mark.django_db
@pytest.mark.parametrize("name", PROTECTED)
def test_anonymous_is_sent_to_login(client, name: str) -> None:
    """Неаутентифицированного посетителя перенаправляет на вход."""
    response = client.get(reverse(name))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


@pytest.mark.django_db
@pytest.mark.parametrize("name", PROTECTED)
def test_authenticated_sees_page(client, name: str) -> None:
    """Вошедший пользователь получает страницу."""
    user = User.objects.create_user(username="tester", password="x" * 14)
    client.force_login(user)
    assert client.get(reverse(name)).status_code == 200


@pytest.mark.django_db
def test_upload_right_belongs_to_field_role() -> None:
    """Загружать рапорты может работник промысла, но не руководство."""
    groups = ensure_roles()

    viewer = User.objects.create_user(username="chief", password="x" * 14)
    viewer.groups.add(groups[Role.MANAGEMENT.value])
    assert viewer.can_upload is False

    operator = User.objects.create_user(username="citu", password="x" * 14)
    operator.groups.add(groups[Role.FIELD.value])
    assert operator.can_upload is True

    admin = User.objects.create_user(username="admin", password="x" * 14)
    admin.groups.add(groups[Role.ADMIN.value])
    assert admin.can_upload is True, "администратор может всё"


@pytest.mark.django_db
def test_new_user_must_change_password() -> None:
    """Выданный администратором пароль подлежит смене при первом входе."""
    user = User.objects.create_user(username="newcomer", password="x" * 14)
    assert user.must_change_password is True


@pytest.mark.django_db
def test_short_name_is_built_from_parts() -> None:
    """Фамилия и инициалы собираются из имеющихся частей ФИО."""
    user = User.objects.create_user(
        username="ivanov", password="x" * 14, last_name="Иванов",
        first_name="Иван", patronymic="Иванович")
    assert user.short_name == "Иванов И. И."
    assert user.full_name == "Иванов Иван Иванович"
