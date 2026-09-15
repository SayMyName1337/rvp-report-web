# -*- coding: utf-8 -*-
"""Проверки сдаточной документации.

Документы, передаваемые заказчику, пишутся официальным техническим
языком, без обращения к читателю. Требование легко нарушить при
очередной правке, поэтому оно закреплено проверкой, а не памятью.

Рабочие документы разработки под это требование не подпадают
и здесь не проверяются.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Документы, передаваемые заказчику. Руководство пользователя —
#: страница интерфейса, оно проверяется в tests/test_guide.py.
DELIVERABLES = (
    "docs/program-description.md",
    "docs/deploy.md",
    "docs/acceptance.md",
    "README.md",
)

#: Формы обращения ко второму лицу.
SECOND_PERSON = re.compile(
    r"\b(вы|вам|вами|вас|ваш|ваша|ваше|ваши|вашего|вашей|вашему|вашим|"
    r"ваших|вашими|вашу)\b", re.IGNORECASE)

#: Цитаты сообщений интерфейса приводятся дословно и из проверки
#: изложения исключаются.
QUOTED = re.compile(r"«[^»]*»")

#: Ссылка на изображение в разметке Markdown.
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


@pytest.mark.parametrize("name", DELIVERABLES)
def test_deliverable_exists(name: str) -> None:
    """Каждый документ комплекта сдачи на месте."""
    assert (ROOT / name).is_file(), f"нет документа {name}"


@pytest.mark.parametrize("name", DELIVERABLES)
def test_deliverable_is_written_impersonally(name: str) -> None:
    """В сдаточном документе нет обращения к читателю на «вы»."""
    text = QUOTED.sub("", (ROOT / name).read_text(encoding="utf-8"))
    found = sorted(set(SECOND_PERSON.findall(text)))

    assert not found, f"{name}: обращение на «вы» — {found}"


@pytest.mark.parametrize("name", DELIVERABLES + ("docs/web-architecture.md",))
def test_referenced_images_exist(name: str) -> None:
    """Схемы, на которые ссылается документ, существуют.

    Ссылка в никуда в переданном документе означает пустое место
    на странице у того, кто его открыл.
    """
    path = ROOT / name
    for link in IMAGE.findall(path.read_text(encoding="utf-8")):
        if link.startswith(("http://", "https://")):
            continue
        assert (path.parent / link).is_file(), f"{name}: нет файла {link}"
