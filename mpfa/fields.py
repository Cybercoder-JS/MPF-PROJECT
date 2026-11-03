# -*- coding: utf-8 -*-
"""強積金基金平台欄位定義：繁體中文原文 <-> 英文欄位名映射。

平台欄位標題是解析的唯一依據（而非欄位位置），因此同一份映射表可同時
用於 HTML 表格、CSV 下載與 XLSX 下載三種來源。

`ALIASES` 收錄同一欄位在平台上出現過的多種寫法（含括號單位、全半角、
英文版標題）。新增別名時只需往對應 list 追加，解析層無須改動。
"""

from __future__ import annotations

# 基金資訊表：每隻基金一行。順序即為輸出 CSV 的欄位順序。
FUND_FIELDS: list[tuple[str, str, str]] = [
    # (英文欄位名, 繁體中文原文, 說明)
    ("trustee",                        "受託人",             "受託人（信託人）名稱"),
    ("scheme_name",                    "計劃名稱",           "強積金計劃名稱"),
    ("fund_name",                      "基金名稱",           "成分基金名稱"),
    ("fund_category",                  "基金類別",           "基金類別（平台分類，約 451 項）"),
    ("fund_type",                      "基金種類",           "基金種類（股票/混合資產/債券/保證/保守等）"),
    ("launch_date",                    "成立日期",           "基金成立日期（ISO 8601）"),
    ("fund_size_hkd_million",          "基金規模",           "基金規模（百萬港元）"),
    ("fer_pct",                        "基金開支比率",       "基金開支比率 FER（%）"),
    ("risk_level",                     "風險級別",           "風險級別（整數 1-7）"),
    ("return_1y_annualised",           "1年年率化回報",      "1 年年率化回報（%）"),
    ("return_5y_annualised",           "5年年率化回報",      "5 年年率化回報（%）"),
    ("return_10y_annualised",          "10年年率化回報",     "10 年年率化回報（%）"),
    ("return_since_launch_annualised", "成立以來年率化回報", "成立以來年率化回報（%）"),
    ("return_1y_cumulative",           "1年累積回報",        "1 年累積回報（%）"),
    ("return_5y_cumulative",           "5年累積回報",        "5 年累積回報（%）"),
    ("return_10y_cumulative",          "10年累積回報",       "10 年累積回報（%）"),
    ("return_since_launch_cumulative", "成立以來累積回報",   "成立以來累積回報（%）"),
]

# 月末單位價格：每隻基金每個月末一行。
UNIT_PRICE_FIELDS: list[tuple[str, str, str]] = [
    ("trustee",     "受託人",       "受託人名稱"),
    ("scheme_name", "計劃名稱",     "強積金計劃名稱"),
    ("fund_name",   "基金名稱",     "成分基金名稱"),
    ("price_date",  "日期",         "月末日期（ISO 8601）"),
    ("unit_price",  "單位價格",     "每單位價格"),
    ("currency",    "貨幣",         "計價貨幣"),
]

FUND_COLUMNS: list[str] = [en for en, _zh, _d in FUND_FIELDS]
UNIT_PRICE_COLUMNS: list[str] = [en for en, _zh, _d in UNIT_PRICE_FIELDS]

ZH_BY_EN: dict[str, str] = {en: zh for en, zh, _d in FUND_FIELDS + UNIT_PRICE_FIELDS}
DESC_BY_EN: dict[str, str] = {en: d for en, _zh, d in FUND_FIELDS + UNIT_PRICE_FIELDS}

# 數值欄位（空值率統計與 n.a. 處理的對象）
NUMERIC_FIELDS: list[str] = [
    "fund_size_hkd_million", "fer_pct", "risk_level",
    "return_1y_annualised", "return_5y_annualised", "return_10y_annualised",
    "return_since_launch_annualised",
    "return_1y_cumulative", "return_5y_cumulative", "return_10y_cumulative",
    "return_since_launch_cumulative",
]
PERCENT_FIELDS: list[str] = [f for f in NUMERIC_FIELDS if f.startswith("return_") or f == "fer_pct"]
DATE_FIELDS: list[str] = ["launch_date", "price_date"]
INT_FIELDS: list[str] = ["risk_level"]

# 平台欄位標題別名。鍵為英文欄位名，值為可能出現的標題寫法（比對前會正規化）。
ALIASES: dict[str, list[str]] = {
    "trustee": ["受託人", "受托人", "信託人", "trustee"],
    "scheme_name": ["計劃名稱", "计划名称", "強積金計劃名稱", "計劃", "scheme", "schemename", "mpfscheme"],
    "fund_name": ["基金名稱", "基金名称", "成分基金名稱", "成分基金", "constituentfund", "fundname"],
    "fund_category": ["基金類別", "基金类别", "fundcategory", "category"],
    "fund_type": ["基金種類", "基金种类", "fundtype", "type"],
    "launch_date": ["成立日期", "推出日期", "launchdate", "inceptiondate", "dateofinception"],
    "fund_size_hkd_million": [
        "基金規模", "基金规模", "基金規模百萬港元", "基金資產淨值", "淨資產值",
        "fundsize", "fundsizemillion", "netassetvalue", "nav",
    ],
    "fer_pct": [
        "基金開支比率", "基金开支比率", "基金開支比率fer", "開支比率", "fer",
        "fundexpenseratio", "expenseratio",
    ],
    "risk_level": ["風險級別", "风险级别", "風險指標", "risklevel", "riskindicator", "riskclass"],
    "return_1y_annualised": ["1年年率化回報", "1年年化回報", "一年年率化回報", "1yearannualisedreturn", "1yearannualizedreturn"],
    "return_5y_annualised": ["5年年率化回報", "5年年化回報", "五年年率化回報", "5yearannualisedreturn", "5yearannualizedreturn"],
    "return_10y_annualised": ["10年年率化回報", "10年年化回報", "十年年率化回報", "10yearannualisedreturn", "10yearannualizedreturn"],
    "return_since_launch_annualised": [
        "成立以來年率化回報", "成立以來年化回報", "自成立以來年率化回報",
        "sincelaunchannualisedreturn", "sinceinceptionannualisedreturn",
    ],
    "return_1y_cumulative": ["1年累積回報", "1年累计回报", "一年累積回報", "1yearcumulativereturn"],
    "return_5y_cumulative": ["5年累積回報", "5年累计回报", "五年累積回報", "5yearcumulativereturn"],
    "return_10y_cumulative": ["10年累積回報", "10年累计回报", "十年累積回報", "10yearcumulativereturn"],
    "return_since_launch_cumulative": [
        "成立以來累積回報", "自成立以來累積回報", "sincelaunchcumulativereturn", "sinceinceptioncumulativereturn",
    ],
    "price_date": ["日期", "月末日期", "截至", "date", "monthenddate", "asofdate"],
    "unit_price": ["單位價格", "单位价格", "基金單位價格", "每單位價格", "unitprice", "navperunit"],
    "currency": ["貨幣", "货币", "計價貨幣", "currency", "ccy"],
}
