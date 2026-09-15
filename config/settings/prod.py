# -*- coding: utf-8 -*-
"""Настройки для сервера.

Дополняют общие настройки требованиями к защищённости соединения.
Все значения, зависящие от площадки, задаются переменными окружения.
"""
from __future__ import annotations

from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, env, env_bool, env_list

# Статику отдаёт WhiteNoise: отдельный слой раздачи в контейнере не нужен,
# nginx остаётся только на TLS и проксировании.
MIDDLEWARE = MIDDLEWARE.copy()
MIDDLEWARE.insert(MIDDLEWARE.index("django.middleware.security."
                                   "SecurityMiddleware") + 1,
                  "whitenoise.middleware.WhiteNoiseMiddleware")

DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Приложение работает за nginx, который завершает TLS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# HSTS включается только после того, как сертификат заработал устойчиво:
# ошибочно включённый заголовок закрывает доступ к сайту на срок его действия.
SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = False

# Сессия закрывается вместе с браузером, а на стороне сервера живёт
# сутки с момента входа. Именно с момента входа, а не с последнего
# обращения: продление на каждом запросе потребовало бы записи в базу
# при каждом обращении, а разница здесь несущественна — рабочий день
# короче суток.
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = int(env("DJANGO_SESSION_AGE", "86400"))

EMAIL_BACKEND = env("DJANGO_EMAIL_BACKEND",
                    "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = int(env("EMAIL_PORT", "25"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "rvp-report@localhost")

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
