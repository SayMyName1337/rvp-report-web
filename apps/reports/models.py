# -*- coding: utf-8 -*-
"""Суточные данные рапорта.

Таблицы повторяют структуры из ``rvp_report/domain/model.py`` один в один.
Это сделано намеренно: перекладывание разобранного рапорта в базу должно
оставаться очевидным и проверяемым, а не превращаться в отдельную логику,
которую надо изучать отдельно от разбора.

Ключевые решения:

* на дату приходится один :class:`Report` и сколько угодно
  :class:`Upload` — рапорт присылают с исправлениями;
* загрузка идемпотентна по дате: суточные строки удаляются и пишутся
  заново в одной транзакции;
* нарастающие итоги, посчитанные в самом рапорте, хранятся отдельно
  от сумм по суткам — расхождение между ними само по себе диагностика;
* текст обращений в здравпункт не хранится нигде (см. :class:`HseDaily`).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.catalog.models import (Contractor, DowntimeReason, Field,
                                 InjectionObject, MeteringNode, PowerObject,
                                 Tank, Well)


def number(label: str, **kwargs) -> models.FloatField:
    """Необязательный числовой показатель.

    Пустое значение в рапорте означает «нет данных», а не ноль, поэтому
    все показатели допускают отсутствие.

    Args:
        label: Подпись поля в панели управления.
        **kwargs: Дополнительные параметры поля.

    Returns:
        Поле с плавающей точкой, допускающее пустое значение.
    """
    return models.FloatField(label, null=True, blank=True, **kwargs)


# --- Сутки и загрузки --------------------------------------------------------
class Report(models.Model):
    """Одни отчётные сутки.

    Запись на дату одна. Повторная загрузка рапорта за ту же дату
    заменяет суточные данные, но не создаёт вторых суток.
    """

    class Status(models.TextChoices):
        """Состояние суток."""

        LOADED = "loaded", "Загружены"
        NEEDS_REVIEW = "needs_review", "Требуют подтверждения"
        FAILED = "failed", "Не разобраны"

    date = models.DateField("Отчётная дата", unique=True, db_index=True)
    status = models.CharField("Состояние", max_length=20,
                              choices=Status.choices, default=Status.LOADED)

    temperature = number("Температура, °C")
    wind = models.CharField("Ветер", max_length=40, blank=True)

    gas_utilization_pct = number("Утилизация газа, %")
    free_volume_total_m3 = number("Свободный объём по всем объектам, м³")

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        verbose_name = "суточный рапорт"
        verbose_name_plural = "суточные рапорты"
        ordering = ("-date",)

    def __str__(self) -> str:
        """Отчётная дата в русской записи."""
        return f"Суточный рапорт {self.date:%d.%m.%Y}"

    #: Списки, из которых складываются потери добычи. Запуски и остановки
    #: сюда НЕ входят: это движение фонда, а не потери, и включать их
    #: значило бы завысить показатель доклада.
    LOSS_CATEGORIES = ("downtime", "idle", "vsp")

    @property
    def total_losses(self) -> float:
        """Суммарные потери добычи за сутки, т.

        В рапорте такой цифры нет: это сумма трёх величин, каждая
        из которых в рапорте есть, — текущего простоя, бездействующего
        фонда и внутрисменных потерь. Происхождение раскрывается
        в :class:`ProvenanceEntry`.
        """
        return sum(item.qo or 0.0 for item in self.well_totals.all()
                   if item.category in self.LOSS_CATEGORIES)


class WellTotals(models.Model):
    """Итог по одному списку скважин: количество, нефть и жидкость."""

    class Category(models.TextChoices):
        """Какой список подытоживается."""

        DOWNTIME = "downtime", "Текущий простой"
        IDLE = "idle", "Бездействие"
        VSP = "vsp", "Внутрисменные потери"
        STARTUP = "startup", "Запуски"
        SHUTDOWN = "shutdown", "Остановки"

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="well_totals",
                               verbose_name="Сутки")
    category = models.CharField("Список", max_length=20,
                                choices=Category.choices)
    count = number("Скважин")
    qo = number("Нефть, т/сут")
    ql = models.FloatField("Жидкость, м³/сут", null=True, blank=True)

    class Meta:
        verbose_name = "итог по списку скважин"
        verbose_name_plural = "итоги по спискам скважин"
        constraints = [models.UniqueConstraint(
            fields=("report", "category"), name="unique_well_totals")]

    def __str__(self) -> str:
        """Список и его итог."""
        return f"{self.get_category_display()}: {self.count} скв."


class Upload(models.Model):
    """Загрузка файла рапорта.

    История загрузок сохраняется целиком: видно, кто и когда заменил
    данные за дату и каким файлом. Действующей считается последняя
    успешная загрузка, остальные остаются для разбирательств.
    """

    class Status(models.TextChoices):
        """Состояние обработки файла."""

        QUEUED = "queued", "В очереди"
        PARSING = "parsing", "Разбирается"
        LOADED = "loaded", "Загружен"
        FAILED = "failed", "Ошибка"

    report = models.ForeignKey(Report, on_delete=models.SET_NULL, null=True,
                               blank=True, related_name="uploads",
                               verbose_name="Сутки")
    file = models.FileField("Файл рапорта", upload_to="reports/%Y/%m")
    original_name = models.CharField("Имя файла", max_length=255)
    sha256 = models.CharField("Контрольная сумма", max_length=64, db_index=True)
    size = models.PositiveIntegerField("Размер, байт")

    status = models.CharField("Состояние", max_length=20,
                              choices=Status.choices, default=Status.QUEUED)
    is_current = models.BooleanField(
        "Действующая", default=False,
        help_text="Данные за сутки взяты именно из этой загрузки.")
    log = models.TextField("Протокол разбора", blank=True)

    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                    on_delete=models.PROTECT,
                                    related_name="uploads",
                                    verbose_name="Загрузил")
    uploaded_at = models.DateTimeField("Загружено", auto_now_add=True)

    class Meta:
        verbose_name = "загрузка"
        verbose_name_plural = "загрузки"
        ordering = ("-uploaded_at",)

    def __str__(self) -> str:
        """Имя файла и время загрузки."""
        return f"{self.original_name} от {self.uploaded_at:%d.%m.%Y %H:%M}"


# --- Показатели, единственные на сутки ---------------------------------------
class ProductionDaily(models.Model):
    """Добыча нефти: планы, факт, потенциал и нарастающие итоги."""

    report = models.OneToOneField(Report, on_delete=models.CASCADE,
                                  related_name="production",
                                  verbose_name="Сутки")

    plan_sg_day = number("План СГ на сутки, т")
    plan_sg_month = number("План СГ на месяц, т")
    plan_bp_day = number("План БП на сутки, т")
    plan_bp_month = number("План БП на месяц, т")

    closed_day = number("Закрытие по сводке за сутки, т")
    fact_com_day = number("Факт ЦОМ за сутки, т")
    forecast_0600 = number("Прогноз на 6:00, т")

    dev_sg_day = number("± к СГ за сутки, т")
    dev_sg_month = number("± к СГ с начала месяца, т")
    dev_bp_day = number("± к БП за сутки, т")
    dev_bp_month = number("± к БП с начала месяца, т")
    dev_bp_year = number("± к БП с начала года, т")
    cumulative_month = number("Нарастающая за месяц, т")

    potential_com = number("Потенциал, т")
    potential_limited = number("Потенциал с учётом ограничений, т")

    nsj_closed = number("НСЖ закрытие, м³")
    nsj_fact = number("НСЖ факт ЦОМ, м³")
    nsj_dev = number("НСЖ отклонение, м³")

    class Meta:
        verbose_name = "добыча за сутки"
        verbose_name_plural = "добыча за сутки"

    def __str__(self) -> str:
        """Дата и закрытие добычи."""
        return f"{self.report.date:%d.%m.%Y}: {self.closed_day} т"


class DeliveryDaily(models.Model):
    """Сдача нефти: на ПСП «Головные» и в систему «Транснефти»."""

    report = models.OneToOneField(Report, on_delete=models.CASCADE,
                                  related_name="delivery",
                                  verbose_name="Сутки")

    plan_day = number("План сдачи на сутки, т")
    fact_day = number("Факт сдачи за сутки, т")
    cumulative = number("Нарастающая сдача, т")
    dev_day = number("± к плану за сутки, т")
    dev_month = number("± к плану за месяц, т")
    from_cps = number("Перекачка с ЦПС, т")

    tn_plan_day = number("План в ТН на сутки, т")
    tn_plan_month = number("План в ТН на месяц, т")
    tn_fact_day = number("Факт в ТН за сутки, т")
    tn_cumulative = number("Нарастающая в ТН, т")
    tn_dev_day = number("± в ТН за сутки, т")
    tn_dev_month = number("± в ТН за месяц, т")

    forecast_total = number("Прогноз сдачи, т/сут")
    forecast_rate_tph = number("Откачка, т/ч")

    class Meta:
        verbose_name = "сдача за сутки"
        verbose_name_plural = "сдача за сутки"

    def __str__(self) -> str:
        """Дата и факт сдачи."""
        return f"{self.report.date:%d.%m.%Y}: {self.fact_day} т"


class PowerDaily(models.Model):
    """Энергетика: выработка и число работающих агрегатов."""

    report = models.OneToOneField(Report, on_delete=models.CASCADE,
                                  related_name="power", verbose_name="Сутки")

    generation_gas = number("Выработка на газе, МВт")
    generation_oil = number("Выработка на нефти, МВт")
    generation_diesel = number("Выработка на дизтопливе, МВт")

    count_gpea = number("ГПЭА + ГТУ + МГТУ в работе")
    count_nes = number("НЭС в работе")
    count_dies = number("ДЭС в работе")

    total_sh_zh = number("Выработка СХ+ЗХ, МВт·ч")
    total_sh_zh_delta = number("± выработки СХ+ЗХ, МВт·ч")
    total_with_psp = number("Выработка СХ+ЗХ+ПСП, МВт·ч")
    total_with_psp_delta = number("± выработки СХ+ЗХ+ПСП, МВт·ч")

    class Meta:
        verbose_name = "энергетика за сутки"
        verbose_name_plural = "энергетика за сутки"

    def __str__(self) -> str:
        """Дата и выработка."""
        return f"{self.report.date:%d.%m.%Y}: {self.total_with_psp} МВт·ч"


class HseDaily(models.Model):
    """Промышленная безопасность и охрана труда за сутки.

    Текст обращений в здравпункт содержит ФИО, год рождения и диагноз —
    специальную категорию персональных данных по 152-ФЗ. **Поля для
    этого текста здесь нет и не должно появиться**: если такие сведения
    окажутся в базе, система становится информационной системой
    персональных данных со всеми требованиями к аттестации. Хранится
    только количество обращений.
    """

    report = models.OneToOneField(Report, on_delete=models.CASCADE,
                                  related_name="hse", verbose_name="Сутки")
    incidents_count = models.PositiveIntegerField("Происшествий", default=0)
    medical_count = models.PositiveIntegerField("Обращений в здравпункт",
                                                default=0)

    class Meta:
        verbose_name = "ПБиОТ за сутки"
        verbose_name_plural = "ПБиОТ за сутки"

    def __str__(self) -> str:
        """Дата и число происшествий."""
        return f"{self.report.date:%d.%m.%Y}: {self.incidents_count} происш."


# --- Строчные показатели -----------------------------------------------------
class DailyRow(models.Model):
    """Общая часть таблиц, у которых на сутки приходится много строк."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               verbose_name="Сутки")
    source_row = models.PositiveIntegerField(
        "Строка в рапорте", null=True, blank=True,
        help_text="Нужна, чтобы показать, откуда взята цифра.")

    class Meta:
        abstract = True


