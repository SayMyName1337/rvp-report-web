# -*- coding: utf-8 -*-
"""Проверки, которые иначе срабатывают только на сервере.

Часть ошибок развёртывания не видна ни в разработке, ни в обычных
проверках: в разработке статику отдаёт сам Django и ничего не собирает,
а прикладные тесты работают с настройками разработки. Такая ошибка
проявляется при первом запуске контейнера — то есть в самый неудачный
момент. Проверки ниже воспроизводят серверную конфигурацию здесь.
"""
from __future__ import annotations

import pytest
from django.core.management import call_command

#: Хранилище статики, применяемое на сервере: считает хеш каждого файла
#: и проверяет ссылки внутри файлов.
PRODUCTION_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


def test_static_files_collect_the_way_they_do_on_the_server(
        tmp_path, settings) -> None:
    """Сборка статики проходит в серверной конфигурации.

    Хранилище сервера разбирает содержимое файлов и обрывается, если
    файл ссылается на отсутствующий. Так и случилось: во вложенной
    библиотеке графиков осталась ссылка на карту исходников, которой
    в поставке нет, и контейнер не поднимался вовсе — сборка статики
    выполняется до запуска приложения.
    """
    settings.STATIC_ROOT = str(tmp_path)
    settings.STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {"BACKEND": PRODUCTION_STORAGE},
    }

    call_command("collectstatic", "--noinput", verbosity=0)

    assert (tmp_path / "staticfiles.json").exists(), "манифест не собран"


@pytest.mark.django_db
def test_system_checks_pass_in_deployment_mode(settings) -> None:
    """Проверки Django для развёртывания не находят ошибок.

    Предупреждения (например, о невключённом HSTS) допустимы:
    заголовок включается вручную после того, как сертификат
    заработал устойчиво. Ошибки недопустимы.
    """
    settings.DEBUG = False
    settings.ALLOWED_HOSTS = ["rapport.example.ru"]

    call_command("check", deploy=True, fail_level="ERROR", verbosity=0)
