# -*- coding: utf-8 -*-
"""Адрес обратившегося при работе за обратным прокси."""
from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest


def client_address(request: HttpRequest) -> str | None:
    """Адрес, с которого пришло обращение.

    На сервере перед приложением стоит nginx, и адресом соединения
    для всех обращений оказывается адрес контейнера прокси — один
    и тот же. Учёт попыток входа по такому адресу бессмыслен, поэтому
    берётся заголовок ``X-Real-IP``.

    Именно он, а не ``X-Forwarded-For``: ``X-Real-IP`` nginx назначает
    сам (``proxy_set_header X-Real-IP $remote_addr``), затирая присланное
    клиентом, и подделать его через прокси нельзя. К ``X-Forwarded-For``
    nginx дописывает, а не заменяет, поэтому левая часть цепочки
    приходит от клиента и доверия не заслуживает.

    Заголовок читается только там, где настройками объявлено, что
    приложение стоит за прокси. Без этого при запуске без nginx любой
    обратившийся назначал бы себе адрес сам и уходил бы от блокировки,
    меняя заголовок после каждой попытки.

    Args:
        request: Обращение.

    Returns:
        Адрес обратившегося либо None, если определить его не удалось.
    """
    if getattr(settings, "TRUST_PROXY_CLIENT_IP", False):
        forwarded = request.META.get("HTTP_X_REAL_IP", "").strip()
        if forwarded:
            return forwarded
    return request.META.get("REMOTE_ADDR") or None
