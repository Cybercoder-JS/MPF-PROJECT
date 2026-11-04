#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""單元測試：欄位比對、值正規化、費用解析、輸出、驗證。不碰網路。

執行： python tests/test_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mpfa import pipeline, validate as V                       # noqa: E402
from mpfa.fields import FUND_COLUMNS, fund_columns, zh_for     # noqa: E402
from mpfa.normalize import (                                   # noqa: E402
    clean_text, is_na, parse_date, parse_fee, parse_int, parse_number, resolve_header,
)
from mpfa.parse import extract_as_of_date, parse_csv           # noqa: E402

failures: list[str] = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'ok ' if cond else 'FAIL'}] {label}" + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(label)


print("== 1. 欄位標題對應（頁面實際欄位名）==")
for raw, want in [
    ("計劃", "scheme_name"), ("成分基金", "fund_name"), ("受託人", "trustee"),
    ("基金類別", "fund_category"), ("推出日期", "launch_date"),
    ("基金規模 （百萬港元）", "fund_size_hkd_million"), ("風險級別", "risk_level"),
    ("最近期基金 開支比率\n            (%)", "fer_pct"),
    ("基金管理費 (% p.a.)", "management_fee_raw"),
    ("受託人費／ 保管人費", "trustee_custodian_fee_raw"),
    ("積金易平台費", "empf_platform_fee_raw"),
    ("成員服務費", "member_service_fee_raw"),
    ("投資管理費", "investment_management_fee_raw"),
    ("保證費 (% p.a.)", "guarantee_fee_raw"),
]:
    got = resolve_header(raw)
    check(f"{raw.strip()[:16]!r} -> {want}", got == want, f"得到 {got}")
check("「受託人費／保管人費」不會被誤配成 trustee",
      resolve_header("受託人費／ 保管人費") != "trustee")

print("\n== 2. n.a. 是空值，真實的 0 要保留 ==")
for v in ("n.a.", "N.A.", "--", "不適用", "", None):
    check(f"is_na({v!r})", is_na(v))
check('parse_number("n.a.") is None', parse_number("n.a.") is None)
check('parse_number("0.00") == 0.0', parse_number("0.00") == 0.0)
check('parse_number("(1.30)") == -1.30', parse_number("(1.30)") == -1.30)
check('parse_number("12,730.70") == 12730.70', parse_number("12,730.70") == 12730.70)
check('parse_int("5.4") is None（不猜四捨五入）', parse_int("5.4") is None)
check('parse_date("10-07-2009") == 2009-07-10', parse_date("10-07-2009") == "2009-07-10")

print("\n== 3. 原文保真（值不做 NFKC）==")
check("全角「－」保留", clean_text("景順環球債券基金－單位類別H") == "景順環球債券基金－單位類別H")
check("全角括號保留", clean_text("BCT（強積金）行業計劃") == "BCT（強積金）行業計劃")
check("換行壓成空格", clean_text("示例受託人\n信託") == "示例受託人 信託")

print("\n== 4. 費用解析：原文 + 數值（區間取上限、「最高 X」取 X）==")
for raw, want_raw, want_val, want_basis in [
    ("最高 1.205", "最高 1.205", 1.205, "max"),
    ("0.84 - 0.96", "0.84 - 0.96", 0.96, "range"),
    ("0.96", "0.96", 0.96, "exact"),
    ("0", "0", 0.0, "exact"),
    ("n.a.", None, None, None),
    ("", None, None, None),
]:
    r, v, b = parse_fee(raw)
    check(f"parse_fee({raw!r}) -> ({want_raw!r}, {want_val}, {want_basis})",
          r == want_raw and v == want_val and b == want_basis, f"得到 {(r, v, b)}")
check("負數不被當成區間", parse_fee("-1.26")[1] == -1.26)
check("看不懂的寫法：原文保留、數值留空", parse_fee("另行約定")[:2] == ("另行約定", None))

print("\n== 5. 資料截止日期 ==")
for t, want in [("最新資料截至2026年09月30日", "2026-09-30"),
                ("<html><p>資料截至 30-09-2026</p></html>", "2026-09-30"),
                ("As at 30 September 2026", "2026-09-30"),
                ("沒有日期", None)]:
    check(f"{t[:28]!r} -> {want}", extract_as_of_date(t) == want, str(extract_as_of_date(t)))

print("\n== 6. 動態曆年回報欄位 ==")
cols = fund_columns([2026, 2025, 2024])
check("年份驅動欄位名", "return_cy2026" in cols and "return_cy2021" not in cols)
check("曆年欄位中文名", zh_for("return_cy2026") == "曆年回報 2026")
check("預設欄位共 33 個", len(FUND_COLUMNS) == 33, str(len(FUND_COLUMNS)))

print("\n== 7. 通用 CSV 路徑（非 mpp 頁面時的回退）==")
csvdata = ("計劃,成分基金,受託人,基金類別,推出日期,風險級別,最近期基金開支比率\n"
           "甲計劃,甲基金,甲信託,股票基金 - 環球,01-12-2000,6,1.25\n"
           "乙計劃,乙基金,乙信託,債券基金 - 環球,15-06-2012,n.a.,n.a.\n").encode()
