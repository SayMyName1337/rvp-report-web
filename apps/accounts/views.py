# -*- coding: utf-8 -*-
"""Вход, выход и смена пароля.

Регистрации нет: учётные записи заводит администратор. Выданный пароль
пользователь обязан сменить при первом входе — до этого его перебрасывает
на форму смены с любой страницы.

Подбор пароля ограничен: после нескольких неудачных попыток вход
для сочетания «учётная запись + адрес» закрывается на время, и вместо
формы отдаётся страница с объяснением.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.shortcuts import render
from django.urls import reverse_lazy


class LoginView(auth_views.LoginView):
    """Форма входа."""

    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    """Выход из системы."""


class PasswordChangeView(auth_views.PasswordChangeView):
    """Смена собственного пароля."""

    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("analytics:dashboard")

    def form_valid(self, form):
        """Снять требование сменить пароль после успешной смены."""
        response = super().form_valid(form)
        user = self.request.user
        if user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=["must_change_password"])
        return response


def lockout(request, *args, **kwargs):
    """Страница вместо формы входа, пока действует блокировка.

    Сообщение должно называть срок и путь решения. Ответ без этого
    неотличим от неисправности системы, а до доклада может оставаться
    десять минут.

    Args:
        request: Обращение к форме входа.

    Returns:
        Страница блокировки с кодом 429.
    """
    return render(request, "accounts/lockout.html",
                  {"minutes": settings.AXES_COOLOFF_MINUTES,
                   "limit": settings.AXES_FAILURE_LIMIT},
                  status=settings.AXES_HTTP_RESPONSE_CODE)