class FieldProductionDaily(DailyRow):
    """Добыча нефти по месторождению за сутки."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="field_production",
                               verbose_name="Сутки")
    field = models.ForeignKey(Field, on_delete=models.PROTECT,
                              verbose_name="Месторождение")
    qo = number("Добыча, т/сут")

    class Meta:
        verbose_name = "добыча по месторождению"
        verbose_name_plural = "добыча по месторождениям"
        constraints = [models.UniqueConstraint(
            fields=("report", "field"), name="unique_field_production")]

    def __str__(self) -> str:
        """Месторождение и добыча."""
        return f"{self.field.name}: {self.qo} т"


class StockDaily(DailyRow):
    """Состояние фонда скважин по месторождению или итог за сутки."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="stock", verbose_name="Сутки")
    field = models.ForeignKey(Field, on_delete=models.PROTECT, null=True,
                              blank=True, verbose_name="Месторождение",
                              help_text="Пусто — строка итога по компании.")
    is_total = models.BooleanField("Итоговая строка", default=False)

    total = number("Общий фонд")
    operating_stock = number("Эксплуатационный фонд")
    in_work = number("В работе")
    in_work_delta = number("± в работе за сутки")
    in_downtime = number("В текущем простое")
    downtime_rate = number("Потери простоя, т/сут")
    in_idle = number("В бездействии")
    idle_rate = number("Потери бездействия, т/сут")
    idle_delta = number("± в бездействии за сутки")
    awaiting = number("В ожидании освоения")

    inj_total = number("Нагнетательные, всего")
    inj_in_work = number("Нагнетательные в работе")
    inj_downtime = number("Нагнетательные в простое")
    inj_idle = number("Нагнетательные в БД")

    observation = number("Наблюдательные")
    conservation = number("В консервации")
    liquidated = number("Ликвидированные")

    class Meta:
        verbose_name = "фонд скважин"
        verbose_name_plural = "фонд скважин"
        ordering = ("-is_total", "field__name")

    def __str__(self) -> str:
        """Месторождение или пометка итога."""
        return "ИТОГО" if self.is_total else str(self.field)


