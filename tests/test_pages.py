# -*- coding: utf-8 -*-
"""Проверки страниц суточных рапортов."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.reports.loader import store
from apps.reports.models import Report
from apps.reports.templatetags.rvp import num, plural, share, signed

from .conftest import load, report_files


@pytest.fixture
def viewer(client) -> User:
    """Вошедший пользователь."""
    user = User.objects.create_user(username="chief", password="x" * 14,
                                    must_change_password=False)
    client.force_login(user)
    return user


@pytest.fixture
def loaded(db) -> Report:
    """Одни сутки, записанные в базу."""
    files = report_files()
    if not files:
        pytest.skip("нет рапортов для проверки")
    return store(load(files[0]), [])


# --- форматирование ----------------------------------------------------------
@pytest.mark.parametrize("value,digits,expected", [
    (8351.8, 1, "8 351,8"),
    (1092.18648, 3, "1 092,186"),
    (0, 0, "0"),
    (None, 0, "—"),
    ("", 1, "—"),
])
def test_numbers_use_russian_notation(value, digits, expected: str) -> None:
    """Разряды через пробел, дробная часть через запятую."""
    assert num(value, digits).replace(" ", " ") == expected


@pytest.mark.parametrize("value,expected", [
    (38.3, "+38,3"),
    (-201.0, "−201,0"),
    (0, "+0,0"),
    (None, "—"),
])
def test_deviations_carry_their_sign(value, expected: str) -> None:
    """Минус выводится знаком, а не дефисом: в столбце цифр дефис теряется."""
    assert signed(value, 1).replace(" ", " ") == expected


def test_share_of_zero_total_is_a_dash() -> None:
    """Доля от нуля — не ноль процентов, а отсутствие значения."""
    assert share(10, 0) == "—"
    assert share(None, 100) == "—"


@pytest.mark.parametrize("count,expected", [
    (1, "сутки"), (2, "суток"), (4, "суток"), (5, "суток"),
    (11, "суток"), (12, "суток"), (14, "суток"),
    (21, "сутки"), (22, "суток"), (31, "сутки"), (0, "суток"),
])
def test_word_agrees_with_the_number(count: int, expected: str) -> None:
    """Существительное согласуется с числом.

    Встроенный фильтр ``pluralize`` рассчитан на два варианта и при
    трёх молча возвращал пустую строку: на страницах выходило
    «Всего в базе 33 .» — слово со счётом пропадало вовсе.
    """
    assert plural(count, "сутки,суток,суток") == expected


def test_word_form_survives_bad_input() -> None:
    """Неожиданное значение не роняет страницу."""
    assert plural(None, "сутки,суток,суток") == "суток"
    assert plural("", "сутки,суток,суток") == "суток"
    assert plural(3, "сутки,суток") == "", "принято неверное число форм"


# --- страницы ----------------------------------------------------------------
@pytest.mark.django_db
def test_list_shows_loaded_days(client, viewer, loaded: Report) -> None:
    """Список показывает загруженные сутки."""
    response = client.get(reverse("reports:list"))
    assert response.status_code == 200
    assert loaded.date.strftime("%d.%m.%Y") in response.content.decode()


@pytest.mark.django_db
def test_list_marks_gaps_between_days(client, viewer, loaded: Report) -> None:
    """Пропущенные сутки показываются отдельной строкой.

    Без этого сводка за период считалась бы по неполному месяцу
    незаметно для читателя.
    """
    Report.objects.create(date=loaded.date + timedelta(days=4))
    page = client.get(reverse("reports:list")).content.decode()
    assert "Нет данных: 3" in page


@pytest.mark.django_db
def test_detail_shows_losses_with_their_parts(client, viewer,
                                              loaded: Report) -> None:
    """Потери — величина расчётная и раскрывается слагаемыми."""
    page = client.get(
        reverse("reports:detail", args=[loaded.date])).content.decode()
    assert "величина расчётная" in page
    assert "Текущий простой" in page
    assert "Бездействие" in page
    assert "Внутрисменные" in page


@pytest.mark.django_db
def test_detail_has_link_to_sources(client, viewer, loaded: Report) -> None:
    """С карточки суток можно перейти к происхождению цифр."""
    page = client.get(
        reverse("reports:detail", args=[loaded.date])).content.decode()
    assert reverse("reports:sources", args=[loaded.date]) in page


@pytest.mark.django_db
def test_sources_page_lists_every_metric(client, viewer,
                                         loaded: Report) -> None:
    """Происхождение показано для каждого показателя.

    Требование доклада: любое число проверяется по рапорту.
    """
    response = client.get(reverse("reports:sources", args=[loaded.date]))
    assert response.status_code == 200
    page = response.content.decode()
    assert f"Всего показателей: {loaded.provenance.count()}" in page
    for entry in loaded.provenance.all()[:5]:
        assert entry.origin in page


@pytest.mark.django_db
def test_unknown_day_gives_404(client, viewer) -> None:
    """Несуществующие сутки не должны выдавать пустую страницу."""
    missing = date(2000, 1, 1)
    assert client.get(
        reverse("reports:detail", args=[missing])).status_code == 404


@pytest.mark.django_db
def test_pages_require_login(client, loaded: Report) -> None:
    """Карточка суток и происхождение цифр закрыты от посторонних."""
    for name in ("reports:detail", "reports:sources"):
        response = client.get(reverse(name, args=[loaded.date]))
        assert response.status_code == 302
        assert reverse("accounts:login") in response.url


@pytest.mark.django_db
def test_detail_query_count_is_bounded(client, viewer, loaded: Report,
                                       django_assert_max_num_queries) -> None:
    """Карточка не должна ходить в базу за каждой строкой таблицы.

    Разделов на странице полтора десятка, и без предварительной выборки
    связанных записей число запросов росло бы вместе с числом скважин.
    """
    with django_assert_max_num_queries(40):
        client.get(reverse("reports:detail", args=[loaded.date]))


def test_sample_files_exist() -> None:
    """Напоминание: проверки страниц идут на настоящих рапортах."""
    files: list[Path] = report_files()
    if not files:
        pytest.skip("каталог с рапортами не задан")
    assert files[0].suffix == ".xlsx"


@pytest.mark.django_db
def test_day_without_fund_data_shows_a_dash_not_zero(client, viewer) -> None:
    """Сутки без блока фонда показывают прочерк, а не нулевые потери.

    Ноль утверждает, что потерь не было; отсутствие строк говорит лишь
    о том, что данных нет. Путать эти два состояния нельзя.
    """
    report = Report.objects.create(date=date(2026, 3, 3))

    page = client.get(reverse("reports:detail", args=[report.date]))
    assert page.status_code == 200
    text = page.content.decode()
    assert "складывать нечего" in text
    assert "= 0,000 т/сут" not in text
