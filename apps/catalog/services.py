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

from .models import Field, FieldAlias, Reference, Well, normalize


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


def get_field(name: str) -> Field | None:
    """Найти месторождение, а при отсутствии — завести новое.

    Args:
        name: Название так, как оно записано в рапорте.

    Returns:
        Месторождение или None, если название пустое.
    """
    found = find_field(name)
    if found is not None:
        return found
    key = normalize(name)
    if not key:
        return None
    return Field.objects.create(name=str(name).strip(), needs_review=True)


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
    """Найти скважину по номеру, а при отсутствии — завести.

    Скважины между месторождениями не переезжают, поэтому расхождение
    месторождения у известной скважины — признак ошибки в рапорте.
    Запись при этом не меняется и не дублируется: возвращается
    предупреждение, а решение остаётся за человеком.

    Args:
        number: Номер скважины из рапорта.
        field: Месторождение, указанное в той же строке рапорта.

    Returns:
        Пару «скважина, предупреждение». Скважина равна None, если номер
        пустой; предупреждение пустое, если расхождений нет.
    """
    number = str(number or "").strip()
    if not number:
        return None, ""

    found = Well.objects.filter(number=number).select_related("field").first()
    if found is None:
        if field is None:
            return None, f"скв. {number}: не указано месторождение"
        return Well.objects.create(number=number, field=field,
                                   needs_review=True), ""

    if field is not None and found.field_id != field.pk:
        return found, (f"скв. {number}: в рапорте месторождение "
                       f"«{field.name}», в справочнике — «{found.field.name}»")
    return found, ""


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