class WellDaily(DailyRow):
    """Скважина в одном из списков за сутки.

    Центральная таблица истории: связь со справочником скважин открывает
    то, чего в исходной таблице нет вообще, — накопленные потери
    по конкретной скважине и повторные отказы после ремонта.
    """

    class Category(models.TextChoices):
        """В каком списке рапорта стоит скважина."""

        DOWNTIME = "downtime", "Текущий простой"
        IDLE = "idle", "Бездействие"
        VSP = "vsp", "Внутрисменные потери"
        STARTUP = "startup", "Запуск"

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="wells", verbose_name="Сутки")
    well = models.ForeignKey(Well, on_delete=models.PROTECT,
                             related_name="daily", verbose_name="Скважина")
    category = models.CharField("Список", max_length=20,
                                choices=Category.choices, db_index=True)

    qo = number("Потери нефти, т/сут")
    ql = number("Жидкость, м³/сут")
    wc = number("Обводнённость, %")

    pump = models.CharField("Насос", max_length=100, blank=True)
    reason = models.CharField("Причина остановки", max_length=300, blank=True)
    code = models.CharField("Код", max_length=60, blank=True)
    well_category = models.CharField("Категория", max_length=100, blank=True)
    days = models.CharField("Длительность", max_length=60, blank=True)
    status = models.CharField("Состояние", max_length=300, blank=True)
    note = models.CharField("Примечание", max_length=500, blank=True)

    stop_date = models.DateField("Дата остановки", null=True, blank=True)
    last_repair = models.DateField("Дата последнего ремонта", null=True,
                                   blank=True)

    class Meta:
        verbose_name = "скважина за сутки"
        verbose_name_plural = "скважины за сутки"
        constraints = [models.UniqueConstraint(
            fields=("report", "well", "category"), name="unique_well_daily")]
        indexes = [models.Index(fields=("well", "report"))]

    def __str__(self) -> str:
        """Скважина и её список."""
        return f"{self.well.number} — {self.get_category_display()}"


