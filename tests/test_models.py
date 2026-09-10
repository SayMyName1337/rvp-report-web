# -*- coding: utf-8 -*-
"""Проверки модели данных, не зависящие от наличия рапортов."""
from __future__ import annotations

import pytest
from django.db import models

from apps.accounts.models import Role, ensure_roles
from apps.catalog.models import Field, normalize
from apps.catalog.services import find_field, get_field, get_well
from apps.reports.models import HseDaily


def test_hse_stores_only_counts() -> None:
    """В сутках ПБиОТ не должно быть ни одного текстового поля.

    Текст обращений в здравпункт — специальная категория персональных
    данных по 152-ФЗ. Если он попадёт в базу, система станет ИСПДн
    со всеми требованиями к аттестации, и проект остановится
    на согласовании. Ограничение закреплено здесь, чтобы его нельзя
    было нарушить по невнимательности при доработке модели.
    """
    allowed = {"id", "report"}
    for field in HseDaily._meta.get_fields():
        if field.name in allowed:
            continue
        assert isinstance(field, models.PositiveIntegerField), (
            f"поле «{field.name}» хранит не количество: в сутках ПБиОТ "
            "нельзя держать ничего, кроме чисел")


@pytest.mark.parametrize("written,expected", [
    ("Северо-Ошкотынское", "североошкотынское"),
    ("  Северо—Ошкотынское  ", "североошкотынское"),
    ("СЕВЕРО-ОШКОТЫНСКОЕ", "североошкотынское"),
    ("Тёдинское", "тединское"),
    ("ЦПС РВС-5000", "цпсрвс5000"),
    ("", ""),
])
def test_normalize_ignores_meaningless_differences(written: str,
                                                   expected: str) -> None:
    """Регистр, пробелы, дефисы и «ё» не должны различать названия."""
    assert normalize(written) == expected


@pytest.mark.parametrize("one,other", [
    ("Верхне-Колвинское", "Верхнеколвинское"),
    ("ЦПС РВС-5000", "ЦПС РВС 5000"),
    ("Северо-Хоседаюское", "СЕВЕРО–ХОСЕДАЮСКОЕ"),
])
def test_spelling_variants_are_the_same_name(one: str, other: str) -> None:
    """Написания, различающиеся только оформлением, — одно название.

    «Верхне-Колвинское» и «Верхнеколвинское» встретились в одном
    и том же августовском рапорте.
    """
    assert normalize(one) == normalize(other)


@pytest.mark.django_db
def test_field_found_by_alias() -> None:
    """Сокращённое написание месторождения должно вести к той же записи.

    В одном и том же рапорте месторождение называется
    «Северо-Ошкотынское» в добыче и «С.Ошк» в бурении.
    """
    field = Field.objects.create(name="Северо-Ошкотынское",
                                 short_name="С.Ошк")
    field.aliases.create(name="С.Ошк")

    assert find_field("Северо-Ошкотынское") == field
    assert find_field("с.ошк") == field
    assert find_field("СЕВЕРО–ОШКОТЫНСКОЕ") == field
    assert find_field("Висовое") is None


@pytest.mark.django_db
def test_new_field_is_created_for_review() -> None:
    """Незнакомое месторождение заводится, но помечается для проверки."""
    created = get_field("Новое месторождение")
    assert created is not None
    assert created.needs_review is True
    assert get_field("новое  месторождение") == created


@pytest.mark.django_db
def test_well_is_identified_by_field_and_number() -> None:
    """Один и тот же номер на разных месторождениях — разные скважины.

    В августе 2026 скважина №2 нашлась одновременно на Висовом,
    Сюрхаратинском и Северо-Хоседаюском.
    """
    visovoe = Field.objects.create(name="Висовое")
    surh = Field.objects.create(name="Сюрхаратинское")

    first, warning = get_well("2", visovoe)
    assert first is not None and not warning

    second, warning = get_well("2", surh)
    assert second is not None and not warning
    assert second != first, "скважины на разных месторождениях — разные"

    again, _warning = get_well("2", visovoe)
    assert again == first, "повторный вызов не должен создавать двойника"


@pytest.mark.django_db
def test_well_without_field_is_not_created() -> None:
    """Без месторождения скважину опознать нельзя."""
    well, warning = get_well("2", None)
    assert well is None
    assert "не указано месторождение" in warning


@pytest.mark.django_db
@pytest.mark.parametrize("short,full", [
    ("Сюрх", "Сюрхаратинское"),
    ("С.Ошк", "Северо-Ошкотынское"),
    ("ЗХ", "Западно-Хоседаюское"),
    ("СХ", "Северо-Хоседаюское"),
    ("Вис", "Висовое"),
])
def test_abbreviations_are_recognised(short: str, full: str) -> None:
    """Сокращения из блока бурения должны опознаваться как подсказка."""
    from apps.catalog.services import looks_like_abbreviation

    assert looks_like_abbreviation(short, full)


@pytest.mark.parametrize("short,full", [
    ("СХ", "Северо-Сихорейское"),
    ("Висовое", "Висовое"),
    ("Сюрхаратинское", "Сюрх"),
    ("Лыдушорское", "Мусюршорское"),
])
def test_unrelated_names_are_not_abbreviations(short: str, full: str) -> None:
    """Догадка не должна срабатывать на посторонних названиях."""
    from apps.catalog.services import looks_like_abbreviation

    assert not looks_like_abbreviation(short, full)


@pytest.mark.django_db
def test_roles_are_created_once() -> None:
    """Создание ролей безопасно при повторном выполнении."""
    first = ensure_roles()
    second = ensure_roles()
    assert set(first) == {role.value for role in Role}
    assert {g.pk for g in first.values()} == {g.pk for g in second.values()}
