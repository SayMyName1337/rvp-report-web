# -*- coding: utf-8 -*-
"""Схема суточного рапорта в терминах подписей, а не адресов ячеек.

Каждый блок находится по своему заголовку, каждый столбец — по тексту шапки.
Адреса из поля reference — эталон по файлам 21–25.07.2026: они используются
только как запасной вариант, если подпись не найдена, и в этом случае
программа выдаёт предупреждение.

Правка этого файла — единственное, что требуется при изменении шаблона Excel.
"""
from __future__ import annotations

from .spec import Block, Col, Cross, Find, Scalar, Table

SHEET_CANDIDATES = ("Сут.рапорт", "Суточный рапорт", "Сут. рапорт")
# по этим подписям лист опознаётся, если его переименуют
SHEET_MARKERS = ("СОСТОЯНИЕ ФОНДА СКВАЖИН", "Закрытие добычи нефти по сводке")

# Заголовки, которые всегда стоят в самом левом столбце данных. По их
# фактическому положению определяется сдвиг столбцов: вставка столбца слева
# не должна ломать разбор так же, как его не ломает вставка строк. Список
# длинный намеренно — переименование одного заголовка не искажает сдвиг.
LEFT_COLUMN_MARKERS = (
    "СОСТОЯНИЕ ФОНДА СКВАЖИН",
    "План добычи СГ",
    "Расход газа по потребителям",
    "Буровой подрядчик",
    "Качество сдаваемой нефти",
    "Текущий простой",
    "Бездействие",
)

# --- Разделы -----------------------------------------------------------------
BLOCKS: tuple[Block, ...] = (
    Block("hse", "ПБиОТ",
          Find("ДЗО", cols="A"), 4),
    Block("production", "Добыча и сдача",
          Find("План добычи СГ", mode="starts", cols="A"), 12),
    Block("stock", "Фонд скважин",
          Find("СОСТОЯНИЕ ФОНДА СКВАЖИН", mode="starts", cols="A"), 24),
    Block("startups", "Запуск скважин",
          Find("Запуск скважин", cols="A"), 47),
    Block("shutdowns", "Остановки скважин",
          Find("Остановки скважин", cols="A"), 63),
    Block("idle", "Бездействие",
          Find("Бездействие", cols="A"), 66),
    Block("downtime", "Текущий простой",
          Find("Текущий простой", cols="A"), 131),
    Block("vsp", "Внутрисменные потери",
          Find("ВСП", cols="A"), 449),
    Block("rampup", "Вывод на режим",
          Find("Вывод на режим", cols="A"), 496),
    Block("muslyd", "Мусюршор и Лыдушор",
          Find("Мус+Лыд", cols="A"), 508),
    Block("control", "Контроль и ГТМ",
          Find("Контроль + ГТМ", cols="A"), 526),
    Block("injection", "ППД",
          Find("ППД", cols="A"), 537),
    Block("pipelines", "Трубопроводы",
          Find("Скважины ППД", cols="A"), 543),
    Block("tanks", "Резервуарный парк",
          Find("Резервуарный парк", mode="starts", cols="A:C"), 555),
    Block("quality", "Качество нефти",
          Find("Качество сдаваемой нефти", mode="starts", cols="A"), 572,
          ends_before="gasuse"),
    Block("gas", "Попутный газ",
          Find("Добыча попутного газа", mode="starts", cols="M"), 572,
          ends_before="gasuse"),
    Block("gasuse", "Расход газа",
          Find("Расход газа по потребителям", mode="starts", cols="A"), 579),
    Block("power", "Энергетика",
          Find("ЭЦ ЦПС", mode="starts", cols="A"), 580),
    Block("pigging", "Очистные устройства",
          Find("ОУ", cols="A"), 612),
    Block("drilling", "Бурение",
          Find("Буровой подрядчик", cols="A"), 656),
)

# --- Шапка -------------------------------------------------------------------
HEADER = {
    "temperature": Scalar(Find("Погода", cols="A"), dc=1, reference="B1"),
    "wind": Scalar(Find("Погода", cols="A"), dc=2, reference="C1"),
    "date": Scalar(Find("Погода", cols="A"), dc=4, reference="E1"),
}

