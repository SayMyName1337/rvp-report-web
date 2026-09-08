# -*- coding: utf-8 -*-
"""Вход, выход и смена пароля.

Регистрации нет: учётные записи заводит администратор. Выданный пароль
пользователь обязан сменить при первом входе — до этого его перебрасывает
на форму смены с любой страницы.
"""
from __future__ import annotations

from django.contrib.auth import views as auth_views
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
