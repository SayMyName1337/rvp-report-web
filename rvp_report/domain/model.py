# -*- coding: utf-8 -*-
"""Модель данных суточного рапорта.

Слой между Excel и презентацией: генератор слайдов не знает про ячейки,
парсер не знает про слайды.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .provenance import Ledger

#: Предельные значения показателей качества товарной нефти.
#: Взяты из подписей столбцов самого рапорта.
QUALITY_LIMITS = {"solids": 0.05, "h2s": 20.0, "mercaptans": 40.0,
                  "chlorides": 6.0, "salts": 100.0}


@dataclass
class Issue:
    """Замечание к качеству исходных данных."""
    level: str      # "warning" | "error"
    where: str      # человекочитаемое место, напр. «Бездействие, строка 68»
    message: str


@dataclass
class Production:
    """Плановые и фактические показатели добычи нефти за сутки."""
    plan_sg_day: float | None = None
    plan_sg_month: float | None = None
    plan_bp_day: float | None = None
    plan_bp_month: float | None = None
    closed_day: float | None = None
    fact_com_day: float | None = None
    dev_sg_day: float | None = None
    dev_sg_month: float | None = None
    dev_bp_day: float | None = None
    dev_bp_month: float | None = None
    dev_bp_year: float | None = None
    cumulative_month: float | None = None
    forecast_0600: float | None = None
    potential_com: float | None = None
    potential_limited: float | None = None
    nsj_closed: float | None = None
    nsj_fact: float | None = None
    nsj_dev: float | None = None
    by_field: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class Delivery:
    """Сдача нефти: на ПСП Головные и в систему «Транснефти»."""
    plan_day: float | None = None
    fact_day: float | None = None
    cumulative: float | None = None
    dev_day: float | None = None
    dev_month: float | None = None
    from_cps: float | None = None
    tn_plan_day: float | None = None
    tn_fact_day: float | None = None
    tn_cumulative: float | None = None
    tn_dev_day: float | None = None
    tn_dev_month: float | None = None
    tn_plan_month: float | None = None
    forecast_total: float | None = None
    forecast_rate_tph: float | None = None


@dataclass
class StockRow:
    """Строка таблицы состояния фонда скважин: месторождение или итог."""
    name: str
    total: float | None = None
    operating_stock: float | None = None
    in_work: float | None = None
    in_work_delta: float | None = None
    in_downtime: float | None = None
    downtime_rate: float | None = None
    in_idle: float | None = None
    idle_rate: float | None = None
    idle_delta: float | None = None
    awaiting: float | None = None
    inj_total: float | None = None
    inj_in_work: float | None = None
    inj_downtime: float | None = None
    inj_idle: float | None = None
    observation: float | None = None
    conservation: float | None = None
    liquidated: float | None = None


@dataclass
class WellRow:
    """Строка списка скважин (бездействие / простой / ВСП / ВНР)."""
    well: str = ""
    field_name: str = ""
    pump: str = ""
    qo: float | None = None          # потери нефти, т/сут
    ql: float | None = None          # жидкость, м3/сут
    wc: float | None = None          # обводнённость, %
    reason: str = ""
    code: str = ""
    category: str = ""
    days: str = ""
    status: str = ""
    stop_date: date | None = None
    last_repair: date | None = None
    note: str = ""


@dataclass
class Totals:
    """Итоги по списку скважин: количество, нефть и жидкость."""
    count: float | None = None
    qo: float | None = None
    ql: float | None = None


@dataclass
class RampUpRow:
    """Скважина на выводе на режим или под контролем после ГТМ."""
    field_name: str = ""
    well: str = ""
    plan_ql: float | None = None
    plan_qo: float | None = None
    fact_ql: float | None = None
    fact_qo: float | None = None
    fact_wc: float | None = None
    pump: str = ""
    gtm: str = ""
    days: str = ""
    note: str = ""


@dataclass
class InjectionRow:
    """Объект поддержания пластового давления: режим и факт закачки."""
    name: str = ""
    plan_day: float | None = None
    fact_day: float | None = None
    dev_day: float | None = None
    plan_month: float | None = None
    fact_month: float | None = None
    dev_month: float | None = None
    oil_in_water: float | None = None
    kvch: float | None = None


@dataclass
class TankRow:
    """Резервуар товарного парка: взлив, объём и свободная ёмкость."""
    name: str = ""
    level: float | None = None
    volume: float | None = None
    delta: float | None = None
    free: float | None = None


@dataclass
class QualityRow:
    """Показатели качества товарной нефти по одному узлу учёта."""
    node: str = ""
    density: float | None = None
    water: float | None = None
    solids: float | None = None
    sulfur: float | None = None
    paraffin: float | None = None
    h2s: float | None = None
    mercaptans: float | None = None
    chlorides: float | None = None
    salts: float | None = None


@dataclass
class GasRow:
    """Строка баланса попутного газа: добыча, утилизация или факел."""
    name: str = ""
    day_plan: float | None = None
    day_fact: float | None = None
    day_dev: float | None = None
    month_fact: float | None = None
    year_fact: float | None = None


@dataclass
class PowerState:
    """Состояние энергетики: выработка, работающие агрегаты, запас ДТ."""
    generation_gas: float | None = None
    generation_oil: float | None = None
    generation_diesel: float | None = None
    count_gpea: float | None = None
    count_nes: float | None = None
    count_dies: float | None = None
    total_sh_zh: float | None = None
    total_sh_zh_delta: float | None = None
    total_with_psp: float | None = None
    total_with_psp_delta: float | None = None
    diesel_stock: list[tuple[str, float]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class DrillingRow:
    """Скважина в бурении: подрядчик, проектная глубина и забой."""
    contractor: str = ""
    field_name: str = ""
    well: str = ""
    target_depth: float | None = None
    current_depth: float | None = None
    current_depth_text: str = ""
    start_date: date | None = None


@dataclass
class PiggingRow:
    """Пуск очистного устройства по одному участку трубопровода."""
    line: str = ""
    section: str = ""
    launch: datetime | None = None
    receive: datetime | None = None
    travel_h: float | None = None
    note: str = ""


@dataclass
class HSE:
    """Промышленная безопасность: происшествия и обращения в здравпункт.

    Текст обращений содержит персональные данные и в презентацию
    не выносится: на слайд попадает только их количество.
    """
    incidents: list[dict] = field(default_factory=list)
    medical_count: int = 0
    medical_raw: str = ""


@dataclass
class DailyReport:
    """Суточный рапорт целиком."""
    report_date: date | None = None
    temperature: float | None = None
    wind: str = ""

    production: Production = field(default_factory=Production)
    delivery: Delivery = field(default_factory=Delivery)

    stock_total: StockRow | None = None
    stock_by_field: list[StockRow] = field(default_factory=list)

    startups: list[WellRow] = field(default_factory=list)
    startups_total: Totals = field(default_factory=Totals)
    shutdowns_total: Totals = field(default_factory=Totals)
    shutdowns_note: str = ""

    idle: list[WellRow] = field(default_factory=list)
    idle_total: Totals = field(default_factory=Totals)

    downtime: list[WellRow] = field(default_factory=list)
    downtime_total: Totals = field(default_factory=Totals)
    downtime_breakdown: list[tuple[str, float, float]] = field(default_factory=list)

    vsp: list[WellRow] = field(default_factory=list)
    vsp_total: Totals = field(default_factory=Totals)

    ramp_up: list[RampUpRow] = field(default_factory=list)
    ramp_up_total: dict = field(default_factory=dict)

    injection: list[InjectionRow] = field(default_factory=list)
    injection_total: InjectionRow | None = None

    tanks: list[TankRow] = field(default_factory=list)
    free_volume_total_m3: float | None = None

    quality: list[QualityRow] = field(default_factory=list)
    gas: list[GasRow] = field(default_factory=list)
    gas_utilization_pct: float | None = None
    power: PowerState = field(default_factory=PowerState)

    pigging: list[PiggingRow] = field(default_factory=list)
    drilling: list[DrillingRow] = field(default_factory=list)
    hse: HSE = field(default_factory=HSE)

    issues: list[Issue] = field(default_factory=list)
    #: откуда взялся каждый показатель — заполняется читателем
    ledger: Ledger = field(default_factory=Ledger)

    # --- производные величины ------------------------------------------------
    @property
    def total_losses(self) -> float:
        """Суммарные потери добычи за сутки, т.

        В рапорте такой цифры нет: это сумма трёх величин, каждая из
        которых в рапорте есть — текущий простой, бездействующий фонд
        и внутрисменные потери. Происхождение раскрывается в ledger.
        """
        return sum(v or 0.0 for v in (
            self.downtime_total.qo, self.idle_total.qo, self.vsp_total.qo))

    @property
    def losses_share(self) -> float | None:
        """Доля потерь в суточной добыче, %."""
        closed = self.production.closed_day
        return None if not closed else self.total_losses / closed * 100

    def add_issue(self, level: str, where: str, message: str) -> None:
        """Добавить замечание к качеству данных.

        Args:
            level: ``error``, ``warning`` или ``info``.
            where: Блок рапорта, к которому относится замечание.
            message: Текст замечания для оператора.
        """
        self.issues.append(Issue(level, where, message))