# --- Добыча ------------------------------------------------------------------
PRODUCTION = {
    "plan_sg_day": Scalar(Find("План добычи СГ", "starts"), dc=2,
                          block="production", reference="C12"),
    "plan_sg_month": Scalar(Find("План добычи СГ", "starts"), dc=3,
                            block="production", reference="D12"),
    "plan_bp_day": Scalar(Find("БП (сут/мес)", "starts"), dc=1,
                          block="production", reference="F12"),
    "plan_bp_month": Scalar(Find("БП (сут/мес)", "starts"), dc=2,
                            block="production", reference="G12"),

    "closed_day": Scalar(Find("Закрытие добычи нефти по сводке за сутки", "starts"),
                         dr=2, block="production", reference="A15"),
    "dev_sg_day": Scalar(Find("+,- к СГ за сутки", "starts"), dr=2,
                         block="production", reference="C15"),
    "dev_sg_month": Scalar(Find("+,- к СГ с н.м", "starts"), dr=2,
                           block="production", reference="D15"),
    "dev_bp_day": Scalar(Find("+,- к БП за сутки", "starts"), dr=2,
                         block="production", reference="C16"),
    "dev_bp_month": Scalar(Find("+,- к БП с н.м", "starts"), dr=2,
                           block="production", reference="D16"),
    "fact_com_day": Scalar(Find("Факт. добыча нефти за сутки ЦОМ", "starts"),
                           dr=2, block="production", reference="E15"),
    "dev_bp_year": Scalar(Find("Добыча +/- к бизнес", "starts"), dr=2,
                          block="production", reference="F15"),
    "cumulative_month": Scalar(Find("Нарастающая добыча за месяц", "starts"),
                               dr=2, block="production", reference="G15"),

    "forecast_0600": Scalar(Find("Прогноз добычи", "starts"), dr=2,
                            block="production", reference="C19"),
    "potential_com": Scalar(Find("Факт ЦОМ"), dr=1,
                            block="production", reference="G19"),
    "potential_limited": Scalar(Find("С учётом ограничений", "starts"), dr=1,
                                block="production", reference="H19"),

    "nsj_closed": Scalar(Find("Закрытие НСЖ", "starts"), dr=2,
                         block="production", reference="C22"),
    "nsj_fact": Scalar(Find("НСЖ ЦОМ факт", "starts"), dr=2,
                       block="production", reference="E22"),
    "nsj_dev": Scalar(Find("Откл. НСЖ", "starts"), dr=2,
                      block="production", reference="G22"),
}

# Добыча по месторождениям: подписи в шапке, значения через две строки
FIELDS_ROW = Scalar(Find("Закрытие добычи нефти по сводке за сутки", "starts"),
                    block="production", reference="A13")
FIELDS_VALUE_OFFSET = 2

FIELD_NAMES = {
    "СХ": "Северо-Хоседаюское",
    "ВИС": "Висовое",
    "В.Колв.": "Верхне-Колвинское",
    "ЗХ": "Западно-Хоседаюское",
    "Сих": "Сихорейское",
    "Вост.Сих": "Восточно-Сихорейское",
    "Сев.Сих": "Северо-Сихорейское",
    "Сев.Ош.": "Северо-Ошкотынское",
    "Сюрх": "Сюрхаратинское",
    "Юж.Сюрх.": "Южно-Сюрхаратинское",
    "Пюсейское": "Пюсейское",
    "Урер": "Урернырдское",
    "Вост.Ян.": "Восточно-Янемдейское",
    "Мус": "Мусюршорское",
    "Лыд": "Лыдушорское",
}

# --- Сдача -------------------------------------------------------------------
_DELIVERY_COLS = {
    "plan_day": Find("План сдачи нефти за сутки", "starts"),
    "fact_day": Find("Сдача нефти за сутки", "starts"),
    "cumulative": Find("Нарастающая, т", "starts"),
    "dev_day": Find("+,- к плану с за сутки", "starts"),
    "dev_month": Find("+,- к плану с н.м", "starts"),
    "from_cps": Find("Сдача нефти с ЦПС за сутки", "starts"),
}
_DELIVERY_REF = {"plan_day": "P", "fact_day": "Q", "cumulative": "R",
                 "dev_day": "S", "dev_month": "T", "from_cps": "U"}

