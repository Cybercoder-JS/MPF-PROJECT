# -*- coding: utf-8 -*-
"""表格解析：以「欄位標題」而非「欄位位置」對應，HTML / CSV / XLSX 共用。

分兩層：
  * `tables_from_*`  把檔案位元組攤成「表格 -> 列 -> 格」的純文字結構
  * `rows_to_records` 找出表頭列，依標題文字映射成正規化後的 dict

分層的目的是讓來源層（mpfa/sources.py）能先看表頭、判斷這個檔案是
基金資訊表還是月末單位價格，再決定用哪組欄位解析。

平台若改動欄位順序或增刪欄位，解析不會錯位；只有當標題文字改成未知寫法時
才需要在 fields.ALIASES 補別名。
"""

from __future__ import annotations

import csv
import io
import logging
import re

from bs4 import BeautifulSoup

from .fields import FUND_COLUMNS, UNIT_PRICE_COLUMNS
from .normalize import coerce, parse_date, resolve_header

log = logging.getLogger(__name__)

# 只出現在月末單位價格檔的欄位，用來區分兩種檔案
UNIT_PRICE_MARKERS = frozenset({"price_date", "unit_price"})
# 只出現在基金資訊表的欄位
FUND_MARKERS = frozenset({
    "fund_category", "fund_type", "launch_date", "fund_size_hkd_million",
    "fer_pct", "risk_level",
}) | {c for c in FUND_COLUMNS if c.startswith("return_")}


# ------------------------------------------------------------ 位元組 -> 列

def _sniff_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "big5hkscs", "big5", "cp950", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def tables_from_html(html: str) -> list[list[list[str]]]:
    soup = BeautifulSoup(html, "lxml")
    tables = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if cells:
                rows.append([c.get_text(" ", strip=True) for c in cells])
        if rows:
            tables.append(rows)
    return tables


def tables_from_csv(data: bytes) -> list[list[list[str]]]:
    text = _sniff_text(data)
    try:
        delim = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        delim = ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
    return [rows] if rows else []


def tables_from_xlsx(data: bytes) -> list[list[list]]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    tables = []
    for ws in wb.worksheets:
        rows = [
            ["" if c is None else c for c in row]
            for row in ws.iter_rows(values_only=True)
        ]
        if rows:
            tables.append(rows)
    wb.close()
    return tables


def tables_from_xls(data: bytes) -> list[list[list]]:
    """舊版 .xls（BIFF）。需要 xlrd，未安裝則回報清楚的錯誤。"""
    try:
        import xlrd  # type: ignore
    except ImportError as e:  # noqa: BLE001
        raise RuntimeError(
            "這是舊版 .xls 檔，需要 xlrd 才能讀取：pip install xlrd\n"
            "或請在平台上改下載 CSV / XLSX 格式。"
        ) from e
    book = xlrd.open_workbook(file_contents=data)
    tables = []
    for sh in book.sheets():
        rows = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
        if rows:
            tables.append(rows)
    return tables


def tables_from_bytes(data: bytes, content_type: str = "", filename: str = "") -> list[list[list]]:
    """依內容與副檔名自動選擇解析器，回傳所有表格的原始列。"""
    ct = (content_type or "").lower()
    name = (filename or "").lower()

    if data[:4] == b"PK\x03\x04" or "spreadsheet" in ct or name.endswith((".xlsx", ".xlsm")):
        return tables_from_xlsx(data)
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" or name.endswith(".xls"):
        return tables_from_xls(data)
    if name.endswith((".html", ".htm")) or "html" in ct:
        return tables_from_html(_sniff_text(data))
    if name.endswith((".csv", ".txt", ".tsv")) or "csv" in ct or "text/plain" in ct:
        return tables_from_csv(data)

    head = _sniff_text(data[:4096]).lower()
    if "<table" in head or "<html" in head:
        return tables_from_html(_sniff_text(data))
    return tables_from_csv(data)


# ------------------------------------------------------------ 列 -> 紀錄

def find_header_row(rows: list[list], min_hits: int = 3) -> tuple[int, dict[int, str]] | None:
    """在前若干列中找出表頭列，回傳 (列索引, {欄位索引: 英文欄位名})。"""
    best = None
    for i, row in enumerate(rows[:15]):
        mapping: dict[int, str] = {}
        for j, cell in enumerate(row):
            en = resolve_header(str(cell) if cell is not None else "")
            if en and en not in mapping.values():
                mapping[j] = en
        if len(mapping) >= min_hits and (best is None or len(mapping) > len(best[1])):
            best = (i, mapping)
    return best


