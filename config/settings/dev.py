# -*- coding: utf-8 -*-
"""Настройки для разработки.

Отличаются от серверных только тем, что нужно для удобства работы:
подробные ошибки, отключённые требования HTTPS и вывод писем в консоль.
"""
from __future__ import annotations

from .base import *  # noqa: F401,F403
from .base import env_bool, env_list

# Свои страницы ошибок Django отдаёт только при выключенном DEBUG,
# поэтому выключать его надо уметь и в разработке:
#
#   DJANGO_DEBUG=0 python manage.py runserver --insecure
#
# Ключ `--insecure` оставляет раздачу статики, иначе страница выйдет
# без оформления.
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")

INTERNAL_IPS = ["127.0.0.1"]