class GroupEvent(DailyRow):
    """Событие сразу по нескольким скважинам.

    В списках рапорта встречаются строки, где вместо номера скважины
    записано «76 скважин» или «куст №1», а вместо месторождения —
    перечень: «СХ, Вис, ЗХ, Сюрх, ВЯ». Это не скважины, а групповые
    события — остановка куста, реконструкция ДНС, массовый перезапуск.

    Разносить их по отдельным скважинам нельзя: в рапорте не сказано,
    по каким именно. Но и терять нельзя: в августе 2026 такие строки
    несли 4 781 т потерь. Поэтому они хранятся как есть, отдельно
    от скважин, и в историю конкретной скважины не попадают.
    """

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="group_events",
                               verbose_name="Сутки")
    category = models.CharField("Список", max_length=20,
                                choices=WellDaily.Category.choices,
                                db_index=True)
    subject = models.CharField("Как записано", max_length=200)
    fields_text = models.CharField("Месторождения, как записано",
                                   max_length=300, blank=True)
    field = models.ForeignKey(Field, on_delete=models.PROTECT, null=True,
                              blank=True, verbose_name="Месторождение",
                              help_text="Заполнено, если событие относится "
                                        "к одному месторождению.")
    wells_count = number("Скважин в событии")

    qo = number("Потери нефти, т/сут")
    ql = number("Жидкость, м³/сут")
    wc = number("Обводнённость, %")

    reason = models.CharField("Причина", max_length=300, blank=True)
    code = models.CharField("Код", max_length=60, blank=True)
    days = models.CharField("Длительность", max_length=60, blank=True)
    status = models.CharField("Состояние", max_length=300, blank=True)
    note = models.CharField("Примечание", max_length=500, blank=True)

    class Meta:
        verbose_name = "групповое событие"
        verbose_name_plural = "групповые события"
        ordering = ("-qo",)

    def __str__(self) -> str:
        """Как записано в рапорте и потери."""
        return f"{self.subject}: {self.qo} т/сут"