_find_header_row = find_header_row  # 舊名稱相容


def classify_table(rows: list[list]) -> str | None:
    """判斷一張表是基金資訊表還是月末單位價格；無法判斷回傳 None。"""
    found = find_header_row(rows, min_hits=2)
    if not found:
        return None
    fields = set(found[1].values())
    if fields & UNIT_PRICE_MARKERS:
        return "unit_prices"
    if fields & FUND_MARKERS:
        return "funds"
    # 只有受託人/計劃/基金名稱時，無從判斷類型，當成基金資訊表
    if {"fund_name", "scheme_name", "trustee"} & fields:
        return "funds"
    return None


def rows_to_records(rows: list[list], columns: list[str]) -> list[dict]:
    """把二維表格轉成正規化後的 dict 列表。"""
    found = find_header_row(rows)
    if not found:
        return []
    header_idx, mapping = found
    log.debug("表頭在第 %s 列，辨識出 %s 個欄位", header_idx, len(mapping))

    records = []
    for row in rows[header_idx + 1:]:
        if not any(str(c).strip() for c in row if c is not None):
            continue
        rec = {col: None for col in columns}
        matched = False
        for j, en in mapping.items():
            if j < len(row) and en in rec:
                rec[en] = coerce(en, row[j])
                matched = True
        if not matched:
            continue
        # 整列都沒有識別名稱的，多半是小計/註腳列，丟棄
        if not (rec.get("fund_name") or rec.get("scheme_name")):
            continue
        records.append(rec)
    return records


# ------------------------------------------------------------ 便利函式

def parse_html_tables(html: str, columns: list[str] = FUND_COLUMNS) -> list[dict]:
    out: list[dict] = []
    for rows in tables_from_html(html):
        out.extend(rows_to_records(rows, columns))
    return out


def parse_csv(data: bytes, columns: list[str] = FUND_COLUMNS) -> list[dict]:
    out: list[dict] = []
    for rows in tables_from_csv(data):
        out.extend(rows_to_records(rows, columns))
    return out


def parse_xlsx(data: bytes, columns: list[str] = FUND_COLUMNS) -> list[dict]:
    out: list[dict] = []
    for rows in tables_from_xlsx(data):
        out.extend(rows_to_records(rows, columns))
    return out


def parse_auto(data: bytes, content_type: str = "", columns: list[str] = FUND_COLUMNS,
               filename: str = "") -> list[dict]:
    out: list[dict] = []
    for rows in tables_from_bytes(data, content_type, filename):
        out.extend(rows_to_records(rows, columns))
    return out


def parse_unit_prices(data: bytes, content_type: str = "", filename: str = "") -> list[dict]:
    return parse_auto(data, content_type, UNIT_PRICE_COLUMNS, filename)


def dedupe(records: list[dict], keys: tuple[str, ...] = ("trustee", "scheme_name", "fund_name")) -> list[dict]:
    """依鍵去重，保留第一筆（分頁重疊、多檔案重疊時會用到）。"""
    seen: set[tuple] = set()
    out = []
    for r in records:
        k = tuple(r.get(x) for x in keys)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


# ------------------------------------------------------------ 資料截止日期

AS_OF_PATTERNS = [
    r"截至\s*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{4})",
    r"截至\s*([0-9]{4}\s*年\s*[0-9]{1,2}\s*月\s*[0-9]{1,2}\s*日)",
    r"資料更新至\s*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{4})",
    r"資料截至\s*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{4})",
    r"(?i)as\s+at\s+([0-9]{1,2}\s+\w+\s+[0-9]{4})",
    r"(?i)as\s+at\s+([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{4})",
]


def extract_as_of_date(text_or_html: str) -> str | None:
    """從頁面／檔案文字抓出資料截止日期，轉成 ISO 格式。"""
    if not text_or_html:
        return None
    if "<" in text_or_html[:2000] and ">" in text_or_html[:2000]:
        text = BeautifulSoup(text_or_html, "lxml").get_text(" ", strip=True)
    else:
        text = text_or_html
    for pat in AS_OF_PATTERNS:
        m = re.search(pat, text)
        if m:
            raw = m.group(1)
            # 兩種寫法都試：保留空格（英文 "31 March 2026"）與去除空格（中文 "2026 年 3 月 31 日"）
            for cand in (re.sub(r"\s+", " ", raw).strip(), re.sub(r"\s+", "", raw)):
                iso = parse_date(cand)
                if iso:
                    return iso
            return re.sub(r"\s+", " ", raw).strip()
    return None
