# -*- coding: utf-8 -*-
"""Поиск и заведение записей справочников при загрузке рапорта.

Загрузчик передаёт сюда название так, как оно написано в рапорте,
и получает запись справочника. Новые записи создаются молча, но
помечаются как требующие проверки: администратор потом просматривает
их и либо подтверждает, либо связывает синонимом с уже существующей.

Ошибкой считается не появление новой записи, а её незаметность.
"""
from __future__ import annotations

from django.db import models

from .models import (Field, FieldAlias, Reference, Well, normalize,
                     segments)


def find_field(name: str) -> Field | None:
    """Найти месторождение по названию или его синониму.

    Args:
        name: Название так, как оно записано в рапорте.

    Returns:
        Месторождение или None, если такого написания в справочнике нет.
    """
    key = normalize(name)
    if not key:
        return None
    found = Field.objects.filter(key=key).first()
    if found is not None:
        return found
    alias = FieldAlias.objects.filter(key=key).select_related("field").first()
    return alias.field if alias is not None else None


def looks_like_abbreviation(short: str, full: str) -> bool:
    """Похоже ли ``short`` на сокращение названия ``full``.

    Распознаёт три способа сокращать, которыми пользуются в рапорте:

    * начало названия — «Сюрх» вместо «Сюрхаратинского»;
    * начала частей — «С.Ошк» вместо «Северо-Ошкотынского»;
    * первые буквы частей — «ЗХ» вместо «Западно-Хоседаюского».

    Args:
        short: Предполагаемое сокращение.
        full: Полное название месторождения.

    Returns:
        ``True``, если сокращение согласуется с названием.
    """
    short_key, full_key = normalize(short), normalize(full)
    if not short_key or not full_key or short_key == full_key:
        return False
    if len(short_key) >= len(full_key):
        return False

    if full_key.startswith(short_key):
        return True

    short_parts, full_parts = segments(short), segments(full)
    if len(short_parts) > 1 and len(short_parts) == len(full_parts):
        return all(whole.startswith(part)
                   for part, whole in zip(short_parts, full_parts))

    if len(short_parts) == 1 and len(short_parts[0]) == len(full_parts) > 1:
        return all(whole.startswith(letter)
                   for letter, whole in zip(short_parts[0], full_parts))
    return False


def suggest_fields(name: str) -> list[Field]:
    """Месторождения, сокращением которых может быть данное название.

    Ничего не связывает само: догадка показывается администратору,
    решение остаётся за ним. Ошибочная догадка ничего не стоит,
    пропущенная — оставляет в справочнике двойника.

    Args:
        name: Название из рапорта, которого нет в справочнике.

    Returns:
        Подходящие месторождения, от более коротких названий к длинным.
    """
    if not normalize(name):
        return []
    found = [field for field in Field.objects.all()
             if looks_like_abbreviation(name, field.name)]
    return sorted(found, key=lambda field: len(field.name))


def get_field(name: str) -> Field | None:
    """Найти месторождение, а при отсутствии — завести новое.

    Args:
        name: Название так, как оно записано в рапорте.

    Returns:
        Месторождение или None, если название пустое.
    """
    field, _created, _hint = get_field_checked(name)
    return field


def get_field_checked(name: str) -> tuple[Field | None, bool, str]:
    """То же, что :func:`get_field`, но с пояснением о новой записи.

    Args:
        name: Название так, как оно записано в рапорте.

    Returns:
        Тройку «месторождение, создано ли оно, подсказка». Подсказка
        непустая, если новое название похоже на сокращение уже
        известного месторождения.
    """
    found = find_field(name)
    if found is not None:
        return found, False, ""
    if not normalize(name):
        return None, False, ""

    candidates = suggest_fields(name)
    created = Field.objects.create(name=str(name).strip(), needs_review=True)
    if not candidates:
        return created, True, ""
    names = ", ".join(f"«{item.name}»" for item in candidates[:3])
    return created, True, (
        f"месторождение «{created.name}» заведено как новое, но похоже "
        f"на сокращение: {names}. Свяжите синонимом в справочнике, "
        "иначе история разойдётся по двум записям")


def get_reference(model: type[Reference], name: str) -> Reference | None:
    """Найти запись справочника по названию, а при отсутствии — завести.

    Args:
        model: Класс справочника — наследник :class:`Reference`.
        name: Название так, как оно записано в рапорте.

    Returns:
        Запись справочника или None, если название пустое.
    """
    key = normalize(name)
    if not key:
        return None
    found = model.objects.filter(key=key).first()
    if found is not None:
        return found
    return model.objects.create(name=str(name).strip(), needs_review=True)


def get_well(number: str, field: Field | None) -> tuple[Well | None, str]:
    """Найти скважину по месторождению и номеру, а при отсутствии — завести.

    Скважина опознаётся парой «месторождение и номер»: сами номера между
    месторождениями повторяются, и одного номера для опознания мало.

    Args:
        number: Номер скважины из рапорта.
        field: Месторождение, указанное в той же строке рапорта.

    Returns:
        Пару «скважина, предупреждение». Скважина равна None, если номер
        пустой или месторождение не определено.
    """
    number = str(number or "").strip()
    if not number:
        return None, ""
    if field is None:
        return None, f"скв. {number}: не указано месторождение"

    found = Well.objects.filter(field=field, number=number).first()
    if found is not None:
        return found, ""
    return Well.objects.create(number=number, field=field,
                               needs_review=True), ""


def pending_review() -> dict[str, models.QuerySet]:
    """Записи справочников, ожидающие подтверждения администратором.

    Returns:
        Соответствие «название справочника — выборка непроверенных записей».
    """
    from . import models as catalog

    sources = [catalog.Field, catalog.InjectionObject, catalog.MeteringNode,
               catalog.Tank, catalog.Contractor, catalog.DowntimeReason,
               catalog.PowerObject, catalog.Well]
    out = {}
    for model in sources:
        pending = model.objects.filter(needs_review=True)
        if pending.exists():
            out[model._meta.verbose_name_plural] = pending
    return out
