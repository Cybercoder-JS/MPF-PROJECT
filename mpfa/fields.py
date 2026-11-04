# -*- coding: utf-8 -*-
"""強積金基金平台欄位定義：繁體中文原文 <-> 英文欄位名映射。

欄位依 mpp_list.jsp「基金資訊表」的實際欄目定義。

曆年回報的年份每年會往前推，所以不寫死：`fund_columns(years)` 依實際解析到
的年份產生欄位順序，解析層把年份一併回傳，下游（輸出、驗證）用那份欄位清單。
模組層級的 `FUND_COLUMNS` 是以 `DEFAULT_CALENDAR_YEARS` 產生的預設值。

費用欄位一律成對：`*_raw` 保留平台原文（可能是「最高 1.205」或「0.84 - 0.96」），
`*_pct` 是解析出的數值（區間取上限、「最高 X」取 X）。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 基本欄位

BASE_FIELDS: list[tuple[str, str, str]] = [
    ("scheme_name",            "計劃",               "強積金計劃名稱"),
    ("fund_name",              "成分基金",           "成分基金名稱"),
    ("trustee",                "受託人",             "受託人名稱"),
    ("fund_category",          "基金類別",           "基金類別（含基金種類前綴，如「股票基金 - 亞洲股票基金」）"),
    ("launch_date",            "推出日期",           "基金推出日期（ISO 8601）"),
    ("fund_size_hkd_million",  "基金規模（百萬港元）", "基金規模（百萬港元）"),
    ("risk_level",             "風險級別",           "風險級別（整數 1-7）"),
    ("fer_pct",                "最近期基金開支比率",  "最近期基金開支比率 FER（%）"),
]

# ---------------------------------------------------------------- 回報欄位

# (英文欄位名, 繁中期間名, 說明)；年率化與累積共用同一組期間
RETURN_PERIODS: list[tuple[str, str]] = [
    ("1y",           "一年期"),
    ("5y",           "五年期"),
    ("10y",          "十年期"),
    ("since_launch", "推出至今"),
]

ANNUALISED_FIELDS: list[tuple[str, str, str]] = [
    (f"return_{k}_annualised", f"年率化回報 {zh}", f"{zh}年率化回報（% p.a.）")
    for k, zh in RETURN_PERIODS
]
CUMULATIVE_FIELDS: list[tuple[str, str, str]] = [
    (f"return_{k}_cumulative", f"累積回報 {zh}", f"{zh}累積回報（%）")
    for k, zh in RETURN_PERIODS
]

DEFAULT_CALENDAR_YEARS: list[int] = [2025, 2024, 2023, 2022, 2021]


def calendar_year_field(year: int | str) -> str:
    return f"return_cy{year}"


def calendar_year_zh(year: int | str) -> str:
    return f"曆年回報 {year}"


def calendar_fields(years: list[int] | None = None) -> list[tuple[str, str, str]]:
    years = years if years is not None else DEFAULT_CALENDAR_YEARS
    return [(calendar_year_field(y), calendar_year_zh(y), f"{y} 曆年回報（%）") for y in years]


# ---------------------------------------------------------------- 費用欄位

# (基底英文名, 繁中原文, 說明)
FEE_ITEMS: list[tuple[str, str, str]] = [
    ("management_fee",            "基金管理費",         "基金管理費（% p.a.）"),
    ("trustee_custodian_fee",     "受託人費／保管人費", "基金管理費分項：受託人費／保管人費（% p.a.）"),
    ("empf_platform_fee",         "積金易平台費",       "基金管理費分項：積金易平台費（% p.a.）"),
    ("member_service_fee",        "成員服務費",         "基金管理費分項：成員服務費（% p.a.）"),
    ("investment_management_fee", "投資管理費",         "基金管理費分項：投資管理費（% p.a.）"),
    ("guarantee_fee",             "保證費",             "保證費（% p.a.）"),
]

FEE_FIELDS: list[tuple[str, str, str]] = []
for _base, _zh, _d in FEE_ITEMS:
    FEE_FIELDS.append((f"{_base}_raw", f"{_zh}（原文）",
                       f"{_d} —— 平台原文，可能是「最高 X」或「X - Y」區間"))
    FEE_FIELDS.append((f"{_base}_pct", f"{_zh}（數值）",
                       f"{_d} —— 解析出的數值：區間取上限、「最高 X」取 X"))

FEE_BASES: list[str] = [b for b, _zh, _d in FEE_ITEMS]


# ---------------------------------------------------------------- 組合

def fund_fields(years: list[int] | None = None) -> list[tuple[str, str, str]]:
    return (BASE_FIELDS + ANNUALISED_FIELDS + CUMULATIVE_FIELDS
            + calendar_fields(years) + FEE_FIELDS)


def fund_columns(years: list[int] | None = None) -> list[str]:
    return [en for en, _zh, _d in fund_fields(years)]


FUND_FIELDS: list[tuple[str, str, str]] = fund_fields()
FUND_COLUMNS: list[str] = fund_columns()

# 月末單位價格（平台若另行提供）
UNIT_PRICE_FIELDS: list[tuple[str, str, str]] = [
    ("trustee",     "受託人",   "受託人名稱"),
    ("scheme_name", "計劃",     "強積金計劃名稱"),
    ("fund_name",   "成分基金", "成分基金名稱"),
    ("price_date",  "日期",     "月末日期（ISO 8601）"),
    ("unit_price",  "單位價格", "每單位價格"),
    ("currency",    "貨幣",     "計價貨幣"),
]
UNIT_PRICE_COLUMNS: list[str] = [en for en, _zh, _d in UNIT_PRICE_FIELDS]


def zh_for(field: str) -> str | None:
    """英文欄位名 -> 繁中原文（含動態的曆年回報欄位）。"""
    if field in _ZH_STATIC:
        return _ZH_STATIC[field]
    if field.startswith("return_cy"):
        return calendar_year_zh(field[len("return_cy"):])
    return None


def desc_for(field: str) -> str | None:
    if field in _DESC_STATIC:
        return _DESC_STATIC[field]
    if field.startswith("return_cy"):
        return f"{field[len('return_cy'):]} 曆年回報（%）"
    return None


_ALL_STATIC = BASE_FIELDS + ANNUALISED_FIELDS + CUMULATIVE_FIELDS + FEE_FIELDS + UNIT_PRICE_FIELDS
_ZH_STATIC: dict[str, str] = {en: zh for en, zh, _d in _ALL_STATIC}
_DESC_STATIC: dict[str, str] = {en: d for en, _zh, d in _ALL_STATIC}

# 相容舊名稱（dict 介面）：含預設年份的曆年欄位
ZH_BY_EN: dict[str, str] = {en: (zh_for(en) or en) for en in FUND_COLUMNS + UNIT_PRICE_COLUMNS}
DESC_BY_EN: dict[str, str] = {en: (desc_for(en) or "") for en in FUND_COLUMNS + UNIT_PRICE_COLUMNS}


# ---------------------------------------------------------------- 類型分組

def numeric_fields(years: list[int] | None = None) -> list[str]:
    """需要做數值解析／空值率統計的欄位（不含 *_raw 文字欄）。"""
    out = ["fund_size_hkd_million", "fer_pct", "risk_level"]
    out += [en for en, _zh, _d in ANNUALISED_FIELDS + CUMULATIVE_FIELDS + calendar_fields(years)]
    out += [f"{b}_pct" for b in FEE_BASES]
    return out


NUMERIC_FIELDS: list[str] = numeric_fields()
PERCENT_FIELDS: list[str] = [f for f in NUMERIC_FIELDS if f != "fund_size_hkd_million" and f != "risk_level"]
DATE_FIELDS: list[str] = ["launch_date", "price_date"]
INT_FIELDS: list[str] = ["risk_level"]
FEE_RAW_FIELDS: list[str] = [f"{b}_raw" for b in FEE_BASES]
FEE_PCT_FIELDS: list[str] = [f"{b}_pct" for b in FEE_BASES]

# ---------------------------------------------------------------- 標題別名

ALIASES: dict[str, list[str]] = {
    "trustee": ["受託人", "受托人", "信託人", "trustee"],
    "scheme_name": ["計劃", "計劃名稱", "计划名称", "強積金計劃名稱", "scheme", "schemename", "mpfscheme"],
    "fund_name": ["成分基金", "基金名稱", "基金名称", "成分基金名稱", "constituentfund", "fundname"],
    "fund_category": ["基金類別", "基金类别", "fundcategory", "category"],
    "fund_type": ["基金種類", "基金种类", "fundtype"],
    "launch_date": ["推出日期", "成立日期", "launchdate", "inceptiondate", "dateofinception"],
    "fund_size_hkd_million": [
        "基金規模", "基金规模", "基金規模百萬港元", "基金資產淨值", "淨資產值",
        "fundsize", "fundsizemillion", "netassetvalue", "nav",
    ],
    "fer_pct": [
        "最近期基金開支比率", "最近期基金開支比率", "基金開支比率", "基金开支比率",
        "基金開支比率fer", "開支比率", "fer", "fundexpenseratio", "expenseratio",
    ],
    "risk_level": ["風險級別", "风险级别", "風險指標", "risklevel", "riskindicator", "riskclass"],
    "return_1y_annualised": ["1年年率化回報", "一年期年率化回報", "1yearannualisedreturn"],
    "return_5y_annualised": ["5年年率化回報", "五年期年率化回報", "5yearannualisedreturn"],
    "return_10y_annualised": ["10年年率化回報", "十年期年率化回報", "10yearannualisedreturn"],
    "return_since_launch_annualised": ["成立以來年率化回報", "推出至今年率化回報", "sincelaunchannualisedreturn"],
    "return_1y_cumulative": ["1年累積回報", "一年期累積回報", "1yearcumulativereturn"],
    "return_5y_cumulative": ["5年累積回報", "五年期累積回報", "5yearcumulativereturn"],
    "return_10y_cumulative": ["10年累積回報", "十年期累積回報", "10yearcumulativereturn"],
    "return_since_launch_cumulative": ["成立以來累積回報", "推出至今累積回報", "sincelaunchcumulativereturn"],
    # 費用欄位：精確別名優先於包含比對，避免「受託人費／保管人費」被誤配到「受託人」
    "management_fee_raw": ["基金管理費", "基金管理费", "managementfee"],
    "trustee_custodian_fee_raw": ["受託人費保管人費", "受託人費／保管人費", "受託人費", "保管人費",
                                  "trusteecustodianfee", "trusteefee"],
    "empf_platform_fee_raw": ["積金易平台費", "积金易平台费", "empfplatformfee", "empffee"],
    "member_service_fee_raw": ["成員服務費", "成员服务费", "memberservicefee"],
    "investment_management_fee_raw": ["投資管理費", "投资管理费", "investmentmanagementfee"],
    "guarantee_fee_raw": ["保證費", "保证费", "guaranteefee"],
    "price_date": ["日期", "月末日期", "截至", "date", "monthenddate", "asofdate"],
    "unit_price": ["單位價格", "单位价格", "基金單位價格", "每單位價格", "unitprice", "navperunit"],
    "currency": ["貨幣", "货币", "計價貨幣", "currency", "ccy"],
}