recs = parse_csv(csvdata)
check("解析 2 筆", len(recs) == 2, str(len(recs)))
check("風險級別 n.a. -> None", recs[1]["risk_level"] is None)
check("FER n.a. -> None", recs[1]["fer_pct"] is None)
check("日期轉 ISO", recs[0]["launch_date"] == "2000-12-01")

print("\n== 8. 輸出：CSV 空字串 / JSON null ==")
sample = [{c: None for c in FUND_COLUMNS} | {
    "scheme_name": "甲計劃", "fund_name": "甲基金", "trustee": "甲信託",
    "fund_category": "股票基金 - 環球", "launch_date": "2000-12-01",
    "risk_level": 6, "fer_pct": 1.25, "return_1y_annualised": 0.0,
    "management_fee_raw": "最高 0.68", "management_fee_pct": 0.68}]
with tempfile.TemporaryDirectory() as td:
    out = Path(td)
    pipeline.write_csv(sample, out / "f.csv", FUND_COLUMNS)
    pipeline.write_json(sample, out / "f.json", FUND_COLUMNS)
    text = (out / "f.csv").read_text(encoding="utf-8-sig")
    check("CSV 不含 'n.a.'", "n.a." not in text)
    check("CSV 保留費用原文", "最高 0.68" in text)
    jd = json.loads((out / "f.json").read_text(encoding="utf-8"))
    check("JSON 空值為 null", jd[0]["return_10y_annualised"] is None)
    check("JSON 真實 0.0 不是 null", jd[0]["return_1y_annualised"] == 0.0)
    meta = pipeline.write_metadata(out / "m.json", as_of_date="2026-09-30",
                                   sources=["local:x.html"], row_count=1,
                                   method="local_files", columns=FUND_COLUMNS,
                                   calendar_years=[2025], page_reported_total=382)
    check("metadata 記錄截止日期/行數/頁面自報總數",
          meta["data_as_of_date"] == "2026-09-30" and meta["total_rows"] == 1
          and meta["page_reported_total"] == 382)

print("\n== 9. 驗證：行數用區間，超出報 WARN 而非 FAIL ==")
mk = lambda n, s: [{c: None for c in FUND_COLUMNS} | {
    "scheme_name": f"計劃{i % s}", "fund_name": f"基金{i}",
    "fund_category": "股票基金 - 環球", "risk_level": 4,
    "fer_pct": 1.0} for i in range(n)]
by = lambda recs: {c.name: c for c in V.check_counts(recs)}
check("451 行（已核實的實際值）-> PASS", by(mk(451, 24))["基金總行數"].level == V.PASS)
check("382 行（頁面計數器值）-> PASS", by(mk(382, 24))["基金總行數"].level == V.PASS)
check("380 行（下界）-> PASS", by(mk(380, 24))["基金總行數"].level == V.PASS)
check("470 行（上界）-> PASS", by(mk(470, 24))["基金總行數"].level == V.PASS)
c370 = by(mk(370, 24))["基金總行數"]
check("370 行 -> WARN 且印出實際值", c370.level == V.WARN and "370" in c370.detail, c370.detail[:60])
c500 = by(mk(500, 24))["基金總行數"]
check("500 行 -> WARN 且印出實際值", c500.level == V.WARN and "500" in c500.detail)
check("WARN 不讓 all_passed 變 False", V.run_all(mk(500, 24))["all_passed"])
check("WARN 會進 warnings 清單", len(V.run_all(mk(500, 24))["warnings"]) >= 1)
check("計劃數偏離 -> WARN", by(mk(382, 10))["計劃數"].level == V.WARN)
check("基金類別數是 INFO", by(mk(382, 24))["基金類別數（資訊）"].level == V.INFO)

print("\n== 10. 驗證：風險級別、n.a.-as-0、費用解析 ==")
good = mk(382, 24)
bad = [dict(good[0], risk_level=9), dict(good[1], risk_level=0)]
r = V.check_risk_level(good + bad)
check("風險級別越界 -> FAIL 且逐筆列出", r.level == V.FAIL and len(r.data) == 2, r.detail[:50])
check("正常資料 -> PASS", V.check_risk_level(good).level == V.PASS)
zero = [dict(x, return_1y_annualised=0.0) for x in good]
check("n.a. 被誤轉成 0 -> FAIL", V.check_na_not_zero(zero).level == V.FAIL)
realistic = [dict(x, return_1y_annualised=(0.0 if i % 20 == 0 else 1.5 + i * 0.01))
             for i, x in enumerate(good)]
check("正常分布（5% 的 0）-> PASS", V.check_na_not_zero(realistic).level == V.PASS)
check("樣本過小時不做 0 值判斷", V.check_na_not_zero(good[:5]).level == V.PASS)
unparsed = [dict(good[0], management_fee_raw="另行約定", management_fee_pct=None)]
check("費用有原文無數值 -> WARN", V.check_fee_parsing(unparsed).level == V.WARN)
check("費用正常 -> PASS",
      V.check_fee_parsing([dict(good[0], management_fee_raw="0.68", management_fee_pct=0.68)]).level == V.PASS)
nr = V.null_ratios(good)
check("空值率計算", nr["return_10y_annualised"]["null_ratio"] == 1.0)
check("抽樣 5 筆", len(V.sample_for_manual_check(good, 5)) == 5)

print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} 項\n  - " + "\n  - ".join(failures))
    raise SystemExit(1)
print("全部通過")