class RampUpDaily(DailyRow):
    """Скважина на выводе на режим или под контролем после ГТМ."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="ramp_up", verbose_name="Сутки")
    well = models.ForeignKey(Well, on_delete=models.PROTECT,
                             related_name="ramp_up", verbose_name="Скважина")

    plan_ql = number("План жидкости, м³/сут")
    plan_qo = number("План нефти, т/сут")
    fact_ql = number("Факт жидкости, м³/сут")
    fact_qo = number("Факт нефти, т/сут")
    fact_wc = number("Обводнённость, %")

    pump = models.CharField("Насос", max_length=100, blank=True)
    gtm = models.CharField("Вид ГТМ", max_length=150, blank=True)
    days = models.CharField("Суток на выводе", max_length=60, blank=True)
    note = models.CharField("Примечание", max_length=500, blank=True)

    class Meta:
        verbose_name = "вывод на режим"
        verbose_name_plural = "вывод на режим"
        constraints = [models.UniqueConstraint(
            fields=("report", "well"), name="unique_ramp_up")]

    def __str__(self) -> str:
        """Скважина и факт добычи."""
        return f"{self.well.number}: {self.fact_qo} т/сут"


class DowntimeBreakdownDaily(DailyRow):
    """Разбивка простоя по причинам за сутки.

    Состав причин в рапорте меняют, поэтому справочник причин пополняется
    сам. Сумма по причинам сверяется с общим простоем — расхождение
    попадает в замечания.
    """

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="downtime_breakdown",
                               verbose_name="Сутки")
    reason = models.ForeignKey(DowntimeReason, on_delete=models.PROTECT,
                               verbose_name="Причина")
    wells_count = number("Скважин")
    qo = number("Потери, т/сут")

    class Meta:
        verbose_name = "причина простоя за сутки"
        verbose_name_plural = "разбивка простоя по причинам"
        ordering = ("-qo",)
        constraints = [models.UniqueConstraint(
            fields=("report", "reason"), name="unique_downtime_reason")]

    def __str__(self) -> str:
        """Причина и потери."""
        return f"{self.reason.name}: {self.qo} т/сут"


class InjectionDaily(DailyRow):
    """Закачка по объекту поддержания пластового давления."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="injection", verbose_name="Сутки")
    object = models.ForeignKey(InjectionObject, on_delete=models.PROTECT,
                               null=True, blank=True,
                               verbose_name="Объект ППД",
                               help_text="Пусто — строка «Всего».")
    is_total = models.BooleanField("Итоговая строка", default=False)

    plan_day = number("Режим за сутки, м³")
    fact_day = number("Факт за сутки, м³")
    dev_day = number("± к режиму за сутки, м³")
    plan_month = number("Режим за месяц, м³")
    fact_month = number("Факт за месяц, м³")
    dev_month = number("± к режиму за месяц, м³")
    oil_in_water = number("Нефть в воде, мг/дм³")
    kvch = number("КВЧ, мг/дм³")

    class Meta:
        verbose_name = "закачка ППД"
        verbose_name_plural = "закачка ППД"
        ordering = ("is_total", "object__name")

    def __str__(self) -> str:
        """Объект и факт закачки."""
        name = "Всего" if self.is_total else str(self.object)
        return f"{name}: {self.fact_day} м³"


