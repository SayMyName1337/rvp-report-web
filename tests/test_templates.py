# -*- coding: utf-8 -*-
"""Проверки самих шаблонов, без отрисовки страниц.

Ошибка в разметке шаблона не роняет страницу: Django выводит
непонятое место как обычный текст. Проверки, которые ищут на странице
заданную строку, такого не замечают — строка на месте, а рядом с ней
в глаза пользователю смотрит кусок служебной разметки.

Поэтому шаблоны проверяются ещё и как файлы: на каждую ошибку, которая
проявляется не падением, а мусором на странице.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"


def template_files() -> list[Path]:
    """Все шаблоны проекта."""
    return sorted(TEMPLATES.rglob("*.html"))


def test_templates_are_found() -> None:
    """Сами проверки должны на чём-то работать."""
    assert len(template_files()) > 10, "шаблоны не найдены"


@pytest.mark.parametrize("path", template_files(),
                         ids=lambda p: p.name)
def test_comments_close_on_their_own_line(path: Path) -> None:
    """Комментарий {# … #} закрывается в той же строке.

    Django понимает такой комментарий только однострочным. Перенос
    закрывающих знаков на следующую строку не ошибка разбора: весь
    комментарий выводится на страницу как текст. Именно так
    в заголовок сводки попала фраза «После "из" существительное
    стоит в одной и той же форме…».

    Многострочный комментарий пишется через {% comment %}.
    """
    for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1):
        if "{#" in line and "#}" not in line.split("{#", 1)[1]:
            raise AssertionError(
                f"{path.relative_to(ROOT)}:{number}: комментарий {{# … #}} "
                "не закрыт в той же строке — он выйдет на страницу "
                "текстом; для многострочного нужен {% comment %}")


@pytest.mark.parametrize("path", template_files(),
                         ids=lambda p: p.name)
def test_tags_and_variables_are_closed(path: Path) -> None:
    """Каждая скобка {% … %} и {{ … }} закрыта в той же строке.

    Незакрытая скобка так же выводится на страницу как текст.
    """
    text = path.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        for opening, closing in (("{%", "%}"), ("{{", "}}")):
            tail = line
            while opening in tail:
                tail = tail.split(opening, 1)[1]
                if closing not in tail:
                    raise AssertionError(
                        f"{path.relative_to(ROOT)}:{number}: скобка "
                        f"{opening} не закрыта в той же строке")
                tail = tail.split(closing, 1)[1]


#: Фильтры, рассчитанные на две формы слова. В русском их три,
#: и при трёх вариантах встроенный фильтр молча отдаёт пустую строку.
TWO_FORM_FILTER = re.compile(r"\|pluralize:\"[^\"]*,[^\"]*,")


@pytest.mark.parametrize("path", template_files(),
                         ids=lambda p: p.name)
def test_russian_forms_use_the_right_filter(path: Path) -> None:
    """Три формы слова передаются фильтру ``plural``, а не ``pluralize``.

    Встроенный ``pluralize`` при трёх вариантах возвращает пустую
    строку, не бросая исключения: существительное со страницы просто
    исчезает.
    """
    text = path.read_text(encoding="utf-8")
    assert not TWO_FORM_FILTER.search(text), (
        f"{path.relative_to(ROOT)}: трём формам нужен фильтр plural")
