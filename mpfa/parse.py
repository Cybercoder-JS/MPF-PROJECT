# -*- coding: utf-8 -*-
"""表格解析：以「欄位標題」而非「欄位位置」對應，HTML / CSV / XLSX 共用。

平台若改動欄位順序或增刪欄位，解析不會錯位；只有當標題文字改成未知寫法時
才需要在 fields.ALIASES 補別名。
"""

from __future__ import annotations

import csv
import io
import logging

from bs4 import BeautifulSoup

from .fields import FUND_COLUMNS, UNIT_PRICE_COLUMNS
from .normalize import coerce, resolve_header

log = logging.getLogger(__name__)


def _rows_from_html_table(table) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if cells:
            rows.append([c.get_text(" ", strip=True) for c in cells])
    return rows


def _find_header_row(rows: list[list[str]], min_hits: int = 3) -> tuple[int, dict[int, str]] | None:
    """在前若干列中找出表頭列，回傳 (列索引, {欄位索引: 英文欄位名})。"""
    best = None
    for i, row in enumerate(rows[:10]):
        mapping = {}
        for j, cell in enumerate(row):
            en = resolve_header(cell)
            if en and en not in mapping.values():
                mapping[j] = en
        if len(mapping) >= min_hits and (best is None or len(mapping) > len(best[1])):
            best = (i, mapping)
    return best


def rows_to_records(rows: list[list[str]], columns: list[str]) -> list[dict]:
    """把二維表格轉成正規化後的 dict 列表。"""
    found = _find_header_row(rows)
    if not found:
        return []
    header_idx, mapping = found
    log.debug("表頭在第 %s 列，辨識出 %s 個欄位", header_idx, len(mapping))

    records = []
    for row in rows[header_idx + 1:]:
        if not any((c or "").strip() for c in row):
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


def parse_html_tables(html: str, columns: list[str] = FUND_COLUMNS) -> list[dict]:
    """抽出 HTML 中所有能對應到目標欄位的表格資料並合併。"""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for table in soup.find_all("table"):
        recs = rows_to_records(_rows_from_html_table(table), columns)
        if recs:
            out.extend(recs)
    return out


def _sniff_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "big5hkscs", "big5", "cp950", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_csv(data: bytes, columns: list[str] = FUND_COLUMNS) -> list[dict]:
    text = _sniff_text(data)
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
    return rows_to_records(rows, columns)


def parse_xlsx(data: bytes, columns: list[str] = FUND_COLUMNS) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out: list[dict] = []
    for ws in wb.worksheets:
        rows = [
            ["" if c is None else c for c in row]
            for row in ws.iter_rows(values_only=True)
        ]
        recs = rows_to_records(rows, columns)
        if recs:
            out.extend(recs)
    wb.close()
    return out


def parse_auto(data: bytes, content_type: str = "", columns: list[str] = FUND_COLUMNS) -> list[dict]:
    """依內容自動選擇解析器。"""
    ct = (content_type or "").lower()
    if data[:2] == b"PK" or "spreadsheet" in ct or "xlsx" in ct:
        return parse_xlsx(data, columns)
    if data[:5].lower() == b"<?xml" or data[:1] == b"<" or "html" in ct:
        return parse_html_tables(_sniff_text(data), columns)
    if "csv" in ct or "text/plain" in ct:
        return parse_csv(data, columns)
    # 內容嗅探：有 HTML 標籤當成 HTML，否則試 CSV
    head = _sniff_text(data[:4096]).lower()
    if "<table" in head or "<html" in head:
        return parse_html_tables(_sniff_text(data), columns)
    return parse_csv(data, columns)


def parse_unit_prices(data: bytes, content_type: str = "") -> list[dict]:
    return parse_auto(data, content_type, columns=UNIT_PRICE_COLUMNS)


def dedupe(records: list[dict], keys: tuple[str, ...] = ("trustee", "scheme_name", "fund_name")) -> list[dict]:
    """依鍵去重，保留第一筆（分頁重疊時會用到）。"""
    seen: set[tuple] = set()
    out = []
    for r in records:
        k = tuple(r.get(x) for x in keys)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out
