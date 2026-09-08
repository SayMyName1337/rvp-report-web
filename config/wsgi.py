# -*- coding: utf-8 -*-
"""Точка входа WSGI: через неё приложение запускает gunicorn."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()
