# -*- coding: utf-8 -*-
"""欄位標題比對與值正規化。

設計要點：平台上大量欄位為 "n.a."，一律轉為 None（空值），絕不當成 0。
下游的 CSV 輸出為空字串、JSON 輸出為 null，兩者都不會被誤讀為數值 0。
"""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata

from .fields import ALIASES

# 平台上代表「無資料」的寫法。全部轉為 None。
# 注意：這裡刻意不含 "0"、"0.00" 等，真正的 0 是有效數值。
NA_TOKENS: frozenset[str] = frozenset({
    "n.a.", "na", "n/a", "nil", "-", "--", "---", "—", "–", "不適用", "不适用",
    "無", "无", "沒有提供", "没有提供", "未提供", "不詳", "不详", "",
    "*", "**", "n.a", "notapplicable", "notavailable",
})


def normalize_header(raw: str) -> str:
    """把欄位標題正規化成可比對的鍵。

    全角轉半角、去除空白/換行/標點/單位括號、轉小寫。
    例： "基金開支比率 (FER)\\n(%)" -> "基金開支比率fer"
    """
    if raw is None:
        return ""
    s = unicodedata.normalize("NFKC", str(raw))
    s = s.replace("　", " ")
    # 去掉括號內的單位說明，例如 (%)、（百萬港元）、(HK$)
    s = re.sub(r"[（(][^）)]*[%％$＄]\s*[^）)]*[）)]", "", s)
    s = re.sub(r"[（(]\s*(百萬港元|百万港元|millionhkd|hk\$?m?|港元|%|％)\s*[）)]", "", s, flags=re.I)
    # 去掉所有空白與常見標點，保留中日韓文字、拉丁字母、數字
    s = re.sub(r"[\s_/\\\-–—,.:：、，。·'\"()（）\[\]【】{}<>《》#*]+", "", s)
    return s.strip().lower()


# 預先算好 正規化別名 -> 英文欄位名
_ALIAS_INDEX: dict[str, str] = {}
for _en, _variants in ALIASES.items():
    for _v in _variants:
        _ALIAS_INDEX.setdefault(normalize_header(_v), _en)


def resolve_header(raw: str) -> str | None:
    """把平台的欄位標題對應到英文欄位名；無法對應時回傳 None。"""
    key = normalize_header(raw)
    if not key:
        return None
    if key in _ALIAS_INDEX:
        return _ALIAS_INDEX[key]
    # 退一步做包含比對（處理標題帶多餘前後綴的情況），取最長命中以免誤配
    hits = [(len(a), en) for a, en in _ALIAS_INDEX.items() if len(a) >= 3 and (a in key or key in a)]
    if hits:
        return max(hits)[1]
    return None


def is_na(value) -> bool:
    """判斷是否為平台的「無資料」標記。"""
    if value is None:
        return True
    if isinstance(value, float) and value != value:  # NaN
        return True
    if isinstance(value, (int, float)):
        return False
    s = unicodedata.normalize("NFKC", str(value)).strip()
    return s.lower().replace(" ", "") in NA_TOKENS


def clean_text(value) -> str | None:
    """文字欄位：壓縮空白；"n.a." 類值回傳 None。"""
    if is_na(value):
        return None
    s = unicodedata.normalize("NFKC", str(value))
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def parse_number(value) -> float | None:
    """數值欄位：移除千分位、%、貨幣符號；"n.a." 回傳 None（不是 0）。

    支援括號負數寫法 (1.23) == -1.23。
    """
    if is_na(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = unicodedata.normalize("NFKC", str(value)).strip()
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()
    s = re.sub(r"(?i)(hk\$|hkd|usd|us\$|rmb|cny|\$|％|%|,|\s|港元|百萬|百万)", "", s)
    if s in ("", "+", "-", "."):
        return None
    if s.startswith("+"):
        s = s[1:]
    try:
        n = float(s)
    except ValueError:
        return None
    return -n if negative else n


def parse_int(value) -> int | None:
    """整數欄位（風險級別）。非整數或空值回傳 None，不做四捨五入猜測。"""
    n = parse_number(value)
    if n is None:
        return None
    if abs(n - round(n)) > 1e-9:
        return None
    return int(round(n))


_DATE_PATTERNS = (
    "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d",
    "%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
    "%d.%m.%Y", "%Y%m%d", "%m/%d/%Y",
)


def parse_date(value) -> str | None:
    """日期欄位 -> ISO 8601 字串 (YYYY-MM-DD)。無法解析回傳 None。

    平台以 DD-MM-YYYY / DD/MM/YYYY 為主，故日優先於月。
    """
    if is_na(value):
        return None
    if isinstance(value, _dt.datetime):
        return value.date().isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    s = unicodedata.normalize("NFKC", str(value)).strip()
    s = re.sub(r"\s+", " ", s)
    # 中文日期 2024年3月31日
    m = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$", s)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        try:
            return _dt.date(y, mo, d).isoformat()
        except ValueError:
            return None
    for fmt in _DATE_PATTERNS:
        try:
            return _dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


# 每個英文欄位名對應的轉換函式
from .fields import DATE_FIELDS, INT_FIELDS, NUMERIC_FIELDS  # noqa: E402


def coerce(field: str, value):
    """依欄位類型轉換值。未知欄位視為文字。"""
    if field in DATE_FIELDS:
        return parse_date(value)
    if field in INT_FIELDS:
        return parse_int(value)
    if field in NUMERIC_FIELDS or field == "unit_price":
        return parse_number(value)
    return clean_text(value)
