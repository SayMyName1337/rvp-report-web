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
    ("Северо-Ошкотынское", "северо ошкотынское"),
    ("  Северо—Ошкотынское  ", "северо ошкотынское"),
    ("СЕВЕРО-ОШКОТЫНСКОЕ", "северо ошкотынское"),
    ("Тёдинское", "тединское"),
    ("ЦПС РВС-5000", "цпс рвс 5000"),
    ("", ""),
])
def test_normalize_ignores_meaningless_differences(written: str,
                                                   expected: str) -> None:
    """Регистр, пробелы, дефисы и «ё» не должны различать названия."""
    assert normalize(written) == expected


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
def test_well_keeps_its_field() -> None:
    """Скважина не переезжает на другое месторождение.

    Расхождение — признак ошибки в рапорте, а не повод завести вторую
    скважину с тем же номером.
    """
    one = Field.objects.create(name="Западно-Хоседаюское")
    other = Field.objects.create(name="Висовое")

    well, warning = get_well("32201", one)
    assert well is not None and not warning

    same, warning = get_well("32201", other)
    assert same == well, "скважина не должна раздвоиться"
    assert same.field == one, "месторождение скважины меняться не должно"
    assert "Висовое" in warning and "Западно-Хоседаюское" in warning


@pytest.mark.django_db
def test_roles_are_created_once() -> None:
    """Создание ролей безопасно при повторном выполнении."""
    first = ensure_roles()
    second = ensure_roles()
    assert set(first) == {role.value for role in Role}
    assert {g.pk for g in first.values()} == {g.pk for g in second.values()}
