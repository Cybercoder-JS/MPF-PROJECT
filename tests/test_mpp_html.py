#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mpp_list.jsp 基金資訊表 HTML 解析器測試。不碰網路。

執行： python tests/test_mpp_html.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import make_sample_raw as gen                                      # noqa: E402
from mpfa.mpp_html import (                                        # noqa: E402
    MppStructureError, looks_like_mpp_list, parse_mpp_list,
)

failures: list[str] = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'ok ' if cond else 'FAIL'}] {label}" + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(label)


rows = gen.build_rows(seed=7)[:8]
html = gen.render_html(rows)

print("== 1. 頁面辨識 ==")
check("辨識出基金資訊表", looks_like_mpp_list(html))
check("普通頁面不被誤判", not looks_like_mpp_list("<html><body><p>無關頁面</p></body></html>"))

print("\n== 2. 解析結果 ==")
r = parse_mpp_list(html)
check(f"解析出 {len(rows)} 列", len(r.records) == len(rows), str(len(r.records)))
check("欄位 33 個", len(r.columns) == 33, str(len(r.columns)))
check("曆年回報年份 [2025..2021]", r.calendar_years == [2025, 2024, 2023, 2022, 2021],
      str(r.calendar_years))
check("資料截止日期 2026-09-30", r.as_of_date == "2026-09-30", str(r.as_of_date))
check("最後更新日期已讀出", r.last_updated is not None, str(r.last_updated))
check("頁面自報總數已讀出", r.reported_total == len(rows), str(r.reported_total))

print("\n== 3. 跳過篩選器與註釋 ==")
diag = r.diagnostics
check("選到的是資料表（30 格資料列）", diag["data_row_cells"] == 30, str(diag["data_row_cells"]))
check("整表皆空的結構欄被排除", diag["structural_empty_cols"] == [0, 2, 29],
      str(diag["structural_empty_cols"]))
check("回報欄依 class 定位",
      diag["annualised_cols"] == [10, 11, 12, 13] and diag["cumulative_cols"] == [14, 15, 16, 17]
      and diag["calendar_cols"] == [18, 19, 20, 21, 22])

print("\n== 4. 欄位映射正確（逐格比對原始列）==")
src, got = rows[0], r.records[0]
for field, want in [
    ("scheme_name", src["scheme"]), ("fund_name", src["fund"]),
    ("trustee", src["trustee"]), ("fund_category", src["category"]),
]:
    check(f"{field} == {want[:22]!r}", got[field] == want, repr(got[field])[:34])
d, m, y = src["launch"].split("-")
check("launch_date 轉 ISO", got["launch_date"] == f"{y}-{m}-{d}", str(got["launch_date"]))
check("risk_level 為整數或 None",
      got["risk_level"] is None or isinstance(got["risk_level"], int))
check("一年期累積 == 一年期年率化（定義上相同）",
      got["return_1y_cumulative"] == got["return_1y_annualised"])

print("\n== 5. n.a. 一律空值，不是 0 ==")
na_cells = sum(1 for row in rows for v in (
    [row["size"], row["risk"], row["fer"], row["a5"], row["a10"],
     row["c5"], row["c10"]] + row["cy"]) if v is None)
null_cells = 0
for rec, row in zip(r.records, rows):
    for f, v in (("fund_size_hkd_million", row["size"]), ("risk_level", row["risk"]),
                 ("fer_pct", row["fer"]), ("return_5y_annualised", row["a5"]),
                 ("return_10y_annualised", row["a10"]),
                 ("return_5y_cumulative", row["c5"]), ("return_10y_cumulative", row["c10"])):
        if v is None and rec[f] is None:
            null_cells += 1
    for i, v in enumerate(row["cy"]):
        if v is None and rec[f"return_cy{r.calendar_years[i]}"] is None:
            null_cells += 1
check(f"來源 n.a. {na_cells} 格全部成為 null", na_cells == null_cells,
      f"對上 {null_cells}")
zeros = [rec for rec, row in zip(r.records, rows) if row["a1"] == 0.0]
check("真實 0.00 保留為 0.0",
      all(z["return_1y_annualised"] == 0.0 for z in zeros) if zeros else True)

print("\n== 6. 費用：原文 + 數值 ==")
for rec, row in zip(r.records, rows):
    raw, val = rec["management_fee_raw"], rec["management_fee_pct"]
    if raw is None:
        continue
    check(f"原文保留 {raw[:16]!r}", raw == row["mgmt"], repr(raw))
    if raw.startswith("最高"):
        want = float(re.search(r"[\d.]+", raw).group())
        check("「最高 X」取 X", abs(val - want) < 1e-9, f"{raw} -> {val}")
    elif " - " in raw:
        lo, hi = (float(x) for x in raw.split(" - "))
        check("區間取上限", abs(val - max(lo, hi)) < 1e-9, f"{raw} -> {val}")
    else:
        check("純數字", abs(val - float(raw)) < 1e-9, f"{raw} -> {val}")
    break
basis = r.diagnostics["fee_basis_counts"].get("management_fee", {})
check("費用形式有被統計", bool(basis), str(basis))

print("\n== 7. 結構異常要中止，不做猜測性映射 ==")
try:
    parse_mpp_list("<html><body><table><tr><td>無關</td></tr></table></body></html>")
    check("找不到資料表時拋 MppStructureError", False)
except MppStructureError as e:
    check("找不到資料表時拋 MppStructureError", "找不到基金資訊表" in str(e))

# 砍掉一個回報欄，欄位數就對不上
broken = html.replace('<td class="arCol mpp_tab_green">', '<td class="mpp_tab_green">', 1)
assert broken != html, "測試自身有誤：替換未生效"
try:
    parse_mpp_list(broken)
    check("回報欄數不符時拋錯", False)
except MppStructureError as e:
    check("回報欄數不符時拋錯且說明原因", "arCol" in str(e) or "對不上" in str(e), str(e)[:70])

print("\n== 8. 真實頁面（若存在）==")
real = ROOT / "data/raw/mpp_list.html"
if real.exists():
    rr = parse_mpp_list(real.read_text(encoding="utf-8", errors="replace"))
    check("真實頁面解析出 451 列", len(rr.records) == 451, str(len(rr.records)))
    check("資料截至 2026-09-30", rr.as_of_date == "2026-09-30", str(rr.as_of_date))
    check("頁面自報總數 382", rr.reported_total == 382, str(rr.reported_total))
    check("24 個計劃", len({x["scheme_name"] for x in rr.records}) == 24)
    check("曆年年份 [2025..2021]", rr.calendar_years == [2025, 2024, 2023, 2022, 2021])
    check("無重複 (計劃,基金)",
          len({(x["scheme_name"], x["fund_name"]) for x in rr.records}) == len(rr.records))
else:
    print("  (略過：data/raw/mpp_list.html 不存在)")

print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} 項\n  - " + "\n  - ".join(failures))
    raise SystemExit(1)
print("全部通過")
