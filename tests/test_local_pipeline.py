#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模式 B（本地檔案）端到端測試。不碰網路。

用 scripts/make_sample_raw.py 產生 382 隻基金 / 24 個計劃的合成基金資訊表
HTML（結構鏡像 mpp_list.jsp），跑完整流水線，確認解析、清洗、驗證、輸出都正確。

執行： python tests/test_local_pipeline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import make_sample_raw as gen                        # noqa: E402
from mpfa import pipeline, validate as V             # noqa: E402
from mpfa.sources import LocalSource, build_source   # noqa: E402

failures: list[str] = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'ok ' if cond else 'FAIL'}] {label}" + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(label)


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    raw, out = tmp / "raw", tmp / "out"
    raw.mkdir()

    print("== 1. 產生樣例基金資訊表 HTML ==")
    rows = gen.build_rows(seed=42)
    (raw / "mpp_list_sample.html").write_text(gen.render_html(rows), encoding="utf-8")
    check("382 隻基金 / 24 個計劃", len(rows) == 382 and len({r["scheme"] for r in rows}) == 24,
          f"{len(rows)} 筆 / {len({r['scheme'] for r in rows})} 計劃")

    print("\n== 2. 來源層模式選擇 ==")
    check("mode=local -> LocalSource", isinstance(build_source("local", raw_dir=raw), LocalSource))
    check("mode=auto 有本地檔 -> LocalSource",
          isinstance(build_source("auto", raw_dir=raw), LocalSource))
    try:
        build_source("auto", raw_dir=tmp / "nope")
        check("mode=auto 無本地檔且無 session -> 報錯", False)
    except ValueError:
        check("mode=auto 無本地檔且無 session -> 報錯", True)

    print("\n== 3. 跑完整流水線 ==")
    outcome = pipeline.run(LocalSource(raw), out)
    res, val, meta = outcome["result"], outcome["validation"], outcome["metadata"]
    check("解析 382 筆", len(res.funds) == 382, str(len(res.funds)))
    check("用了 mpp 專用解析器",
          res.file_report[0].get("parser") == "mpp_list_html", str(res.file_report[0].get("parser")))
    check("欄位由解析層決定（33 個）", len(res.columns) == 33, str(len(res.columns)))
    check("曆年年份 [2025..2021]", res.calendar_years == [2025, 2024, 2023, 2022, 2021])
    check("資料截止日期 2026-09-30", res.as_of_date == "2026-09-30", str(res.as_of_date))
    check("頁面自報總數被記錄", res.page_reported_total == 382, str(res.page_reported_total))
    check("method = local_files", res.method == "local_files")

    print("\n== 4. 驗證結果 ==")
    by = {c["check"]: c for c in val["checks"]}
    check("all_passed", val["all_passed"])
    check("無警告", not val["warnings"], str(val["warnings"])[:80])
    check("基金總行數 PASS（在 380-470 區間）", by["基金總行數"]["status"] == "PASS",
          by["基金總行數"]["detail"][:56])
    check("計劃數 PASS", by["計劃數"]["status"] == "PASS")
    check("風險級別 PASS", by["風險級別範圍"]["status"] == "PASS")
    check("n.a. 未被當成 0 PASS", by["n.a. 未被當成 0"]["status"] == "PASS")
    check("費用欄位解析 PASS", by["費用欄位解析"]["status"] == "PASS")
    check("抽樣 5 隻基金", len(val["manual_sample"]) == 5)

    print("\n== 5. n.a. -> null，真實 0 保留 ==")
    byname = {f["fund_name"]: f for f in res.funds}
    na_total = null_total = 0
    for row in rows:
        rec = byname[row["fund"]]
        pairs = [("fund_size_hkd_million", row["size"]), ("risk_level", row["risk"]),
                 ("fer_pct", row["fer"]), ("return_5y_annualised", row["a5"]),
                 ("return_10y_annualised", row["a10"]),
                 ("return_5y_cumulative", row["c5"]), ("return_10y_cumulative", row["c10"])]
        pairs += [(f"return_cy{y}", v) for y, v in zip(res.calendar_years, row["cy"])]
        for f, v in pairs:
            if v is None:
                na_total += 1
                null_total += (rec[f] is None)
    check(f"來源 n.a. {na_total} 格全部成為 null", na_total == null_total, f"對上 {null_total}")
    zeros = [byname[r["fund"]] for r in rows if r["a1"] == 0.0]
    check(f"真實 0.00 保留為 0.0（{len(zeros)} 筆）",
          all(z["return_1y_annualised"] == 0.0 for z in zeros))

    print("\n== 6. 費用：原文 + 數值 ==")
    raws = [f["management_fee_raw"] for f in res.funds]
    check("有「最高 X」寫法", any(r and r.startswith("最高") for r in raws))
    check("有區間寫法", any(r and " - " in r for r in raws))
    check("有純數字寫法", any(r and not r.startswith("最高") and " - " not in r for r in raws))
    for f in res.funds:
        if f["management_fee_raw"] and f["management_fee_raw"].startswith("最高"):
            want = float(f["management_fee_raw"].split()[1])
            check("「最高 X」數值取 X", abs(f["management_fee_pct"] - want) < 1e-9)
            break
    for f in res.funds:
        if f["management_fee_raw"] and " - " in f["management_fee_raw"]:
            lo, hi = (float(x) for x in f["management_fee_raw"].split(" - "))
            check("區間數值取上限", abs(f["management_fee_pct"] - max(lo, hi)) < 1e-9)
            break
    check("每筆都同時有原文與數值（或兩者皆空）",
          all((f["management_fee_raw"] is None) == (f["management_fee_pct"] is None)
              for f in res.funds))

    print("\n== 7. 輸出檔案 ==")
    csv_text = outcome["paths"]["funds_csv"].read_text(encoding="utf-8-sig")
    check("CSV = 1 表頭 + 382 行", len(csv_text.strip().splitlines()) == 383,
          str(len(csv_text.strip().splitlines())))
    check("CSV 不含 'n.a.'", "n.a." not in csv_text)
    check("CSV 含費用原文「最高」", "最高" in csv_text)
    check("CSV 表頭含曆年欄位", "return_cy2025" in csv_text.splitlines()[0])
    jd = json.loads(outcome["paths"]["funds_json"].read_text(encoding="utf-8"))
    check("JSON 382 筆", len(jd) == 382)
    check("JSON 空值為 null", any(v is None for v in jd[0].values()))
    check("metadata 記錄截止日期/行數/方式/年份/頁面自報總數",
          meta["data_as_of_date"] == "2026-09-30" and meta["total_rows"] == 382
          and meta["scrape_method"] == "local_files"
          and meta["calendar_years"] == [2025, 2024, 2023, 2022, 2021]
          and meta["page_reported_total"] == 382)
    check("metadata 含解析診斷（欄位映射）", "parser_diagnostics" in meta)
    check("metadata 欄位說明含中文名",
          all(c["zh"] for c in meta["columns"]), )
    check("驗證報告已輸出", outcome["paths"]["report"].exists())

    print("\n== 8. 失敗路徑 ==")
    empty = tmp / "empty"; empty.mkdir()
    try:
        LocalSource(empty).fetch(); check("空目錄報錯", False)
    except FileNotFoundError as e:
        check("空目錄報錯且訊息可操作", "放進去" in str(e))
    try:
        LocalSource(tmp / "nx").fetch(); check("目錄不存在報錯", False)
    except FileNotFoundError as e:
        check("目錄不存在報錯且訊息可操作", "找不到原始檔目錄" in str(e))

    junk = tmp / "junk"; junk.mkdir()
    (junk / "random.csv").write_text("甲,乙,丙\n1,2,3\n", encoding="utf-8")
    jr = LocalSource(junk).fetch()
    check("表頭無法辨識 -> 0 筆，不產生假資料", len(jr.funds) == 0)
    check("file_report 標示 warning", any("warning" in e for e in jr.file_report))
    try:
        pipeline.run(LocalSource(junk), tmp / "jo"); check("0 筆時流水線中止", False)
    except RuntimeError as e:
        check("0 筆時流水線中止且訊息可操作", "data/raw" in str(e))

    bad_html = junk / "broken.html"
    bad_html.write_text(gen.render_html(rows[:4]).replace(
        '<td class="arCol mpp_tab_green">', '<td class="mpp_tab_green">', 1), encoding="utf-8")
    br = LocalSource(junk).fetch()
    check("結構異常的 HTML 被記錄為 error 而非錯位資料",
          any("MppStructureError" in str(e.get("error", "")) for e in br.file_report))

    print("\n== 9. --as-of 覆寫 ==")
    check("--as-of 參數優先", LocalSource(raw, as_of="2025-12-31").fetch().as_of_date == "2025-12-31")

print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} 項\n  - " + "\n  - ".join(failures))
    raise SystemExit(1)
print("模式 B 端到端：全部通過")