DELIVERY = {
    name: Cross(row=Find("Сдача с ПСП Мусюршор", "starts"), col=find,
                block="production", reference=f"{_DELIVERY_REF[name]}18")
    for name, find in _DELIVERY_COLS.items()
}
DELIVERY.update({
    f"tn_{name}": Cross(row=Find("Сдача в ТН", "starts"), col=find,
                        block="production",
                        reference=f"{_DELIVERY_REF[name]}21")
    for name, find in _DELIVERY_COLS.items() if name != "from_cps"
})
DELIVERY["tn_plan_month"] = Scalar(Find("План сдачи в ТН на месяц", "starts"),
                                   dr=1, block="production", reference="U22")
DELIVERY["forecast_total"] = Cross(row=Find("Всего", cols="B"),
                                   col=Find("Прогноз сдачи, т/сут", "starts"),
                                   block="tanks", reference="D564")
DELIVERY["forecast_rate_tph"] = Cross(row=Find("Всего", cols="B"),
                                      col=Find("Откачка, т/ч", "starts"),
                                      block="tanks", reference="E564")

# --- Фонд скважин ------------------------------------------------------------
STOCK = Table(
    block="stock",
    key_column="name",
    total=Find("ООО", mode="starts", cols="A"),
    reference_rows=(29, 46),
    columns={
        "name": Col("Месторождение", reference="A"),
        "total": Col("Общий фонд", reference="D"),
        "operating_stock": Col("Эксплуатационный фонд", reference="F"),
        "in_work": Col("в работе", parent="Нефтяные", reference="H"),
        "in_work_delta": Col("изм", parent="Нефтяные", nth=0, reference="I"),
        "in_downtime": Col("в тек.простое", parent="Нефтяные", reference="J"),
        "downtime_rate": Col("т/сут", parent="Нефтяные", nth=0, reference="K"),
        "in_idle": Col("в БД", parent="Нефтяные", reference="L"),
        "idle_rate": Col("т/сут", parent="Нефтяные", nth=1, reference="M"),
        "idle_delta": Col("изм", parent="Нефтяные", nth=1, reference="N"),
        "awaiting": Col("в ожид.освоения", parent="Нефтяные", reference="O"),
        "inj_total": Col("Всего", parent="Нагнетательные", reference="P"),
        "inj_in_work": Col("в работе", parent="Нагнетательные", reference="Q"),
        "inj_downtime": Col("в простое", parent="Нагнетательные", reference="R"),
        "inj_idle": Col("в БД", parent="Нагнетательные", reference="S"),
        "observation": Col("Наблюд", reference="T"),
        "conservation": Col("В консервации", reference="U"),
        "liquidated": Col("Ликвидированные", reference="V"),
    },
)

# --- Списки скважин ----------------------------------------------------------
_WELL_COLUMNS = {
    "stop_date": Col("Дата остановки", pick="last", reference="H"),
    "well": Col("№ скв-ны", alt=("№ скважины",), reference="I"),
    "pump": Col("ГНО", alt=("Тип установки",), reference="J"),
    "field": Col("Месторождение", reference="K"),
    "qo": Col("Qн, тонн", parent="Режим", reference="L"),
    "ql": Col("Qж, м3", parent="Режим", reference="M"),
    "wc": Col("% обв", parent="Режим", reference="N"),
    "reason": Col("Причина остановки", reference="O"),
    "code": Col("Код", reference="P"),
    "category": Col("Категория", reference="Q"),
    "days": Col("Сутки, наработка", reference="R"),
    "status": Col("Текущий статус", reference="S"),
    "last_repair": Col("Дата последнего ремонта", reference="T"),
    "note": Col("Примечание", reference="U"),
}

IDLE = Table(block="idle", columns=dict(_WELL_COLUMNS),
             key_column="well", require=("field",),
             require_text=("field",),
             total=Find("ИТОГО в Бездействии", "starts", cols="A"),
             reference_rows=(68, 129))

DOWNTIME = Table(block="downtime", columns=dict(_WELL_COLUMNS),
                 key_column="well", require=("field",),
                 require_text=("field",),
                 total=Find("ИТОГО в Текущем простое", "starts", cols="A"),
                 reference_rows=(133, 445))

# Готовая разбивка простоя по причинам — подписи внутри блока,
# следом за подписью идут два числа: количество скважин и потери, т
#: Сколько строк над ИТОГО просматривать в поисках сводки по причинам.
BREAKDOWN_DEPTH = 6

DOWNTIME_BREAKDOWN = (
    Find("Текущий простой по ограничению", "starts"),
    Find("КРС, ОКРС", "starts"),
    Find("КВД"),
    Find("Сезонная эксплуатация", "starts"),
)

