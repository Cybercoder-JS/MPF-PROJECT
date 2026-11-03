#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模式 B（本地檔案）端到端測試。不碰網路。

用 scripts/make_sample_raw.py 產生 451 隻基金 / 24 個計劃的合成原始檔
（CSV + XLSX 兩種格式、含前導列與大量 n.a.），跑完整流水線，
逐項確認解析、清洗、分類、驗證、輸出都正確。

執行： python tests/test_local_pipeline.py
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import make_sample_raw as gen                      # noqa: E402
from mpfa import pipeline                          # noqa: E402
from mpfa.sources import LocalSource, build_source  # noqa: E402

failures: list[str] = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'ok ' if cond else 'FAIL'}] {label}" + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(label)


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    raw, out = tmp / "raw", tmp / "out"

    print("== 1. 產生樣例原始檔 ==")
    rows = gen.build_rows(seed=42)
    gen.write_csv_file(raw / "fund_info_part1_2026-03-31.csv", rows[:300])
    gen.write_xlsx_file(raw / "fund_info_part2.xlsx", rows[300:])
    n_prices = gen.write_unit_prices(raw / "unit_prices.csv", rows)
    check("產生 451 列基金資料", len(rows) == 451, f"{len(rows)}")
    check("產生 3 個原始檔（CSV + XLSX + 價格）", len(list(raw.iterdir())) == 3)

    print("\n== 2. 來源層：模式選擇 ==")
    check("mode=local 得到 LocalSource", isinstance(build_source("local", raw_dir=raw), LocalSource))
    check("mode=auto 有本地檔時選 LocalSource",
          isinstance(build_source("auto", raw_dir=raw), LocalSource))
    try:
        build_source("auto", raw_dir=tmp / "nope")
        check("mode=auto 無本地檔且無 session 時報錯", False)
    except ValueError:
        check("mode=auto 無本地檔且無 session 時報錯", True)

    print("\n== 3. 跑完整流水線 ==")
    outcome = pipeline.run(LocalSource(raw), out)
    res, val, meta = outcome["result"], outcome["validation"], outcome["metadata"]
    check("基金 451 筆", len(res.funds) == 451, f"{len(res.funds)}")
    check("單位價格 480 列（自動歸類到另一個檔）",
          len(res.unit_prices) == n_prices, f"{len(res.unit_prices)}")
    check("CSV 與 XLSX 兩個檔都被讀入並合併",
          {e["file"] for e in res.file_report} ==
          {"fund_info_part1_2026-03-31.csv", "fund_info_part2.xlsx", "unit_prices.csv"})
    check("檔案分類正確（2 funds + 1 unit_prices）",
          sorted(k for e in res.file_report for k in e["kinds"]) == ["funds", "funds", "unit_prices"])
    check("資料截止日期自動判定為 2026-03-31", res.as_of_date == "2026-03-31", str(res.as_of_date))
    check("method = local_files", res.method == "local_files")

    print("\n== 4. 驗證全部通過 ==")
    check("all_passed", val["all_passed"])
    by = {c["check"]: c for c in val["checks"]}
    check("基金總行數 PASS", by["基金總行數"]["status"] == "PASS", by["基金總行數"]["detail"])
    check("計劃數 PASS（24）", by["計劃數"]["status"] == "PASS", by["計劃數"]["detail"])
    check("風險級別全在 1-7", by["風險級別範圍"]["status"] == "PASS")
    check("n.a. 未被當成 0", by["n.a. 未被當成 0"]["status"] == "PASS")
    check("FER 空值率在上限內",
          by["空值率 基金開支比率(fer_pct)"]["status"] == "PASS")
    check("抽樣 5 隻基金", len(val["manual_sample"]) == 5)

    print("\n== 5. 空值處理：n.a. 數量必須與 null 數量完全相等 ==")
    src = list(csv.reader((raw / "fund_info_part1_2026-03-31.csv").open(encoding="utf-8-sig")))
    data_rows = src[4:]
    na_cells = sum(1 for r in data_rows for c in r[6:] if c == "n.a.")
    byname = {f["fund_name"]: f for f in res.funds}
    numeric_keys = ["fund_size_hkd_million", "fer_pct", "risk_level",
                    "return_1y_annualised", "return_5y_annualised", "return_10y_annualised",
                    "return_since_launch_annualised", "return_1y_cumulative",
                    "return_5y_cumulative", "return_10y_cumulative",
                    "return_since_launch_cumulative"]
    null_cells = sum(1 for r in data_rows for k in numeric_keys if byname[r[2]][k] is None)
    check(f"n.a. {na_cells} 格 == null {null_cells} 格", na_cells == null_cells)
    check("真實 0.00 保留為 0.0 而非 null",
          any(f["return_1y_annualised"] == 0.0 for f in res.funds))
    check("括號負數轉為負值",
          any((f["return_5y_annualised"] or 0) < 0 for f in res.funds))

    print("\n== 6. 原文保真（不被 NFKC 改寫）==")
    check("基金名稱保留全角「－」",
          any("－" in (f["fund_name"] or "") for f in res.funds),
          next(f["fund_name"] for f in res.funds))

    print("\n== 7. 輸出檔案 ==")
    csv_text = outcome["paths"]["funds_csv"].read_text(encoding="utf-8-sig")
    check("CSV = 1 表頭 + 451 行", len(csv_text.strip().splitlines()) == 452)
    check("CSV 不含 'n.a.' 字樣", "n.a." not in csv_text)
    check("CSV 不含括號負數寫法", "(" not in csv_text)
    jd = json.loads(outcome["paths"]["funds_json"].read_text(encoding="utf-8"))
    check("JSON 451 筆且空值為 null", len(jd) == 451 and any(v is None for v in jd[0].values()))
    check("metadata 記錄截止日期/來源/行數/方式",
          meta["data_as_of_date"] == "2026-03-31" and meta["total_rows"] == 451
          and meta["scrape_method"] == "local_files" and len(meta["source_urls"]) == 3)
    check("metadata 含每個輸入檔的解析結果", len(meta["input_files"]) == 3)
    check("單位價格檔已輸出", outcome["paths"]["prices_csv"].exists())
    check("驗證報告已輸出", outcome["paths"]["report"].exists())

    print("\n== 8. 失敗路徑 ==")
    empty = tmp / "empty"
    empty.mkdir()
    try:
        LocalSource(empty).fetch()
        check("空目錄會報錯", False)
    except FileNotFoundError as e:
        check("空目錄報錯且訊息可操作", "放進去" in str(e))
    try:
        LocalSource(tmp / "does_not_exist").fetch()
        check("目錄不存在會報錯", False)
    except FileNotFoundError as e:
        check("目錄不存在報錯且訊息可操作", "找不到原始檔目錄" in str(e))

    junk = tmp / "junk"
    junk.mkdir()
    (junk / "random.csv").write_text("甲,乙,丙\n1,2,3\n", encoding="utf-8")
    jr = LocalSource(junk).fetch()
    check("表頭無法辨識時不報假資料（0 筆）", len(jr.funds) == 0)
    check("並在 file_report 標示 warning",
          any("warning" in e for e in jr.file_report), str(jr.file_report))
    try:
        pipeline.run(LocalSource(junk), tmp / "junk_out")
        check("0 筆時流水線會中止", False)
    except RuntimeError as e:
        check("0 筆時流水線中止且訊息可操作", "data/raw" in str(e))

    print("\n== 9. --as-of 覆寫與 AS_OF.txt ==")
    check("--as-of 參數優先", LocalSource(raw, as_of="2025-12-31").fetch().as_of_date == "2025-12-31")
    (raw / "AS_OF.txt").write_text("30-09-2025", encoding="utf-8")
    check("AS_OF.txt 不被當成資料檔", len(LocalSource(raw).fetch().funds) == 451)

print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} 項\n  - " + "\n  - ".join(failures))
    raise SystemExit(1)
print("模式 B 端到端：全部通過")
