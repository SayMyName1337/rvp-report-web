# -*- coding: utf-8 -*-
"""Страницы ошибок.

Без своих шаблонов Django отдаёт страницу в одну строку по-английски:
«Not Found», «Server Error (500)». Начальник ЦИТУ, увидев такую в восемь
утра, не поймёт ни что случилось, ни успеет ли он доложить в девять.
Поэтому страницы свои: на русском, с указанием, что делать дальше.

Шаблоны ``400.html``, ``403.html``, ``403_csrf.html`` и ``500.html``
Django находит по имени сам. Своё представление нужно только для 404 —
ради пояснения, почему именно не найдено.
"""
from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render


class Missing(Http404):
    """Не найдено, и причину можно показать человеку.

    Обычный :class:`~django.http.Http404` несёт служебный текст
    (``No Report matches the given query``): он написан для
    разработчика, по-английски и с именем модели. Наследник помечает
    те случаи, где сообщение составлено для пользователя и его
    не стыдно вывести на страницу.
    """


def not_found(request: HttpRequest, exception: Exception,
              template_name: str = "404.html") -> HttpResponse:
    """Страница «не найдено».

    Args:
        request: Запрос, не нашедший страницы.
        exception: Исключение, прервавшее обработку.
        template_name: Шаблон страницы.

    Returns:
        Ответ с кодом 404 и пояснением, если оно написано для человека.
    """
    reason = str(exception) if isinstance(exception, Missing) else ""
    return render(request, template_name, {"reason": reason}, status=404)
