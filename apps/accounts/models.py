# -*- coding: utf-8 -*-
"""Пользователи и роли.

У каждого работника своя личная учётная запись: общих входов в системе
нет, иначе журнал действий теряет смысл — непонятно, кто загрузил или
заменил данные. Права определяются ролью, роль соответствует должности.
"""
from __future__ import annotations

from django.contrib.auth.models import AbstractUser, Group
from django.db import models


class Role(models.TextChoices):
    """Роли системы. Значение совпадает с именем группы Django."""

    ADMIN = "Администраторы", "Администратор"
    MANAGEMENT = "Руководство", "Руководство"
    FIELD = "Работники промысла", "Работник промысла"


#: Что разрешает каждая роль. Используется в правах и в справке интерфейса.
ROLE_ABILITIES = {
    Role.ADMIN: (
        "Полный доступ: справочники, пользователи, повторный разбор архива, "
        "всё, что могут остальные роли."
    ),
    Role.MANAGEMENT: (
        "Просмотр дашборда, карточек суток и сводок за период, "
        "скачивание презентаций и выгрузок."
    ),
    Role.FIELD: (
        "Загрузка и перезагрузка суточных рапортов, работа с замечаниями "
        "к данным, плюс всё, что доступно руководству."
    ),
}


class User(AbstractUser):
    """Учётная запись работника.

    Заводится администратором вручную через панель управления:
    самостоятельной регистрации в системе нет. При первом входе
    пользователь обязан сменить выданный пароль.
    """

    patronymic = models.CharField("Отчество", max_length=100, blank=True)
    position = models.CharField("Должность", max_length=150, blank=True)
    department = models.CharField("Подразделение", max_length=150, blank=True)
    phone = models.CharField("Телефон", max_length=30, blank=True)
    must_change_password = models.BooleanField(
        "Требуется смена пароля", default=True,
        help_text="Снимается автоматически после того, как пользователь "
                  "сменит выданный ему пароль.")

    class Meta:
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"
        ordering = ("last_name", "first_name")

    def __str__(self) -> str:
        """Фамилия и инициалы, а при их отсутствии — имя входа."""
        return self.short_name or self.get_username()

    @property
    def full_name(self) -> str:
        """Фамилия, имя и отчество одной строкой."""
        parts = [self.last_name, self.first_name, self.patronymic]
        return " ".join(part for part in parts if part).strip()

    @property
    def short_name(self) -> str:
        """Фамилия и инициалы, например «Иванов И. И.»."""
        if not self.last_name:
            return self.first_name.strip()
        initials = "".join(f"{part[0]}. " for part in
                           (self.first_name, self.patronymic) if part)
        return f"{self.last_name} {initials}".strip()

    @property
    def roles(self) -> list[str]:
        """Названия ролей, назначенных пользователю."""
        return [group.name for group in self.groups.all()]

    def has_role(self, *roles: str) -> bool:
        """Состоит ли пользователь хотя бы в одной из перечисленных ролей.

        Args:
            *roles: Значения :class:`Role`.

        Returns:
            ``True``, если роль назначена. Суперпользователь и
            администратор считаются обладателями любой роли.
        """
        if self.is_superuser or self.groups.filter(name=Role.ADMIN).exists():
            return True
        return self.groups.filter(name__in=roles).exists()

    @property
    def can_upload(self) -> bool:
        """Может ли пользователь загружать и заменять суточные рапорты."""
        return self.has_role(Role.FIELD)


def ensure_roles() -> dict[str, Group]:
    """Создать группы ролей, если их ещё нет.

    Вызывается миграцией и командой начальной настройки, поэтому
    безопасна при повторном выполнении.

    Returns:
        Соответствие «название роли — группа».
    """
    return {role.value: Group.objects.get_or_create(name=role.value)[0]
            for role in Role}
