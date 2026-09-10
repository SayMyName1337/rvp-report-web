# -*- coding: utf-8 -*-
"""Общая обвязка тестов разбора рапортов.

Настоящие суточные рапорты — коммерческая тайна и в репозитории
не хранятся. Каталог с ними задаётся переменной окружения
``RVP_REPORTS_DIR``; по умолчанию берётся ``data_august`` в корне
проекта. Если каталога нет, тесты разбора пропускаются, и это
не считается провалом: остальные проверки от данных не зависят.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from rvp_report.domain.model import DailyReport
from rvp_report.excel.reader import read_report

ROOT = Path(__file__).resolve().parent.parent

#: Разобранные рапорты, чтобы не читать один файл в каждом тесте заново.
_CACHE: dict[Path, DailyReport] = {}


def reports_dir() -> Path:
    """Каталог с суточными рапортами для проверок."""
    return Path(os.environ.get("RVP_REPORTS_DIR", ROOT / "data_august"))


def report_files() -> list[Path]:
    """Файлы рапортов, отсортированные по имени. Пустой список — нет данных."""
    folder = reports_dir()
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.glob("*.xlsx")
                  if not path.name.startswith("~$"))


def load(path: Path) -> DailyReport:
    """Разобрать рапорт, повторно используя ранее прочитанный результат."""
    if path not in _CACHE:
        _CACHE[path] = read_report(str(path))
    return _CACHE[path]


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Развернуть тесты, принимающие ``report_path``, по всем файлам."""
    if "report_path" not in metafunc.fixturenames:
        return
    files = report_files()
    if not files:
        pytest.skip(f"нет рапортов в {reports_dir()}", allow_module_level=True)
    metafunc.parametrize("report_path", files, ids=[p.stem for p in files])