class TankDaily(DailyRow):
    """Резервуар товарного парка на 6:00."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="tanks", verbose_name="Сутки")
    tank = models.ForeignKey(Tank, on_delete=models.PROTECT,
                             verbose_name="Резервуар")
    level = number("Взлив, м")
    volume = number("Объём, м³")
    delta = number("± к прошлым суткам, м³")
    free = number("Свободный объём, м³")

    class Meta:
        verbose_name = "резервуар за сутки"
        verbose_name_plural = "резервуарный парк"
        constraints = [models.UniqueConstraint(
            fields=("report", "tank"), name="unique_tank_daily")]

    def __str__(self) -> str:
        """Резервуар и объём."""
        return f"{self.tank.name}: {self.volume} м³"


class QualityDaily(DailyRow):
    """Качество товарной нефти по узлу учёта."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="quality", verbose_name="Сутки")
    node = models.ForeignKey(MeteringNode, on_delete=models.PROTECT,
                             verbose_name="Узел учёта")

    density = number("Плотность, кг/м³")
    water = number("Вода, %")
    solids = number("Механические примеси, %")
    sulfur = number("Сера, %")
    paraffin = number("Парафины, %")
    h2s = number("Сероводород, ppm")
    mercaptans = number("Меркаптаны, ppm")
    chlorides = number("Органические хлориды, ppm")
    salts = number("Хлористые соли, мг/дм³")

    class Meta:
        verbose_name = "качество нефти"
        verbose_name_plural = "качество товарной нефти"
        constraints = [models.UniqueConstraint(
            fields=("report", "node"), name="unique_quality_daily")]

    def __str__(self) -> str:
        """Узел учёта и плотность."""
        return f"{self.node.name}: {self.density} кг/м³"


class GasDaily(DailyRow):
    """Строка баланса попутного нефтяного газа."""

    class Kind(models.TextChoices):
        """Какая часть баланса."""

        PRODUCTION = "production", "Добыча газа"
        UTILIZATION = "utilization", "Утилизация (с/н + потери)"
        FLARE = "flare", "Факел"

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="gas", verbose_name="Сутки")
    kind = models.CharField("Показатель", max_length=20, choices=Kind.choices)

    day_plan = number("БП за сутки, тыс. м³")
    day_fact = number("Факт за сутки, тыс. м³")
    day_dev = number("± к БП за сутки, тыс. м³")
    month_fact = number("Факт за месяц, тыс. м³")
    year_fact = number("Факт за год, тыс. м³")

    class Meta:
        verbose_name = "газ за сутки"
        verbose_name_plural = "попутный нефтяной газ"
        constraints = [models.UniqueConstraint(
            fields=("report", "kind"), name="unique_gas_daily")]

    def __str__(self) -> str:
        """Показатель и факт."""
        return f"{self.get_kind_display()}: {self.day_fact} тыс. м³"


