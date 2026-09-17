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
    user = User.objects.create_user(username="tester", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)
    assert client.get(reverse(name)).status_code == 200


# --- обязательная смена выданного пароля -------------------------------------
@pytest.mark.django_db
@pytest.mark.parametrize("name", PROTECTED + ["reports:upload", "guide:index"])
def test_issued_password_blocks_the_rest_of_the_system(client,
                                                       name: str) -> None:
    """С невозмещённым выданным паролем дальше формы смены не пускают.

    Пароль назначает администратор и передаёт работнику, то есть
    какое-то время он известен не только владельцу учётной записи.
    Работа под ним не должна продолжаться.
    """
    user = User.objects.create_user(username="newcomer", password="x" * 14)
    assert user.must_change_password is True
    client.force_login(user)

    response = client.get(reverse(name))

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_change")


@pytest.mark.django_db
def test_password_change_and_logout_stay_reachable(client) -> None:
    """Сама форма смены и выход доступны, иначе пользователь заперт."""
    user = User.objects.create_user(username="newcomer", password="x" * 14)
    client.force_login(user)

    assert client.get(reverse("accounts:password_change")).status_code == 200
    assert client.post(reverse("accounts:logout")).status_code == 302


@pytest.mark.django_db
def test_requirement_is_lifted_after_the_change(client) -> None:
    """После смены пароля система открывается обычным порядком."""
    user = User.objects.create_user(username="newcomer", password="x" * 14)
    client.force_login(user)

    response = client.post(reverse("accounts:password_change"), {
        "old_password": "x" * 14,
        "new_password1": "Сложный-Пароль-2026",
        "new_password2": "Сложный-Пароль-2026",
    })

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.must_change_password is False
    assert client.get(reverse("analytics:dashboard")).status_code == 200


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


# --- сплошная проверка закрытости ---------------------------------------------
#: Образцы для частей адреса. Конкретные значения неважны: проверяется
#: не содержимое страницы, а то, пускает ли она без входа.
SAMPLES = {"day": "2026-08-01", "pk": "1", "key": "k", "fmt": "pdf"}


def _addresses() -> list[str]:
    """Все адреса приложения, кроме панели управления.

    Панель управления закрывает Django собственными средствами
    и проверяется отдельно.
    """
    from django.urls import get_resolver

    def walk(resolver, prefix=""):
        for item in resolver.url_patterns:
            if hasattr(item, "url_patterns"):
                yield from walk(item, prefix + str(item.pattern))
            else:
                yield prefix + str(item.pattern)

    found = []
    for raw in walk(get_resolver()):
        if raw.startswith("admin/"):
            continue
        url = "/" + raw
        for name, value in SAMPLES.items():
            for form in (f"<{name}>", f"<int:{name}>", f"<str:{name}>",
                         f"<day:{name}>"):
                url = url.replace(form, value)
        if "<" in url or "(" in url:
            continue
        found.append(url)
    return found


@pytest.mark.django_db
@pytest.mark.parametrize("url", _addresses())
def test_no_page_opens_without_login(client, url: str) -> None:
    """Ни один адрес приложения не отвечает содержимым без входа.

    Проверка идёт по списку адресов, а не по списку известных страниц:
    представление, добавленное без `LoginRequiredMixin`, иначе осталось
    бы незамеченным до первой утечки.

    Исключения: форма входа и выход из системы.
    """
    if url in (reverse("accounts:login"), reverse("accounts:logout")):
        pytest.skip("страница входа и выход закрытыми быть не могут")

    response = client.get(url)
    if hasattr(response, "streaming_content"):
        b"".join(response.streaming_content)
        response.close()

    assert response.status_code == 302, f"{url} открылся без входа"
    assert reverse("accounts:login") in response.headers.get("Location", ""), (
        f"{url} увёл не на форму входа")