VSP = Table(
    block="vsp", key_column="well", require=("field",),
    require_text=("field",),
    reference_rows=(452, 494),
    columns={
        "well": Col("№ скв-ны", reference="F"),
        "pump": Col("Тип установки", reference="G"),
        "field": Col("Месторождение", reference="H"),
        "qo": Col("Qн, тонн", parent="Режим", reference="I"),
        "ql": Col("Qж, м3", parent="Режим", reference="J"),
        "wc": Col("% обводненности", parent="Режим", reference="K"),
        "loss_qo": Col("Qн, тонн", parent="Потери", reference="L"),
        "loss_ql": Col("Qж, м3", parent="Потери", reference="M"),
        "reason": Col("Причина остановки", reference="N"),
        "code": Col("Код", reference="O"),
        "category": Col("Категория", reference="P"),
        "stop_time": Col("остан", parent="Время", reference="R"),
        "start_time": Col("пуск", parent="Время", reference="S"),
        "duration": Col("Простой", reference="T"),
        "note": Col("Примечание", reference="V"),
    },
)

# --- Движение фонда ----------------------------------------------------------
STARTUPS = Table(
    block="startups", key_column="well", reference_rows=(49, 61),
    total=Find("ИТОГО", cols="E"),
    columns={
        "well": Col("№скв", reference="E"),
        "field": Col("Местор-е", reference="F"),
        "ql": Col("Замер, м3/сут", parent="Пусковые параметры", reference="O"),
        "qo": Col("Q нефти, тн", parent="Пусковые параметры", reference="P"),
        "wc": Col("Н2О, %", parent="Пусковые параметры", reference="Q"),
        "reason": Col("Вид ремонта", reference="R"),
        "note": Col("Примечание", reference="U"),
    },
)

SHUTDOWN_ROWS = {
    "svodka": Find("Сводка", cols="E"),
    "fact": Find("Факт", cols="E"),
    "total": Find("ИТОГО", cols="E"),
}

# --- Вывод на режим, Мус+Лыд, контроль ---------------------------------------
_RAMP_COLUMNS = {
    "field": Col("Местор-е", alt=("Месторождение",), reference="B"),
    "well": Col("№скв", reference="C"),
    "plan_ql": Col("Qож, м3", alt=("Qж.реж, м3",), reference="D"),
    "plan_qo": Col("Qож, тн", alt=("Qн, тн", "Qн.реж, тн"), reference="E"),
    "plan_wc": Col("Н2О, %ож", alt=("Н20%реж",), reference="F"),
    "pump": Col("Тип установки", reference="G"),
    "gtm": Col("вид ГТМ", reference="H"),
    "days": Col("Дней в освоении", reference="I"),
    "fact_ql": Col("Замер, м3/сут", alt=("Замер АГЗУ, м3/сут",), reference="L"),
    "fact_qo": Col("Q нефти, тн/сут", alt=("Q нефти, тн",), reference="M"),
    "fact_wc": Col("Н2О, %", mode="exact", reference="N"),
    "freq": Col("част, Гц", reference="R"),
    "note": Col("Примечание", reference="V"),
}

RAMP_UP = Table(block="rampup", columns=dict(_RAMP_COLUMNS), key_column="well",
                require=("field",), total=Find("ИТОГО", cols="B"),
                reference_rows=(497, 506))

# у блока Мус+Лыд столбец с площадкой не подписан — определяется по данным
MUS_LYD = Table(block="muslyd",
                columns={**_RAMP_COLUMNS,
                         "field": Col(anchor_col=True, reference="B"),
                         "days": Col("Дней в освоении", optional=True)},
                key_column="well", require=("field",),
                total=Find("ИТОГО", cols="B"), reference_rows=(509, 520))

CONTROL_GTM = Table(block="control", columns=dict(_RAMP_COLUMNS),
                    key_column="well", require=("field",),
                    total=Find("ИТОГО", cols="B"), reference_rows=(527, 531))