class DieselStockDaily(DailyRow):
    """Остаток дизельного топлива на объекте энергетики."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="diesel_stock",
                               verbose_name="Сутки")
    object = models.ForeignKey(PowerObject, on_delete=models.PROTECT,
                               verbose_name="Объект")
    tons = number("Остаток, т")

    class Meta:
        verbose_name = "остаток дизтоплива"
        verbose_name_plural = "остатки дизтоплива"
        constraints = [models.UniqueConstraint(
            fields=("report", "object"), name="unique_diesel_stock")]

    def __str__(self) -> str:
        """Объект и остаток."""
        return f"{self.object.name}: {self.tons} т"


class DrillingDaily(DailyRow):
    """Скважина в бурении за сутки."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="drilling", verbose_name="Сутки")
    contractor = models.ForeignKey(Contractor, on_delete=models.PROTECT,
                                   verbose_name="Подрядчик")
    field = models.ForeignKey(Field, on_delete=models.PROTECT,
                              verbose_name="Месторождение")
    well_number = models.CharField("Скважина", max_length=40)

    target_depth = number("Проектная глубина, м")
    current_depth = number("Забой на 6:00, м")
    current_depth_text = models.CharField("Забой, как записано",
                                          max_length=100, blank=True)
    start_date = models.DateField("Начало бурения", null=True, blank=True)

    class Meta:
        verbose_name = "бурение за сутки"
        verbose_name_plural = "бурение"

    def __str__(self) -> str:
        """Скважина и забой."""
        return f"скв. {self.well_number}: {self.current_depth} м"


class PiggingDaily(DailyRow):
    """Пуск очистного устройства по участку трубопровода."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="pigging", verbose_name="Сутки")
    line = models.CharField("Трубопровод", max_length=200, blank=True)
    section = models.CharField("Участок", max_length=300, blank=True)
    launch = models.DateTimeField("Пуск", null=True, blank=True)
    receive = models.DateTimeField("Приём", null=True, blank=True)
    travel_h = number("В пути, ч")
    note = models.CharField("Примечание", max_length=500, blank=True)

    class Meta:
        verbose_name = "очистное устройство"
        verbose_name_plural = "очистные устройства"

    def __str__(self) -> str:
        """Участок трубопровода."""
        return self.section or self.line or "участок не указан"


# --- Служебное ---------------------------------------------------------------
class LoadIssue(DailyRow):
    """Замечание к качеству исходных данных, найденное при загрузке.

    Хранится вместе с данными: расхождения в рапорте видны не только
    в день загрузки, но и потом — например, при разборе, почему сводка
    за месяц не сходится.
    """

    class Level(models.TextChoices):
        """Насколько серьёзно замечание."""

        INFO = "info", "К сведению"
        WARNING = "warning", "Предупреждение"
        ERROR = "error", "Ошибка"

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="issues", verbose_name="Сутки")
    level = models.CharField("Уровень", max_length=10, choices=Level.choices,
                             default=Level.WARNING)
    where = models.CharField("Блок рапорта", max_length=200)
    message = models.TextField("Замечание")

    class Meta:
        verbose_name = "замечание к данным"
        verbose_name_plural = "замечания к данным"
        ordering = ("level", "where")

    def __str__(self) -> str:
        """Место и текст замечания."""
        return f"{self.where}: {self.message[:80]}"


class ProvenanceEntry(DailyRow):
    """Происхождение одного показателя.

    Требование доклада: любую цифру можно проверить по рапорту. Здесь
    записано, откуда она взялась, — адрес ячейки, диапазон суммирования
    или формула расчёта. Без этой записи показатель на страницу
    не выносится.
    """

    class Kind(models.TextChoices):
        """Каким способом получено значение."""

        CELL = "cell", "Значение ячейки"
        SUM = "sum", "Сумма по строкам"
        COUNT = "count", "Количество строк"
        DERIVED = "derived", "Расчёт"
        MANUAL = "manual", "Указано оператором"

    report = models.ForeignKey(Report, on_delete=models.CASCADE,
                               related_name="provenance",
                               verbose_name="Сутки")
    section = models.CharField("Раздел", max_length=100)
    label = models.CharField("Показатель", max_length=200)
    value = models.CharField("Значение", max_length=100)
    kind = models.CharField("Способ", max_length=20, choices=Kind.choices,
                            default=Kind.CELL)
    origin = models.CharField("Откуда", max_length=500)

    class Meta:
        verbose_name = "происхождение показателя"
        verbose_name_plural = "происхождение показателей"
        ordering = ("section", "label")

    def __str__(self) -> str:
        """Показатель и его источник."""
        return f"{self.label} ← {self.origin[:60]}"
