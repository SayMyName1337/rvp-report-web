# -*- coding: utf-8 -*-
"""Общие настройки проекта.

Значения, различающиеся между разработкой и сервером, вынесены
в :mod:`config.settings.dev` и :mod:`config.settings.prod`. Секреты
и параметры среды читаются из переменных окружения, образец —
в файле ``.env.example``.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    """Прочитать переменную окружения.

    Args:
        name: Имя переменной.
        default: Значение, если переменная не задана.

    Returns:
        Значение переменной окружения или ``default``.
    """
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    """Прочитать логическую переменную окружения.

    Истиной считаются ``1``, ``true``, ``yes`` и ``on`` в любом регистре.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def env_list(name: str, default: str = "") -> list[str]:
    """Прочитать переменную окружения как список значений через запятую."""
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-key-for-local-use-only")
DEBUG = False
ALLOWED_HOSTS: list[str] = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# --- Приложения --------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS: list[str] = []

LOCAL_APPS = [
    "apps.accounts",
    "apps.catalog",
    "apps.reports",
    "apps.layout",
    "apps.analytics",
    "apps.decks",
    "apps.guide",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise подключается только на сервере: в разработке статику
    # отдаёт сам Django, и собранного каталога staticfiles ещё нет.
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- База данных -------------------------------------------------------------
# PostgreSQL используется и в разработке, и на сервере: сводки за период
# опираются на оконные функции и усечение дат, и расхождение диалектов
# между средами проявилось бы именно там, где цена ошибки наибольшая.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "rvp"),
        "USER": env("POSTGRES_USER", "rvp"),
        "PASSWORD": env("POSTGRES_PASSWORD", "rvp"),
        "HOST": env("POSTGRES_HOST", "127.0.0.1"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Пользователи ------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "analytics:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation."
             "UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation."
             "CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Локализация -------------------------------------------------------------
LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"     # НАО живёт по московскому времени
USE_I18N = True
USE_TZ = True

# --- Статика и файлы ---------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Загруженные рапорты и собранные презентации содержат коммерческую тайну
# и НЕ отдаются веб-сервером напрямую: скачивание идёт через представление
# с проверкой прав и записью в журнал.
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))

#: Предельный размер загружаемого суточного рапорта.
MAX_UPLOAD_SIZE_MB = int(env("MAX_UPLOAD_SIZE_MB", "25"))

# --- Фоновых задач нет --------------------------------------------------------
# Очередь из проекта убрана вместе с django-q. Всё, что делает система,
# делается в самом запросе: разбор рапорта занимает секунды, сборка
# презентации — пять, а происходит это раз в сутки. Очередь добавляла бы
# службу, состояние и новый способ сломаться, не давая ничего взамен.
# Повторный разбор всего архива — разовая работа администратора
# и выполняется командой `manage.py load_reports`.

# --- Журналирование ----------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}

# --- Гриф --------------------------------------------------------------------
COMPANY = "ООО «СК Русвьетпетро»"
CONFIDENTIALITY = f"Коммерческая тайна. {COMPANY}"
