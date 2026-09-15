# -*- coding: utf-8 -*-
"""Принуждение к смене выданного пароля.

Пароль учётной записи назначает администратор и передаёт работнику —
голосом, запиской, в сообщении. Пока этот пароль действует, он известен
не только владельцу учётной записи, поэтому работа под ним не должна
продолжаться дальше формы смены.

Признак хранится в :attr:`~apps.accounts.models.User.must_change_password`
и снимается после успешной смены.
"""
from __future__ import annotations

from django.shortcuts import redirect
from django.urls import reverse


class PasswordChangeRequired:
    """Не пускает дальше формы смены пароля, пока пароль не заменён.

    Исключения — сама форма смены и выход из системы: иначе
    пользователь оказался бы заперт без возможности ни сменить
    пароль, ни выйти.
    """

    def __init__(self, get_response):
        """Запомнить следующий обработчик в цепочке."""
        self.get_response = get_response
        self._allowed: tuple[str, ...] | None = None

    @property
    def allowed(self) -> tuple[str, ...]:
        """Адреса, доступные до смены пароля.

        Вычисляются при первом обращении, а не при создании: на момент
        сборки цепочки обработчиков таблица адресов может быть
        ещё не готова.
        """
        if self._allowed is None:
            self._allowed = (reverse("accounts:password_change"),
                             reverse("accounts:logout"))
        return self._allowed

    def __call__(self, request):
        """Перенаправить на смену пароля, если она обязательна."""
        user = getattr(request, "user", None)
        if (user is not None and user.is_authenticated
                and getattr(user, "must_change_password", False)
                and request.path not in self.allowed):
            return redirect("accounts:password_change")
        return self.get_response(request)
