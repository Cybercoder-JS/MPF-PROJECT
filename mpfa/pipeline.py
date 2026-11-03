# -*- coding: utf-8 -*-
"""流程編排與輸出。

來源（模式 A 直連 / 模式 B 本地檔）由 mpfa/sources.py 提供，本模組只負責
把 FetchResult 清洗後寫成檔案並附上驗證結果，因此兩種模式共用同一條流水線。
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import logging
from pathlib import Path

from .fields import DESC_BY_EN, FUND_COLUMNS, UNIT_PRICE_COLUMNS, ZH_BY_EN
from .parse import extract_as_of_date  # noqa: F401  （對外沿用舊匯入路徑）
from .validate import format_report, run_all

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- 輸出

def write_csv(records: list[dict], path: Path, columns: list[str]) -> None:
    """UTF-8 with BOM，Excel 可直接開。None 寫成空字串（不是 0、不是 "n.a."）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})


def write_json(records: list[dict], path: Path, columns: list[str]) -> None:
    """None 寫成 null。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [{c: r.get(c) for c in columns} for r in records]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_metadata(path: Path, *, as_of_date, sources, row_count, method,
                   unit_price_rows=0, unit_price_source=None, validation=None,
                   file_report=None) -> dict:
    meta = {
        "data_as_of_date": as_of_date,
        "scraped_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "source_urls": sources,
        "total_rows": row_count,
        "scrape_method": method,
        "unit_price_rows": unit_price_rows,
        "unit_price_source": unit_price_source,
        "columns": [
            {"field": c, "zh": ZH_BY_EN.get(c), "description": DESC_BY_EN.get(c)}
            for c in FUND_COLUMNS
        ],
        "null_convention": '平台的 "n.a." 一律輸出為空值（CSV 空字串 / JSON null），絕不轉成 0',
    }
    if file_report:
        meta["input_files"] = file_report
    if validation is not None:
        meta["validation"] = {
            "all_passed": validation["all_passed"],
            "checks": validation["checks"],
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


# ---------------------------------------------------------------- 編排

def run(source, out_dir: Path) -> dict:
    """抓取 -> 驗證 -> 輸出。回傳 {result, validation, metadata, paths}。

    `source` 為任何提供 `.fetch() -> FetchResult` 的物件（模式 A 或模式 B）。
    """
    out_dir = Path(out_dir)
    result = source.fetch()

    if not result.funds:
        raise RuntimeError(
            "一筆基金資料都沒取得。\n"
            "模式 B：確認 data/raw/ 裡的檔案是基金資訊表，且表頭為平台原始欄位名。\n"
            "模式 A：先執行 --probe 檢查頁面結構與端點。"
        )

    log.info("取得基金 %s 筆、單位價格 %s 筆（方式：%s）",
             len(result.funds), len(result.unit_prices), result.method)

    paths = {
        "funds_csv": out_dir / "funds_latest.csv",
        "funds_json": out_dir / "funds_latest.json",
        "metadata": out_dir / "metadata.json",
        "report": out_dir / "validation_report.txt",
    }
    write_csv(result.funds, paths["funds_csv"], FUND_COLUMNS)
    write_json(result.funds, paths["funds_json"], FUND_COLUMNS)

    if result.unit_prices:
        paths["prices_csv"] = out_dir / "unit_prices_latest.csv"
        paths["prices_json"] = out_dir / "unit_prices_latest.json"
        write_csv(result.unit_prices, paths["prices_csv"], UNIT_PRICE_COLUMNS)
        write_json(result.unit_prices, paths["prices_json"], UNIT_PRICE_COLUMNS)

    validation = run_all(result.funds)
    unit_src = next((s for s in result.sources if "price" in s.lower()), None)
    metadata = write_metadata(
        paths["metadata"],
        as_of_date=result.as_of_date,
        sources=result.sources,
        row_count=len(result.funds),
        method=result.method,
        unit_price_rows=len(result.unit_prices),
        unit_price_source=unit_src,
        validation=validation,
        file_report=result.file_report or None,
    )
    report_txt = format_report(validation)
    paths["report"].write_text(report_txt, encoding="utf-8")

    return {"result": result, "validation": validation, "metadata": metadata,
            "paths": paths, "report_text": report_txt}
