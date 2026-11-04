#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量結構不變量核驗：若欄位錯位，這些數學關係會大面積破裂。

這是獨立於 mpfa 套件的交叉檢查 —— 它只讀輸出的 JSON，用回報之間的數學關係
反向驗證欄位映射是否正確，不依賴解析層的任何假設。

用法：
  python scripts/check_invariants.py data/funds_latest.json
  python scripts/check_invariants.py data/funds_latest.json --as-of 2026-09-30

結束碼：0 全部通過 / 1 有不變量破裂。
"""
import argparse, json, datetime as dt, re, sys

_ap = argparse.ArgumentParser(description="核驗抓取結果的結構不變量")
_ap.add_argument("json_path")
_ap.add_argument("--as-of", help="資料截止日期 YYYY-MM-DD（預設讀 data/metadata.json）")
_args = _ap.parse_args()

recs = json.load(open(_args.json_path, encoding="utf-8"))
_as_of = _args.as_of
if not _as_of:
    try:
        import pathlib
        _m = json.load(open(pathlib.Path(_args.json_path).parent / "metadata.json", encoding="utf-8"))
        _as_of = _m.get("data_as_of_date")
    except Exception:
        pass
if not _as_of:
    print("找不到資料截止日期，請用 --as-of 指定"); raise SystemExit(2)
AS_OF = dt.date(*(int(x) for x in _as_of.split("-")))
print(f"資料截止日期：{AS_OF}")
_failed = 0
print(f"樣本: {len(recs)} 筆\n")

def rpt(name, checked, bad, examples, tol):
    global _failed
    if bad: _failed += 1
    status = "OK" if not bad else "**破裂**"
    print(f"{status:>8}  {name:<46} 檢查 {checked:4}  不符 {len(bad):3}  (容差 {tol})")
    for e in examples[:3]: print(f"              {e}")

# 1) 一年期：累積回報 == 年率化回報（定義上相同）
bad, checked, ex = [], 0, []
for r in recs:
    a, c = r["return_1y_annualised"], r["return_1y_cumulative"]
    if a is None or c is None: continue
    checked += 1
    if abs(a - c) > 1e-9:
        bad.append(r); ex.append(f"{r['fund_name']}: ann={a} cum={c}")
rpt("一年期 累積 == 年率化", checked, bad, ex, "0")

# 2/3) 五年、十年：(1+ann)^n - 1 == cum
for n, af, cf in ((5,"return_5y_annualised","return_5y_cumulative"),
                  (10,"return_10y_annualised","return_10y_cumulative")):
    bad, checked, ex = [], 0, []
    for r in recs:
        a, c = r[af], r[cf]
        if a is None or c is None: continue
        checked += 1
        pred = ((1 + a/100) ** n - 1) * 100
        if abs(pred - c) > 1.0:
            bad.append(r); ex.append(f"{r['fund_name']}: ann={a} -> 推算 {pred:.2f} vs cum={c}")
    rpt(f"{n}年期 (1+年率化)^{n}-1 == 累積", checked, bad, ex, "±1.0 個百分點")

# 4) 推出至今：用推出日期算年數
bad, checked, ex = [], 0, []
for r in recs:
    a, c, d = r["return_since_launch_annualised"], r["return_since_launch_cumulative"], r["launch_date"]
    if a is None or c is None or not d: continue
    y, m, dd = (int(x) for x in d.split("-"))
    yrs = (AS_OF - dt.date(y, m, dd)).days / 365.25
    if yrs < 1: continue
    checked += 1
    pred = ((1 + a/100) ** yrs - 1) * 100
    tol = max(2.0, abs(c) * 0.05)
    if abs(pred - c) > tol:
        bad.append(r); ex.append(f"{r['fund_name']}: ann={a} {yrs:.1f}年 -> 推算 {pred:.1f} vs cum={c}")
rpt("推出至今 (1+年率化)^年數-1 == 累積", checked, bad, ex, "±max(2, 5%)")

# 5) 風險級別整數且 1-7
bad = [r for r in recs if r["risk_level"] is not None and (not isinstance(r["risk_level"], int) or not 1 <= r["risk_level"] <= 7)]
rpt("風險級別 ∈ 1..7 且為整數", sum(1 for r in recs if r["risk_level"] is not None), bad, [], "-")

# 6) FER 與費用在合理範圍（錯位到回報欄會立刻爆掉）
for f, lo, hi in (("fer_pct",0,6),("management_fee_pct",0,5),("empf_platform_fee_pct",0,2),
                  ("guarantee_fee_pct",0,5),("fund_size_hkd_million",0,500000)):
    vals = [r[f] for r in recs if r[f] is not None]
    bad = [v for v in vals if not lo <= v <= hi]
    rpt(f"{f} ∈ [{lo},{hi}]", len(vals), bad, [f"離群值: {bad[:5]}"] if bad else [], "-")

# 7) 費用分項之和 vs 基金管理費（頁面註明未必相等，僅觀察）
diffs = []
for r in recs:
    parts = [r[f"{k}_pct"] for k in ("trustee_custodian_fee","empf_platform_fee",
                                     "member_service_fee","investment_management_fee")]
    if any(p is None for p in parts) or r["management_fee_pct"] is None: continue
    diffs.append(abs(sum(parts) - r["management_fee_pct"]))
if diffs:
    close = sum(1 for d in diffs if d < 0.01)
    print(f"\n    資訊  分項之和 vs 基金管理費：{len(diffs)} 筆可比，"
          f"{close} 筆相等（{close/len(diffs):.0%}），"
          f"中位差 {sorted(diffs)[len(diffs)//2]:.4f}")
    print("          （頁面註明：因收費豁免或費用回扣，分項之和未必等於基金管理費）")

# 8) 計劃／基金命名觀察
names = {(r["scheme_name"], re.sub(r"\s*[-－]\s*單位類別.*$", "", r["fund_name"])) for r in recs}
print(f"\n    資訊  去掉「單位類別」後的 (計劃,基金) 去重數：{len(names)}")
print(f"    資訊  含「單位類別」的基金筆數：{sum(1 for r in recs if '單位類別' in r['fund_name'])}")

print()
if _failed:
    print(f"有 {_failed} 項不變量破裂 —— 欄位映射可能錯位，請檢查解析層。")
    sys.exit(1)
print("全部不變量通過。")
