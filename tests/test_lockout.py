# -*- coding: utf-8 -*-
"""Проверки защиты от перебора паролей.

Система стоит на узле с внешним адресом, вход в неё — по паролю,
и единственное, что отделяет чужого от коммерческой тайны, — стойкость
этого пароля. Перебор обязан упираться в блокировку.

Вторая половина проверок — о том, чтобы защита не била по своим.
Все работники предприятия выходят в сеть через один внешний адрес,
а доклад главному инженеру идёт в 09:00: блокировка, закрывающая
вход всему отделу из-за чужой опечатки, или блокировка, которую
посторонний может навесить на начальника ЦИТУ перед докладом, —
это отказ системы, а не её защита.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from axes.models import AccessAttempt, AccessFailureLog
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from config.ip import client_address

#: Верный пароль проверочной учётной записи.
PASSWORD = "Правильный-Пароль-2026"

#: Адреса, с которых приходят обращения в проверках.
HERE = "10.10.0.7"
ELSEWHERE = "10.10.0.8"


@pytest.fixture
def person(db) -> User:
    """Учётная запись с известным паролем."""
    return User.objects.create_user(username="citu", password=PASSWORD,
                                    must_change_password=False)


@pytest.fixture(autouse=True)
def clean_attempts(db):
    """Счётчики попыток не должны перетекать между проверками."""
    AccessAttempt.objects.all().delete()
    AccessFailureLog.objects.all().delete()


def _try(client, username: str, password: str, address: str = HERE):
    """Одна попытка входа с указанного адреса."""
    return client.post(reverse("accounts:login"),
                       {"username": username, "password": password},
                       REMOTE_ADDR=address)


def _fail(client, times: int, username: str = "citu",
          address: str = HERE) -> None:
    """Исчерпать указанное число попыток неверным паролем."""
    for _ in range(times):
        _try(client, username, "неверный-пароль", address)


# --- блокировка --------------------------------------------------------------
@pytest.mark.django_db
def test_wrong_password_alone_does_not_lock(client, person: User) -> None:
    """Пока попытки не исчерпаны, верный пароль пускает как обычно."""
    _fail(client, settings.AXES_FAILURE_LIMIT - 1)

    response = _try(client, "citu", PASSWORD)
    assert response.status_code == 302, "верный пароль перестал пускать"


@pytest.mark.django_db
def test_login_closes_after_the_limit(client, person: User) -> None:
    """После исчерпания попыток вход закрывается."""
    _fail(client, settings.AXES_FAILURE_LIMIT)

    response = _try(client, "citu", "неверный-пароль")
    assert response.status_code == settings.AXES_HTTP_RESPONSE_CODE
    assert "Вход временно закрыт" in response.content.decode()


@pytest.mark.django_db
def test_correct_password_does_not_open_a_locked_account(client,
                                                         person: User) -> None:
    """Во время блокировки не пускает и верный пароль.

    Иначе блокировка не мешала бы перебору: подобранный пароль
    сработал бы с первой же попытки после неё.
    """
    _fail(client, settings.AXES_FAILURE_LIMIT)

    response = _try(client, "citu", PASSWORD)
    assert response.status_code == settings.AXES_HTTP_RESPONSE_CODE
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_lockout_page_names_the_term_and_the_way_out(client,
                                                     person: User) -> None:
    """Страница блокировки называет срок и путь решения.

    Ответ без этого неотличим от неисправности системы, а до доклада
    может оставаться десять минут.
    """
    _fail(client, settings.AXES_FAILURE_LIMIT)
    page = _try(client, "citu", PASSWORD).content.decode()

    assert str(settings.AXES_COOLOFF_MINUTES) in page, "не назван срок"
    assert "минут" in page, "срок указан без единицы измерения"
    assert "администратор" in page.lower(), "не назван путь решения"


@pytest.mark.django_db
def test_successful_login_resets_the_counter(client, person: User) -> None:
    """Удачный вход обнуляет счётчик неудачных попыток.

    Иначе редкие опечатки за неделю сложились бы в блокировку
    на ровном месте.
    """
    _fail(client, settings.AXES_FAILURE_LIMIT - 1)
    assert _try(client, "citu", PASSWORD).status_code == 302

    client.logout()
    _fail(client, settings.AXES_FAILURE_LIMIT - 1)
    assert _try(client, "citu", PASSWORD).status_code == 302, (
        "счётчик не обнулился после удачного входа")


@pytest.mark.django_db
def test_login_opens_after_the_cooloff(client, person: User) -> None:
    """По истечении срока вход открывается сам."""
    _fail(client, settings.AXES_FAILURE_LIMIT)
    assert _try(client, "citu", PASSWORD).status_code != 302

    gone = timezone.now() - settings.AXES_COOLOFF_TIME - timedelta(minutes=1)
    AccessAttempt.objects.update(attempt_time=gone)

    assert _try(client, "citu", PASSWORD).status_code == 302, (
        "вход не открылся после истечения срока блокировки")


@pytest.mark.django_db
def test_attempts_during_lockout_do_not_extend_it(client,
                                                  person: User) -> None:
    """Попытки во время блокировки её не продлевают.

    Срок снятия обязан быть предсказуем: человек, который в 08:50
    несколько раз нажал «Войти», должен знать, когда сможет войти.
    """
    _fail(client, settings.AXES_FAILURE_LIMIT)
    locked_at = AccessAttempt.objects.get().attempt_time

    _fail(client, 3)

    assert AccessAttempt.objects.get().attempt_time == locked_at, (
        "попытка во время блокировки сдвинула срок её снятия")


# --- блокировка не бьёт по своим ---------------------------------------------
@pytest.mark.django_db
def test_one_mistake_does_not_close_the_office(client, person: User) -> None:
    """Чужая опечатка не закрывает вход другим с того же адреса.

    Предприятие выходит в сеть через один внешний адрес: блокировка
    по адресу оставила бы без системы весь отдел.
    """
    User.objects.create_user(username="chief", password=PASSWORD,
                             must_change_password=False)
    _fail(client, settings.AXES_FAILURE_LIMIT, username="citu")

    response = _try(client, "chief", PASSWORD)
    assert response.status_code == 302, (
        "блокировка одной записи закрыла вход другой с того же адреса")


@pytest.mark.django_db
def test_an_outsider_cannot_lock_out_the_chief(client, person: User) -> None:
    """Посторонний не закрывает вход работнику, подбирая пароль извне.

    Блокировка по одному имени позволяла бы кому угодно закрыть вход
    начальнику ЦИТУ перед докладом, пять раз ошибившись за него.
    """
    _fail(client, settings.AXES_FAILURE_LIMIT, address=ELSEWHERE)

    response = _try(client, "citu", PASSWORD, address=HERE)
    assert response.status_code == 302, (
        "перебор с чужого адреса закрыл вход работнику с его рабочего места")


# --- адрес обратившегося -----------------------------------------------------
@pytest.mark.django_db
def test_attempts_are_recorded_with_the_address(client, person: User) -> None:
    """Неудачные попытки записываются вместе с адресом.

    Счётчика мало: администратору нужна картина — когда и откуда
    подбирали пароль.
    """
    _fail(client, 2, address=ELSEWHERE)

    assert AccessFailureLog.objects.count() == 2
    assert AccessAttempt.objects.get().ip_address == ELSEWHERE


@override_settings(TRUST_PROXY_CLIENT_IP=True)
def test_address_behind_a_proxy_comes_from_the_header(rf) -> None:
    """За обратным прокси адрес берётся из заголовка.

    Без этого адресом каждого обращения был бы адрес контейнера
    прокси — один и тот же для всех, и учёт попыток по адресу
    потерял бы смысл.
    """
    request = rf.get("/", REMOTE_ADDR="172.18.0.4",
                     HTTP_X_REAL_IP="203.0.113.9")

    assert client_address(request) == "203.0.113.9"


@override_settings(TRUST_PROXY_CLIENT_IP=False)
def test_address_without_a_proxy_ignores_the_header(rf) -> None:
    """Без прокси заголовок не читается.

    Иначе обратившийся назначал бы себе адрес сам и уходил бы
    от блокировки, меняя заголовок после каждой попытки.
    """
    request = rf.get("/", REMOTE_ADDR="203.0.113.9",
                     HTTP_X_REAL_IP="10.0.0.1")

    assert client_address(request) == "203.0.113.9"
