# -*- coding: utf-8 -*-
"""Запись разобранного рапорта в базу.

Слой между движком разбора и моделями Django. Разбор ничего не знает про
базу, модели ничего не знают про Excel, а здесь одно превращается
в другое — и только здесь.

Загрузка **идемпотентна по дате**: рапорт присылают с исправлениями,
и повторная загрузка за ту же дату заменяет суточные строки целиком,
в одной транзакции. История самих загрузок при этом сохраняется:
видно, кто, когда и каким файлом заменил данные.

Поля моделей названы так же, как поля структур ``domain/model.py``,
поэтому перекладка скалярных показателей идёт по списку имён, взятому
из самой модели. Совпадение имён проверяется тестом: разойдись они —
показатель молча перестал бы записываться.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import fields as dataclass_fields
from datetime import date, datetime
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import (Contractor, DowntimeReason, InjectionObject,
                                 MeteringNode, PowerObject, Tank)
from apps.catalog.services import (find_field, get_field_checked,
                                   get_reference, get_well)
from rvp_report.domain.model import DailyReport
from rvp_report.excel.reader import ReportReader

from .models import (DeliveryDaily, DieselStockDaily, DowntimeBreakdownDaily,
                     DrillingDaily, FieldProductionDaily, GasDaily,
                     GroupEvent, HseDaily, InjectionDaily, LoadIssue,
                     PiggingDaily, PowerDaily, ProductionDaily,
                     ProvenanceEntry, QualityDaily, RampUpDaily, Report,
                     StockDaily, TankDaily, Upload, WellDaily, WellTotals)

#: Как выглядит номер скважины: цифры и, возможно, одна буква — «32201»,
#: «9Р», «13р», «1П». Всё остальное на этом месте — групповая запись:
#: «76 скважин», «куст №1», «1102, 1110».
WELL_NUMBER = re.compile(r"^\d+\s*[А-Яа-яA-Za-z]?$")

#: Из групповой записи вида «76 скважин» вынимается количество.
WELLS_COUNT = re.compile(r"(\d+)\s*скважин", re.IGNORECASE)

#: Таблицы, содержимое которых пересоздаётся при каждой загрузке суток.
#: Перечислены классами, а не именами связей: обращение к отсутствующей
#: связи «один к одному» возбуждает исключение, а выборка — нет.
REPLACED = (ProductionDaily, DeliveryDaily, PowerDaily, HseDaily,
            FieldProductionDaily, StockDaily, WellDaily, WellTotals,
            GroupEvent, RampUpDaily, DowntimeBreakdownDaily, InjectionDaily,
            TankDaily, QualityDaily, GasDaily, DieselStockDaily,
            DrillingDaily, PiggingDaily, LoadIssue, ProvenanceEntry)

#: По какому слову в названии строки баланса газа определяется её вид.
GAS_KINDS = (
    ("утилизац", GasDaily.Kind.UTILIZATION),
    ("факел", GasDaily.Kind.FLARE),
    ("добыч", GasDaily.Kind.PRODUCTION),
)

#: Списки скважин: поле модели рапорта, итог, категория в базе.
WELL_LISTS = (
    ("downtime", "downtime_total", WellDaily.Category.DOWNTIME),
    ("idle", "idle_total", WellDaily.Category.IDLE),
    ("vsp", "vsp_total", WellDaily.Category.VSP),
    ("startups", "startups_total", WellDaily.Category.STARTUP),
)


class LoadError(Exception):
    """Файл не удалось прочитать как суточный рапорт."""


def digest(path: str | Path) -> str:
    """Контрольная сумма файла.

    Args:
        path: Путь к файлу.

    Returns:
        SHA-256 в шестнадцатеричном виде.
    """
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


#: Поля, которые загрузчик заполняет сам, а не переносит из структуры
#: разбора: в исходных структурах их нет и быть не должно.
OWN_FIELDS = {"id", "report", "source_row", "is_total", "kind", "category",
              "incidents_count", "medical_count", "well_number",
              "current_depth_text", "start_date"}


def scalar_names(model) -> list[str]:
    """Имена простых полей модели, переносимых из структуры разбора.

    Args:
        model: Класс модели Django.

    Returns:
        Имена полей без служебных, без связей и без тех, что загрузчик
        заполняет сам.
    """
    return [field.name for field in model._meta.get_fields()
            if getattr(field, "concrete", False)
            and field.name not in OWN_FIELDS and not field.is_relation]


def copy_scalars(source, target, names: list[str]) -> None:
    """Перенести одноимённые показатели из структуры разбора в модель.

    Args:
        source: Структура из ``domain/model.py``.
        target: Экземпляр модели Django.
        names: Имена переносимых полей.
    """
    for name in names:
        setattr(target, name, getattr(source, name, None))


def missing_names(model, structure) -> list[str]:
    """Поля модели, которых нет в структуре разбора.

    Нужна тесту: расхождение имён означало бы, что показатель
    молча перестал записываться.

    Args:
        model: Класс модели Django.
        structure: Класс структуры из ``domain/model.py``.

    Returns:
        Имена полей модели, отсутствующие в структуре.
    """
    known = {field.name for field in dataclass_fields(structure)}
    return [name for name in scalar_names(model) if name not in known]


# --- чтение файла ------------------------------------------------------------
def read_file(path: str | Path) -> tuple[DailyReport, list[str]]:
    """Прочитать файл рапорта.

    Args:
        path: Путь к файлу .xlsx.

    Returns:
        Пару «разобранный рапорт, список показателей, взятых по эталону».

    Raises:
        LoadError: Если файл не удалось прочитать как суточный рапорт.
    """
    try:
        reader = ReportReader(str(path))
        daily = reader.read()
    except Exception as error:                     # noqa: BLE001
        raise LoadError(str(error)) from error
    if daily.report_date is None:
        raise LoadError("в файле не найдена отчётная дата")
    return daily, list(reader.map.degraded)


# --- запись в базу -----------------------------------------------------------
@transaction.atomic
def store(daily: DailyReport, degraded: list[str],
          upload: Upload | None = None) -> Report:
    """Записать разобранный рапорт в базу, заменив данные за эту дату.

    Args:
        daily: Разобранный суточный рапорт.
        degraded: Показатели, взятые по эталонному адресу.
        upload: Загрузка, из которой пришли данные.

    Returns:
        Сутки с записанными данными.
    """
    report, _created = Report.objects.get_or_create(date=daily.report_date)
    for model in REPLACED:
        model.objects.filter(report=report).delete()

    report.temperature = daily.temperature
    report.wind = daily.wind
    report.gas_utilization_pct = daily.gas_utilization_pct
    report.free_volume_total_m3 = daily.free_volume_total_m3
    report.status = (Report.Status.NEEDS_REVIEW if degraded
                     else Report.Status.LOADED)
    report.save()

    warnings: list[str] = []
    _store_blocks(report, daily)
    _store_fields(report, daily, warnings)
    _store_stock(report, daily, warnings)
    _store_wells(report, daily, warnings)
    _store_ramp_up(report, daily, warnings)
    _store_breakdown(report, daily)
    _store_injection(report, daily)
    _store_tanks(report, daily)
    _store_quality(report, daily)
    _store_gas(report, daily)
    _store_power_rows(report, daily)
    _store_drilling(report, daily, warnings)
    _store_pigging(report, daily)
    _store_issues(report, daily, warnings)
    _store_provenance(report, daily)

    if upload is not None:
        Upload.objects.filter(report=report).update(is_current=False)
        upload.report = report
        upload.is_current = True
        upload.status = Upload.Status.LOADED
        upload.save(update_fields=["report", "is_current", "status"])
    return report


def _store_blocks(report: Report, daily: DailyReport) -> None:
    """Показатели, единственные на сутки: добыча, сдача, энергетика, ПБиОТ."""
    production = ProductionDaily(report=report)
    copy_scalars(daily.production, production, scalar_names(ProductionDaily))
    production.save()

    delivery = DeliveryDaily(report=report)
    copy_scalars(daily.delivery, delivery, scalar_names(DeliveryDaily))
    delivery.save()

    power = PowerDaily(report=report)
    copy_scalars(daily.power, power, scalar_names(PowerDaily))
    power.save()

    HseDaily.objects.create(
        report=report,
        incidents_count=len(daily.hse.incidents),
        medical_count=daily.hse.medical_count)


def _field(name: str, warnings: list[str]):
    """Месторождение из справочника, с подсказкой о возможном сокращении.

    Args:
        name: Название так, как оно записано в рапорте.
        warnings: Список, куда добавляются подсказки. Повторы не пишутся.

    Returns:
        Месторождение или None, если название пустое.
    """
    field, _created, hint = get_field_checked(name)
    if hint and hint not in warnings:
        warnings.append(hint)
    return field


def _store_fields(report: Report, daily: DailyReport,
                  warnings: list[str]) -> None:
    """Добыча по месторождениям."""
    seen: set[int] = set()
    for name, qo in daily.production.by_field:
        field = _field(name, warnings)
        if field is None:
            continue
        if field.pk in seen:
            warnings.append(f"месторождение «{name}» встретилось дважды "
                            "в добыче по месторождениям")
            continue
        seen.add(field.pk)
        FieldProductionDaily.objects.create(report=report, field=field, qo=qo)


def _store_stock(report: Report, daily: DailyReport,
                 warnings: list[str]) -> None:
    """Фонд скважин по месторождениям и итог."""
    names = scalar_names(StockDaily)

    if daily.stock_total is not None:
        row = StockDaily(report=report, is_total=True)
        copy_scalars(daily.stock_total, row, names)
        row.save()

    seen: set[int] = set()
    for item in daily.stock_by_field:
        field = _field(item.name, warnings)
        if field is None or field.pk in seen:
            continue
        seen.add(field.pk)
        row = StockDaily(report=report, field=field)
        copy_scalars(item, row, names)
        row.save()


def _store_wells(report: Report, daily: DailyReport,
                 warnings: list[str]) -> None:
    """Списки скважин и итоги по ним."""
    for source, totals_name, category in WELL_LISTS:
        seen: set[int] = set()
        for item in getattr(daily, source):
            if not WELL_NUMBER.match(str(item.well or "").strip()):
                _store_group_event(report, item, category)
                continue
            field = _field(item.field_name, warnings)
            well, warning = get_well(item.well, field)
            if warning:
                warnings.append(warning)
            if well is None:
                continue
            if well.pk in seen:
                warnings.append(
                    f"скв. {item.well} встретилась дважды в списке "
                    f"«{WellDaily.Category(category).label}»")
                continue
            seen.add(well.pk)
            WellDaily.objects.create(
                report=report, well=well, category=category,
                qo=item.qo, ql=item.ql, wc=item.wc, pump=item.pump,
                reason=item.reason, code=item.code,
                well_category=item.category, days=item.days,
                status=item.status, note=item.note,
                stop_date=_safe_date(item.stop_date),
                last_repair=_safe_date(item.last_repair))

        totals = getattr(daily, totals_name, None)
        if totals is not None:
            WellTotals.objects.create(report=report, category=category,
                                      count=totals.count, qo=totals.qo,
                                      ql=totals.ql)

    if daily.shutdowns_total is not None:
        WellTotals.objects.create(
            report=report, category=WellTotals.Category.SHUTDOWN,
            count=daily.shutdowns_total.count, qo=daily.shutdowns_total.qo,
            ql=daily.shutdowns_total.ql)


def _store_group_event(report: Report, item, category: str) -> None:
    """Записать строку, относящуюся не к одной скважине, а к группе.

    Месторождение проставляется связью, только если запись относится
    к одному уже известному месторождению. Перечни вида «СХ, Вис, ЗХ»
    в справочник не заводятся: это не название месторождения.

    Args:
        report: Сутки, к которым относится запись.
        item: Строка списка скважин из разобранного рапорта.
        category: Список, в котором строка стояла.
    """
    subject = str(item.well or "").strip()
    text = str(item.field_name or "").strip()
    match = WELLS_COUNT.search(subject)
    GroupEvent.objects.create(
        report=report, category=category, subject=subject[:200],
        fields_text=text[:300], field=find_field(text),
        wells_count=float(match.group(1)) if match else None,
        qo=item.qo, ql=item.ql, wc=item.wc, reason=item.reason,
        code=item.code, days=item.days, status=item.status, note=item.note)


def _store_ramp_up(report: Report, daily: DailyReport,
                   warnings: list[str]) -> None:
    """Скважины на выводе на режим."""
    seen: set[int] = set()
    for item in daily.ramp_up:
        field = _field(item.field_name, warnings)
        well, warning = get_well(item.well, field)
        if warning:
            warnings.append(warning)
        if well is None or well.pk in seen:
            continue
        seen.add(well.pk)
        RampUpDaily.objects.create(
            report=report, well=well, plan_ql=item.plan_ql,
            plan_qo=item.plan_qo, fact_ql=item.fact_ql, fact_qo=item.fact_qo,
            fact_wc=item.fact_wc, pump=item.pump, gtm=item.gtm,
            days=item.days, note=item.note)


def _store_breakdown(report: Report, daily: DailyReport) -> None:
    """Разбивка простоя по причинам."""
    seen: set[int] = set()
    for name, count, qo in daily.downtime_breakdown:
        reason = get_reference(DowntimeReason, name)
        if reason is None or reason.pk in seen:
            continue
        seen.add(reason.pk)
        DowntimeBreakdownDaily.objects.create(
            report=report, reason=reason, wells_count=count, qo=qo)


def _store_injection(report: Report, daily: DailyReport) -> None:
    """Закачка по объектам ППД и итог."""
    names = scalar_names(InjectionDaily)
    seen: set[int] = set()
    for item in daily.injection:
        obj = get_reference(InjectionObject, item.name)
        if obj is None or obj.pk in seen:
            continue
        seen.add(obj.pk)
        row = InjectionDaily(report=report, object=obj)
        copy_scalars(item, row, names)
        row.save()

    if daily.injection_total is not None:
        row = InjectionDaily(report=report, is_total=True)
        copy_scalars(daily.injection_total, row, names)
        row.save()


def _store_tanks(report: Report, daily: DailyReport) -> None:
    """Резервуарный парк."""
    names = scalar_names(TankDaily)
    seen: set[int] = set()
    for item in daily.tanks:
        tank = get_reference(Tank, item.name)
        if tank is None or tank.pk in seen:
            continue
        seen.add(tank.pk)
        row = TankDaily(report=report, tank=tank)
        copy_scalars(item, row, names)
        row.save()


def _store_quality(report: Report, daily: DailyReport) -> None:
    """Качество товарной нефти по узлам учёта."""
    names = scalar_names(QualityDaily)
    seen: set[int] = set()
    for item in daily.quality:
        node = get_reference(MeteringNode, item.node)
        if node is None or node.pk in seen:
            continue
        seen.add(node.pk)
        row = QualityDaily(report=report, node=node)
        copy_scalars(item, row, names)
        row.save()


def _store_gas(report: Report, daily: DailyReport) -> None:
    """Баланс попутного нефтяного газа."""
    names = scalar_names(GasDaily)
    seen: set[str] = set()
    for item in daily.gas:
        kind = _gas_kind(item.name)
        if kind is None or kind in seen:
            continue
        seen.add(kind)
        row = GasDaily(report=report, kind=kind)
        copy_scalars(item, row, names)
        row.save()


def _gas_kind(name: str) -> str | None:
    """Определить вид строки баланса газа по её названию."""
    text = (name or "").lower()
    for marker, kind in GAS_KINDS:
        if marker in text:
            return kind
    return None


def _store_power_rows(report: Report, daily: DailyReport) -> None:
    """Остатки дизельного топлива по объектам."""
    seen: set[int] = set()
    for name, tons in daily.power.diesel_stock:
        obj = get_reference(PowerObject, name)
        if obj is None or obj.pk in seen:
            continue
        seen.add(obj.pk)
        DieselStockDaily.objects.create(report=report, object=obj, tons=tons)


def _store_drilling(report: Report, daily: DailyReport,
                    warnings: list[str]) -> None:
    """Скважины в бурении.

    Месторождения здесь пишут сокращённо — «С.Ошк», «ЗХ», — поэтому
    именно на этом блоке чаще всего срабатывает подсказка о синониме.
    """
    for item in daily.drilling:
        contractor = get_reference(Contractor, item.contractor)
        field = _field(item.field_name, warnings)
        if contractor is None or field is None:
            continue
        DrillingDaily.objects.create(
            report=report, contractor=contractor, field=field,
            well_number=str(item.well), target_depth=item.target_depth,
            current_depth=item.current_depth,
            current_depth_text=item.current_depth_text,
            start_date=_safe_date(item.start_date))


def _store_pigging(report: Report, daily: DailyReport) -> None:
    """Пуски очистных устройств."""
    for item in daily.pigging:
        PiggingDaily.objects.create(
            report=report, line=item.line, section=item.section,
            launch=_aware(item.launch), receive=_aware(item.receive),
            travel_h=item.travel_h, note=item.note)


def _store_issues(report: Report, daily: DailyReport,
                  extra: list[str]) -> None:
    """Замечания к качеству данных, найденные при разборе и при записи."""
    rows = [LoadIssue(report=report, level=issue.level, where=issue.where,
                      message=issue.message) for issue in daily.issues]
    rows += [LoadIssue(report=report, level=LoadIssue.Level.WARNING,
                       where="Справочники", message=message)
             for message in extra]
    LoadIssue.objects.bulk_create(rows)


def _store_provenance(report: Report, daily: DailyReport) -> None:
    """Происхождение каждого показателя."""
    ProvenanceEntry.objects.bulk_create([
        ProvenanceEntry(report=report, section=item.section, label=item.label,
                        value=item.value, kind=item.kind, origin=item.origin)
        for item in daily.ledger.items])


def _aware(value) -> datetime | None:
    """Время из рапорта с часовым поясом приложения.

    В рапорте время записано без пояса — промысел живёт по московскому,
    он же задан настройкой ``TIME_ZONE``.
    """
    if not isinstance(value, datetime):
        return None
    if timezone.is_aware(value):
        return value
    return timezone.make_aware(value, timezone.get_current_timezone())


def _safe_date(value) -> date | None:
    """Дата, если она правдоподобна.

    В рапорте встречаются опечатки вроде 13.02.2107 — такие значения
    в базу не попадают, но остаются в замечаниях, записанных разбором.
    """
    if not isinstance(value, date):
        return None
    return value if 1950 <= value.year <= date.today().year + 1 else None
