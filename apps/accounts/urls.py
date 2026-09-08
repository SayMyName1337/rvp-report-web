# -*- coding: utf-8 -*-
"""Адреса раздела «Пользователи»: вход, выход и смена пароля."""
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("password/", views.PasswordChangeView.as_view(),
         name="password_change"),
]
