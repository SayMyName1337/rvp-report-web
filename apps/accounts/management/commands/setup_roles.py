# -*- coding: utf-8 -*-
"""Создание ролей системы. Выполняется при первом развёртывании."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.accounts.models import ROLE_ABILITIES, Role, ensure_roles


class Command(BaseCommand):
    """Завести группы ролей, если их ещё нет."""

    help = "Создать роли: администратор, руководство, работник промысла"

    def handle(self, *args, **options) -> None:
        """Создать недостающие группы и показать состав ролей."""
        before = set(Role.values)
        groups = ensure_roles()
        self.stdout.write("Роли системы:")
        for role in Role:
            group = groups[role.value]
            mark = "создана" if group.name in before else "уже была"
            self.stdout.write(f"  {role.value} — {mark}")
            self.stdout.write(f"      {ROLE_ABILITIES[role]}")
        self.stdout.write(self.style.SUCCESS(
            "Готово. Учётные записи заводятся вручную в панели управления."))