# --- ППД ---------------------------------------------------------------------
INJECTION = Table(
    block="injection", key_column="name", reference_rows=(538, 541),
    total=Find("Всего", cols="B"),
    columns={
        "name": Col(anchor_col=True, reference="B"),
        "plan_day": Col("Режим сутки, м3", reference="D"),
        "fact_day": Col("Закачка", mode="starts", reference="F"),
        "dev_day": Col("+/- к режиму за сутки", mode="starts", reference="G"),
        "plan_month": Col("Режим месяц, м3", reference="H"),
        "fact_month": Col("Факт", mode="starts", reference="I"),
        "dev_month": Col("+/- к режиму за месяц", mode="starts", reference="J"),
        "level": Col("Взлив, м", reference="K"),
        "oil_in_water": Col("Конц. нефти в воде", mode="starts", reference="P"),
        "kvch": Col("КВЧ", mode="starts", reference="Q"),
    },
)

# --- Резервуарный парк -------------------------------------------------------
TANKS_LEFT = Table(
    block="tanks", key_column="name", require_number=("level",),
    reference_rows=(557, 559), cols="A:E",
    columns={
        "name": Col("Взлив, м", dc=-1, reference="A"),
        "level": Col("Взлив, м", reference="B"),
        "volume": Col("Vж, м3", reference="C"),
        "delta": Col("+/- к пр. сут", mode="starts", reference="D"),
        "free": Col("Свободный объем", mode="starts", reference="E"),
    },
)
TANKS_RIGHT = Table(
    block="tanks", key_column="name", require_number=("level",),
    reference_rows=(557, 559), cols="F:J",
    columns={
        "name": Col("Взлив, м", dc=-1, reference="F"),
        "level": Col("Взлив, м", reference="G"),
        "volume": Col("Vж, м3", reference="H"),
        "delta": Col("+/- к пр. сут", mode="starts", reference="I"),
        "free": Col("Свободный объем", mode="starts", reference="J"),
    },
)
FREE_VOLUME_TOTAL = Scalar(Find("Свободный объем по всем объектам", "starts"),
                           dc=3, block="tanks", reference="I560")

# --- Качество нефти ----------------------------------------------------------
OIL_QUALITY = Table(
    block="quality", key_column="node", reference_rows=(575, 578), cols="A:L",
    columns={
        "node": Col(anchor_col=True, reference="A"),
        "density": Col("ρ при 20", mode="starts", reference="B"),
        "water": Col("Массовая доля воды", mode="starts", reference="C"),
        "solids": Col("Массовая доля мех", mode="starts", reference="D"),
        "sulfur": Col("Массовая доля серы", mode="starts", reference="F"),
        "paraffin": Col("Массовая доля парафина", mode="starts", reference="G"),
        "h2s": Col("Массовая доля сероводорода", mode="starts", reference="H"),
        "mercaptans": Col("Массовая доля метил", mode="starts", reference="I"),
        "chlorides": Col("Массовая доля орг", mode="starts", reference="K"),
        "salts": Col("Масс. конц. хлор", mode="starts", reference="L"),
    },
)
# --- Газ ---------------------------------------------------------------------
GAS = Table(
    block="gas", key_column="name", reference_rows=(575, 578), cols="M:V",
    columns={
        "name": Col(anchor_col=True, reference="M"),
        "day_plan": Col("БП", parent="Сутки, тыс. м3", reference="N"),
        "day_fact": Col("Факт", parent="Сутки, тыс. м3", reference="O"),
        "day_dev": Col("Откл", parent="Сутки, тыс. м3", reference="P"),
        "month_fact": Col("Факт", parent="Месяц, тыс. м3", reference="R"),
        "year_fact": Col("Факт", parent="Год, тыс. м3", reference="U"),
    },
)
GAS_CONSUMERS_TOTAL = Scalar(Find("Всего", cols="M"), search="right",
                             block="gasuse", reference="N579")
DIESEL_LEFT = Scalar(Find("Остаток ДТ", "starts", cols="U"), dc=1,
                     block="gasuse", reference="V579")

# --- Энергетика --------------------------------------------------------------
POWER = {
    # подпись и значение здесь разнесены по-разному, поэтому берётся
    # ближайшее число под подписью, а не фиксированное смещение
    "total_sh_zh": Scalar(Find("Общая выработка эл/энергии, МВт/час (СХ+ЗХ)",
                               mode="starts"), search="down",
                          block="power", reference="U592"),
    "total_with_psp": Scalar(Find("Общая выработка эл/энергии, МВт/час (СХ+ЗХ+ПСП)",
                                  mode="starts"), search="down",
                             block="power", reference="U594"),
    "generation_gas": Scalar(Find("на Газу", mode="starts"), search="right",
                             block="power", reference="V588"),
    "generation_oil": Scalar(Find("на нефти", mode="starts"), search="right",
                             block="power", reference="V589"),
    "generation_diesel": Scalar(Find("на ДТ", mode="starts"), search="right",
                                block="power", reference="V587"),
    "count_dies": Scalar(Find("Кол-во ДЭС в работе", mode="starts"),
                         search="right", block="power", reference="T587"),
    "count_gpea": Scalar(Find("Кол-во ГПЭА", mode="starts"), search="right",
                         block="power", reference="T588"),
    "count_nes": Scalar(Find("Кол-во НЭС в работе", mode="starts"),
                        search="right", block="power", reference="T589"),
}
# отклонение к прошлым суткам стоит справа от самого значения
POWER_DELTA_DC = 1

