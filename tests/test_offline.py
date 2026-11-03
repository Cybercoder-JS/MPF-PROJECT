#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""離線自我測試：不碰網路，驗證解析 / 正規化 / 輸出 / 驗證全鏈路。

執行： python tests/test_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mpfa import pipeline, validate as V          # noqa: E402
from mpfa.fields import FUND_COLUMNS              # noqa: E402
from mpfa.normalize import parse_number, parse_int, parse_date, resolve_header  # noqa: E402
from mpfa.parse import parse_html_tables          # noqa: E402

failures: list[str] = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'ok ' if cond else 'FAIL'}] {label}" + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(label)


print("== 1. 欄位標題對應 ==")
for raw, want in [("受託人", "trustee"), ("基金開支比率 (FER)\n(%)", "fer_pct"),
                  ("風險級別", "risk_level"), ("基金規模（百萬港元）", "fund_size_hkd_million"),
                  ("成立以來累積回報", "return_since_launch_cumulative")]:
    check(f"{raw!r} -> {want}", resolve_header(raw) == want, f"得到 {resolve_header(raw)}")

print("\n== 2. n.a. 必須是空值，真實的 0 必須保留 ==")
check('parse_number("n.a.") is None', parse_number("n.a.") is None)
check('parse_number("--") is None', parse_number("--") is None)
check('parse_number("0.00") == 0.0', parse_number("0.00") == 0.0)
check('parse_number("(1.30)") == -1.30', parse_number("(1.30)") == -1.30)
check('parse_number("1,234.56") == 1234.56', parse_number("1,234.56") == 1234.56)
check('parse_int("5.4") is None（不猜測四捨五入）', parse_int("5.4") is None)
check('parse_date("01-12-2000") == 2000-12-01', parse_date("01-12-2000") == "2000-12-01")

print("\n== 3. HTML 解析 ==")
html = (ROOT / "tests/fixtures/sample_list.html").read_text(encoding="utf-8")
recs = parse_html_tables(html, FUND_COLUMNS)
check("解析出 3 筆（備註列被丟棄）", len(recs) == 3, f"得到 {len(recs)}")
check("資料截止日期 = 2026-03-31", pipeline.extract_as_of_date(html) == "2026-03-31",
      str(pipeline.extract_as_of_date(html)))
cons = next(r for r in recs if r["fund_name"] == "強積金保守基金")
check("保守基金 FER 為空值（n.a.）", cons["fer_pct"] is None)
check("保守基金 1年回報為 0.0 而非空值", cons["return_1y_annualised"] == 0.0)
check("保守基金 基金規模為空值", cons["fund_size_hkd_million"] is None)
bond = next(r for r in recs if r["fund_name"] == "亞洲債券基金")
check("債券基金 5年年率化回報 = -1.30（括號負數）", bond["return_5y_annualised"] == -1.30)
check("債券基金 成立日期 = 2012-06-15", bond["launch_date"] == "2012-06-15")

print("\n== 4. 輸出檔案 ==")
with tempfile.TemporaryDirectory() as td:
    out = Path(td)
    pipeline.write_csv(recs, out / "funds_latest.csv", FUND_COLUMNS)
    pipeline.write_json(recs, out / "funds_latest.json", FUND_COLUMNS)
    meta = pipeline.write_metadata(out / "metadata.json", as_of_date="2026-03-31",
                                   sources=["https://mfp.mpfa.org.hk/tch/mpp_list.jsp"],
                                   row_count=len(recs), method="html_parse")
    csv_text = (out / "funds_latest.csv").read_text(encoding="utf-8-sig")
    check("CSV 有表頭與 3 行資料", len(csv_text.strip().splitlines()) == 4)
    check('CSV 中 n.a. 寫成空字串而非 0', ",," in csv_text and ",0," not in csv_text.split("\n")[2])
    jd = json.loads((out / "funds_latest.json").read_text(encoding="utf-8"))
    check("JSON 中 n.a. 是 null", jd[1]["fer_pct"] is None)
    check("JSON 中 0.00 是 0.0 不是 null", jd[1]["return_1y_annualised"] == 0.0)
    check("metadata 記錄了截止日期/抓取時間/來源/行數",
          all(meta.get(k) for k in ("data_as_of_date", "scraped_at", "source_urls", "total_rows")))

print("\n== 5. 驗證模組 ==")
bad = [dict(recs[0], risk_level=9), dict(recs[1], risk_level=0)]
r = V.check_risk_level(recs + bad)
check("風險級別越界會被抓出（9 與 0）", (not r.passed) and len(r.data) == 2, r.detail)
check("正常資料的風險級別檢查通過", V.check_risk_level(recs).passed)
zero_inflated = [dict(x, return_1y_annualised=0.0, fer_pct=0.0) for x in recs * 10]
check("n.a. 被誤轉成 0 時會被抓出", not V.check_na_not_zero(zero_inflated).passed)
# 真實分布：少數基金（如強積金保守基金）回報確實為 0.00，比例應遠低於門檻
realistic = [dict(recs[0], return_1y_annualised=(0.0 if i % 20 == 0 else 1.5 + i * 0.01),
                  fer_pct=1.0 + i * 0.001) for i in range(100)]
check("正常分布（5% 的 0）不會誤報 n.a.-as-0", V.check_na_not_zero(realistic).passed)
check("樣本過小時不做 0 值判斷（避免假警報）", V.check_na_not_zero(recs).passed)
cnt = {c.name: c for c in V.check_counts(recs)}
check("行數不足時回報漏抓", not cnt["基金總行數"].passed, cnt["基金總行數"].detail)
check("計劃數不足時回報漏抓", not cnt["計劃數"].passed, cnt["計劃數"].detail)
check("基金類別數為資訊項（不判定成敗）", cnt["基金類別數（資訊）"].informational)
nr = V.null_ratios(recs)
check("空值率計算正確（fer_pct 3 筆中 1 筆空）", abs(nr["fer_pct"]["null_ratio"] - 1/3) < 1e-4)
check("抽樣輸出 3 筆（資料不足 5 筆時取全部）", len(V.sample_for_manual_check(recs, 5)) == 3)

print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} 項\n  - " + "\n  - ".join(failures))
    raise SystemExit(1)
print("全部通過")
