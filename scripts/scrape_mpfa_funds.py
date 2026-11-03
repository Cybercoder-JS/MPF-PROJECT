#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""強積金基金平台資料抓取（可重複執行）。

用法：
  # 1) 解封網路後，先探查端點，用真實證據決定抓取方式
  python scripts/scrape_mpfa_funds.py --probe

  # 2) 正式抓取 + 驗證 + 輸出
  python scripts/scrape_mpfa_funds.py

  # 其他
  --strategy download|html|auto   指定抓取方式（預設 auto：先試下載端點）
  --no-unit-prices                跳過月末單位價格
  --delay 2.0                     調整請求間延遲（秒）
  --out-dir data                  輸出目錄
  --validate-only data/funds_latest.json   只對既有檔案重跑驗證
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mpfa import pipeline, probe as probe_mod, validate as validate_mod  # noqa: E402
from mpfa.fetch import BlockedError, PoliteSession  # noqa: E402
from mpfa.fields import FUND_COLUMNS, UNIT_PRICE_COLUMNS  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="抓取強積金基金平台的基金資訊表")
    p.add_argument("--base-url", default="https://mfp.mpfa.org.hk")
    p.add_argument("--out-dir", default="data", type=Path)
    p.add_argument("--probe-dir", default=Path("data/probe"), type=Path)
    p.add_argument("--strategy", choices=["auto", "download", "html"], default="auto")
    p.add_argument("--delay", type=float, default=1.5, help="請求之間的延遲秒數")
    p.add_argument("--timeout", type=int, default=45)
    p.add_argument("--probe", action="store_true", help="只做端點探查，不抓資料")
    p.add_argument("--no-unit-prices", action="store_true")
    p.add_argument("--validate-only", type=Path, help="對既有 JSON 重跑驗證")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("mpfa")

    # 只重跑驗證，不碰網路
    if args.validate_only:
        records = json.loads(args.validate_only.read_text(encoding="utf-8"))
        result = validate_mod.run_all(records)
        print(validate_mod.format_report(result))
        return 0 if result["all_passed"] else 1

    session = PoliteSession(base_url=args.base_url, delay=args.delay, timeout=args.timeout)

    try:
        if args.probe:
            log.info("開始探查端點 -> %s", args.probe_dir)
            report = probe_mod.probe(session, args.probe_dir)
            print(probe_mod.summarise(report))
            print(f"\n完整報告：{args.probe_dir / 'probe_report.json'}")
            return 0

        log.info("開始抓取（策略 =%s，延遲 =%ss）", args.strategy, args.delay)
        result = pipeline.scrape_funds(session, strategy=args.strategy)
        records = result["records"]
        if not records:
            log.error("一筆都沒抓到。先執行 --probe 檢查頁面結構與端點。")
            return 2
        log.info("抓到 %s 筆（方式：%s）", len(records), result["method"])

        unit = {"records": [], "source": None}
        if not args.no_unit_prices:
            try:
                unit = pipeline.scrape_unit_prices(session)
                log.info("月末單位價格：%s 筆", len(unit["records"]))
            except BlockedError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("單位價格抓取失敗（不影響主檔）：%s", e)

        out = args.out_dir
        pipeline.write_csv(records, out / "funds_latest.csv", FUND_COLUMNS)
        pipeline.write_json(records, out / "funds_latest.json", FUND_COLUMNS)
        if unit["records"]:
            pipeline.write_csv(unit["records"], out / "unit_prices_latest.csv", UNIT_PRICE_COLUMNS)
            pipeline.write_json(unit["records"], out / "unit_prices_latest.json", UNIT_PRICE_COLUMNS)

        validation = validate_mod.run_all(records)
        pipeline.write_metadata(
            out / "metadata.json",
            as_of_date=result["as_of_date"],
            sources=result["sources"],
            row_count=len(records),
            method=result["method"],
            unit_price_rows=len(unit["records"]),
            unit_price_source=unit["source"],
            validation=validation,
        )
        report_txt = validate_mod.format_report(validation)
        (out / "validation_report.txt").write_text(report_txt, encoding="utf-8")
        print(report_txt)
        print(f"\n輸出：{out/'funds_latest.csv'}, {out/'funds_latest.json'}, {out/'metadata.json'}")
        return 0 if validation["all_passed"] else 1

    except BlockedError as e:
        log.error("網路被阻擋，已停止，未嘗試繞過：\n%s", e)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
