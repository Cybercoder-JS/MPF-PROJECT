# -*- coding: utf-8 -*-
"""解析 mpp_list.jsp「基金資訊表」的伺服器端渲染 HTML。

為什麼需要專用解析器：這張表的表頭橫跨三列（分組標題 + 主標題 + 期間子標題），
而且主標題用 rowspan、分組標題用 colspan，表頭與資料列的 colspan 並不一致，
所以把表格展開成矩形網格後兩者對不齊，通用的「表頭驅動」解析不適用。

改用兩個穩定訊號，仍然不寫死欄位位置：
  1. 資料格的 CSS class —— 平台用 `arCol`（年率化）、`crCol`（累積）、
     `cyrCol`（曆年）標記三組回報欄，頁面上以 radio 切換顯示。
  2. 表頭文字的「順序」—— 非回報欄位依主標題（加上分項子標題）的出現順序
     對應到資料列中「扣掉回報欄、且並非整表皆空」的欄位。

欄位數量對不上時直接拋 `MppStructureError`，不做猜測性映射 —— 寧可失敗，
也不要產出錯位的資料。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as _dcfield

from bs4 import BeautifulSoup

from .fields import (
    ANNUALISED_FIELDS,
    CUMULATIVE_FIELDS,
    FEE_BASES,
    calendar_year_field,
    fund_columns,
)
from .normalize import clean_text, coerce, parse_fee, resolve_header

log = logging.getLogger(__name__)


class MppStructureError(RuntimeError):
    """頁面結構與預期不符，無法安全對應欄位。"""


# 用來認出主表頭的欄位名（辨識到足夠多就認定是基金資訊表）
_HEADER_ANCHORS = (
    "scheme_name", "fund_name", "trustee", "fund_category",
    "launch_date", "fund_size_hkd_million", "risk_level", "fer_pct",
)
_MIN_HEADER_ANCHORS = 5

_PERIOD_RE = re.compile(r"^(一年期|五年期|十年期|推出至今|1年|5年|10年|成立以來)$")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")

# 回報欄的 class -> 欄位清單
_RETURN_CLASS_FIELDS = {
    "arCol": [en for en, _zh, _d in ANNUALISED_FIELDS],
    "crCol": [en for en, _zh, _d in CUMULATIVE_FIELDS],
}

AS_OF_RE = re.compile(r"最新資料截至\s*((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
LAST_UPDATED_RE = re.compile(r"最後更新日期[：:\s]*(\d{1,2}/\d{1,2}/\d{4})")
REPORTED_TOTAL_RE = re.compile(r"已選擇的成分基金總數[：:\s]*([\d,]+)")


@dataclass
class MppParseResult:
    records: list[dict] = _dcfield(default_factory=list)
    columns: list[str] = _dcfield(default_factory=list)
    calendar_years: list[int] = _dcfield(default_factory=list)
    as_of_date: str | None = None
    last_updated: str | None = None
    reported_total: int | None = None
    diagnostics: dict = _dcfield(default_factory=dict)


def _direct_cells(tr):
    return tr.find_all(["th", "td"], recursive=False)


def _direct_rows(table):
    return [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]


def _cell_classes(cell) -> set[str]:
    return set(cell.get("class") or [])


def looks_like_mpp_list(html: str) -> bool:
    """快速判斷一份 HTML 是否為基金資訊表頁面。"""
    if "mpp_list" in html[:400000] or "scrolltable" in html:
        return True
    return bool(AS_OF_RE.search(html) and REPORTED_TOTAL_RE.search(html))


def _find_data_table(soup):
    """找出資料表：表頭能辨識到足夠多欄位名，且資料列最多的那張表。

    頁面上的篩選器、註釋、提示都是表格，靠這個條件自然被排除。
    """
    best = None
    for table in soup.find_all("table"):
        rows = _direct_rows(table)
        if len(rows) < 5:
            continue
        for hi, tr in enumerate(rows[:6]):
            names = [c.get_text(" ", strip=True) for c in _direct_cells(tr)]
            hits = {resolve_header(n) for n in names if n}
            hits &= set(_HEADER_ANCHORS)
            if len(hits) >= _MIN_HEADER_ANCHORS:
                # 資料列 = 之後列中格數最常見的那些
                counts: dict[int, int] = {}
                for tr2 in rows[hi + 1:]:
                    n = len(_direct_cells(tr2))
                    counts[n] = counts.get(n, 0) + 1
                if not counts:
                    continue
                modal_n = max(counts, key=lambda k: (counts[k], k))
                n_data = counts[modal_n]
                if n_data >= 5 and (best is None or n_data > best[3]):
                    best = (table, rows, hi, n_data, modal_n)
                break
    if best is None:
        raise MppStructureError(
            "在頁面中找不到基金資訊表。\n"
            f"需要一張表格，其表頭能辨識出至少 {_MIN_HEADER_ANCHORS} 個已知欄位名"
            f"（如 計劃／成分基金／受託人／基金類別／推出日期／基金規模／風險級別／基金開支比率）。\n"
            "若平台改了欄位名稱，請在 mpfa/fields.py 的 ALIASES 補上新寫法。"
        )
    return best


def _split_subheader(names: list[str]) -> tuple[list[str], list[int], list[str]]:
    """子標題拆成 (期間名, 曆年年份, 其他=費用分項名)，順序保留。"""
    periods, years, others = [], [], []
    for n in names:
        flat = re.sub(r"\s+", "", n)
        if _PERIOD_RE.match(flat):
            periods.append(n)
        elif _YEAR_RE.match(flat):
            years.append(int(flat))
        else:
            others.append(n)
    return periods, years, others


def _expected_nonreturn_fields(header_names: list[str], fee_subitems: list[str]) -> list[str]:
    """依表頭順序產生非回報欄位的英文欄位名序列。"""
    out: list[str] = []
    for name in header_names:
        flat = re.sub(r"\s+", "", name)
        # 回報分組標題（三種回報共用一格，用 radio 切換）—— 由 class 處理
        if "回報" in flat and ("年率化回報" in flat or "累積回報" in flat or "曆年回報" in flat) \
                and sum(k in flat for k in ("年率化回報", "累積回報", "曆年回報")) >= 2:
            continue
        # 基金管理費分項分組標題 -> 展開成子標題的各分項
        if "分項" in flat:
            for sub in fee_subitems:
                en = resolve_header(sub)
                if en is None:
                    raise MppStructureError(
                        f"無法辨識基金管理費分項欄位名「{sub}」。"
                        f"請在 mpfa/fields.py 的 ALIASES 補上。"
                    )
                out.append(en)
            continue
        if "詳細內容" in flat or "詳情" in flat:
            continue
        en = resolve_header(name)
        if en is None:
            log.debug("表頭「%s」無法對應已知欄位，略過", name)
            continue
        out.append(en)
    return out


def parse_mpp_list(html: str) -> MppParseResult:
    soup = BeautifulSoup(html, "lxml")
    page_text = soup.get_text(" ", strip=True)

    table, rows, hi, n_data, modal_n = _find_data_table(soup)
    header_cells = _direct_cells(rows[hi])
    header_names = [c.get_text(" ", strip=True) for c in header_cells if c.get_text(" ", strip=True)]

    # 子標題：表頭的下一列（期間名／年份／費用分項）
    sub_names: list[str] = []
    if hi + 1 < len(rows):
        sub_names = [c.get_text(" ", strip=True) for c in _direct_cells(rows[hi + 1])
                     if c.get_text(" ", strip=True)]
    periods, years, fee_subitems = _split_subheader(sub_names)

    data_rows = [tr for tr in rows[hi + 1:] if len(_direct_cells(tr)) == modal_n]
    if not data_rows:
        raise MppStructureError("找到表頭但沒有資料列。")

    # --- 回報欄位：依 class 定位
    first = _direct_cells(data_rows[0])
    ar_idx = [i for i, c in enumerate(first) if "arCol" in _cell_classes(c)]
    cr_idx = [i for i, c in enumerate(first) if "crCol" in _cell_classes(c)]
    cyr_idx = [i for i, c in enumerate(first) if "cyrCol" in _cell_classes(c)]

    col_field: dict[int, str] = {}
    for cls, idxs in (("arCol", ar_idx), ("crCol", cr_idx)):
        want = _RETURN_CLASS_FIELDS[cls]
        if len(idxs) != len(want):
            raise MppStructureError(
                f"{cls} 欄位數為 {len(idxs)}，預期 {len(want)}（{'/'.join(want)}）。\n"
                f"頁面的回報期間可能有變動，請檢查 mpfa/fields.py 的 RETURN_PERIODS。"
            )
        for i, f in zip(idxs, want):
            col_field[i] = f

    if cyr_idx:
        if not years:
            raise MppStructureError(
                f"找到 {len(cyr_idx)} 個曆年回報欄，但子標題裡讀不到年份。"
            )
        if len(cyr_idx) != len(years):
            raise MppStructureError(
                f"曆年回報欄位數為 {len(cyr_idx)}，但子標題讀到 {len(years)} 個年份 {years}。"
            )
        for i, y in zip(cyr_idx, years):
            col_field[i] = calendar_year_field(y)

    # --- 非回報欄位：扣掉回報欄與整表皆空的欄，依表頭順序對應
    return_cols = set(col_field)
    nonreturn = [i for i in range(modal_n) if i not in return_cols]
    all_empty = [
        i for i in nonreturn
        if all(not _direct_cells(tr)[i].get_text(" ", strip=True) for tr in data_rows)
    ]
    value_cols = [i for i in nonreturn if i not in all_empty]

    expected = _expected_nonreturn_fields(header_names, fee_subitems)
    if len(value_cols) != len(expected):
        raise MppStructureError(
            f"非回報欄位對不上：資料列有 {len(value_cols)} 個有值的非回報欄，"
            f"但表頭推導出 {len(expected)} 個欄位。\n"
            f"  有值的欄位索引：{value_cols}\n"
            f"  表頭推導的欄位：{expected}\n"
            f"  主標題：{header_names}\n"
            f"  子標題：{sub_names}\n"
            "頁面結構可能已變動。已中止，未產出可能錯位的資料。"
        )
    for i, f in zip(value_cols, expected):
        col_field[i] = f

    # --- 逐列建立紀錄
    years_desc = years
    columns = fund_columns(years_desc) if years_desc else fund_columns()
    records: list[dict] = []
    fee_basis_counter: dict[str, dict[str, int]] = {}

    for tr in data_rows:
        cells = _direct_cells(tr)
        rec: dict = {c: None for c in columns}
        for i, fname in col_field.items():
            raw = cells[i].get_text(" ", strip=True)
            base = fname[:-4] if fname.endswith("_raw") else None
            if base in FEE_BASES:
                raw_txt, val, basis = parse_fee(raw)
                rec[f"{base}_raw"] = raw_txt
                rec[f"{base}_pct"] = val
                if basis:
                    fee_basis_counter.setdefault(base, {}).setdefault(basis, 0)
                    fee_basis_counter[base][basis] += 1
            elif fname in rec:
                rec[fname] = coerce(fname, raw)
        if not (rec.get("fund_name") or rec.get("scheme_name")):
            continue
        records.append(rec)

    # --- 頁面上的日期與自報總數
    as_of = None
    m = AS_OF_RE.search(page_text)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        as_of = f"{y:04d}-{mo:02d}-{d:02d}"
    m = LAST_UPDATED_RE.search(page_text)
    last_updated = None
    if m:
        dd, mm, yy = m.group(1).split("/")
        last_updated = f"{int(yy):04d}-{int(mm):02d}-{int(dd):02d}"
    m = REPORTED_TOTAL_RE.search(page_text)
    reported = int(m.group(1).replace(",", "")) if m else None

    diagnostics = {
        "header_row_index": hi,
        "data_row_cells": modal_n,
        "data_rows_found": len(data_rows),
        "annualised_cols": ar_idx,
        "cumulative_cols": cr_idx,
        "calendar_cols": cyr_idx,
        "structural_empty_cols": all_empty,
        "column_map": {str(i): col_field[i] for i in sorted(col_field)},
        "fee_basis_counts": fee_basis_counter,
        "page_reported_total": reported,
        "page_as_of": as_of,
        "page_last_updated": last_updated,
    }
    log.info("基金資訊表：解析 %s 列，曆年回報年份 %s", len(records), years_desc)

    return MppParseResult(
        records=records, columns=columns, calendar_years=years_desc,
        as_of_date=as_of, last_updated=last_updated, reported_total=reported,
        diagnostics=diagnostics,
    )