DIESEL_STOCK = Scalar(Find("Остатки на 24:00", "starts"), dr=1,
                      block="power", reference="S585")
POWER_NOTES = (
    Find("ГПЭА", cols="P"), Find("ДЭА", cols="P"), Find("МГТУ", cols="P"),
    Find("КМ", "starts", cols="P"),
)

# --- Очистные устройства -----------------------------------------------------
PIGGING = Table(
    block="pigging", key_column="launch", reference_rows=(614, 655),
    columns={
        "line": Col("Дата пуска", mode="starts", dc=-2, reference="A"),
        "launch": Col("Дата пуска", mode="starts", reference="C"),
        "receive": Col("Дата приёма", mode="starts", reference="E"),
        "section": Col("НСК", reference="G"),
        "travel_h": Col("Время в пути", mode="starts", reference="J"),
        "note": Col("Примечание", reference="K"),
    },
)
PIGGING_MAX_HOURS = 240.0

# --- Бурение -----------------------------------------------------------------
DRILLING = Table(
    block="drilling", key_column="well", reference_rows=(657, 663),
    columns={
        "contractor": Col("Буровой подрядчик", mode="starts", reference="A"),
        "field": Col("Месторождение", reference="E"),
        "well": Col("№ скважины", mode="starts", reference="F"),
        "target_depth": Col("Проектная глубина", mode="starts", reference="G"),
        "current_depth": Col("Забой на", mode="starts", reference="I"),
        "start_date": Col("Дата начала бурения", mode="starts", reference="K"),
        "works": Col("Описание работ", mode="starts", reference="M"),
    },
)

# --- ПБиОТ -------------------------------------------------------------------
HSE = Table(
    block="hse", key_column="dzo", reference_rows=(5, 11),
    columns={
        "dzo": Col("ДЗО", reference="A"),
        "field": Col("Месторождение", mode="starts", reference="B"),
        "area": Col("Область события", mode="starts", reference="D"),
        "type": Col("Тип", reference="F"),
        "description": Col("Описание происшествия", mode="starts", reference="G"),
        "consequences": Col("Последствия", mode="starts", reference="K"),
        "comments": Col("Комментарии", mode="starts", reference="N"),
    },
)
# текст лежит в строке под заголовком столбца, а не в самом заголовке
HSE_MEDICAL = Scalar(Find("Обращения в медпункт", mode="starts"), dr=1,
                     block="hse", reference="P5")

#: Понятные названия показателей для отчёта о происхождении.
#: Нужны там, где подпись в самом рапорте неоднозначна: например,
#: температура, ветер и дата подписаны одним словом «Погода».
METRIC_LABELS = {
    "temperature": "Температура воздуха",
    "wind": "Ветер",
    "date": "Дата рапорта",
    "plan_sg_day": "План СГ на сутки",
    "plan_sg_month": "План СГ на месяц",
    "plan_bp_day": "План БП на сутки",
    "plan_bp_month": "План БП на месяц",
    "potential_com": "Потенциальная добыча на утро (факт ЦОМ)",
    "potential_limited": "Потенциальная добыча с учётом ограничений",
    "dev_bp_year": "Добыча ± к бизнес-плану с начала года",
    "forecast_0600": "Прогноз добычи на 6:00",
    "total_sh_zh": "Выработка электроэнергии СХ+ЗХ",
    "total_with_psp": "Выработка электроэнергии СХ+ЗХ+ПСП",
    "generation_gas": "Выработка на газу",
    "generation_oil": "Выработка на нефти",
    "generation_diesel": "Выработка на дизтопливе",
}

# год, за пределами которого дата считается опечаткой (в файлах есть «13.02.2107»)
MAX_PLAUSIBLE_YEAR = 2100
