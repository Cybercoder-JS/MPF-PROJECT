#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""強積金基金平台資料抓取（可重複執行）。

兩種資料來源模式，下游清洗/驗證/輸出完全相同：

  模式 A（network）：直連 https://mfp.mpfa.org.hk 抓取
  模式 B（local）  ：讀取 data/raw/ 下手動下載的 CSV / XLSX / XLS / HTML

用法：
  # 模式 B：把平台下載的檔案放進 data/raw/ 後執行
  python scripts/scrape_mpfa_funds.py --mode local

  # 模式 A：域名放行後，先探查端點再抓
  python scripts/scrape_mpfa_funds.py --probe
  python scripts/scrape_mpfa_funds.py --mode network

  # 預設 auto：data/raw/ 有檔案就用模式 B，否則走模式 A
  python scripts/scrape_mpfa_funds.py
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
from mpfa.sources import build_source  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="抓取強積金基金平台的基金資訊表",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="模式 A = 直連平台；模式 B = 讀取 data/raw/ 的手動下載檔案。",
    )
    p.add_argument("--mode", choices=["auto", "network", "local"], default="auto",
                   help="資料來源模式（預設 auto：有本地檔用 local，否則 network）")
    p.add_argument("--raw-dir", default=Path("data/raw"), type=Path,
                   help="模式 B 的原始檔目錄（預設 data/raw）")
    p.add_argument("--as-of", help="手動指定資料截止日期 YYYY-MM-DD（模式 B 無法自動判定時）")
    p.add_argument("--out-dir", default=Path("data"), type=Path)
    p.add_argument("--base-url", default="https://mfp.mpfa.org.hk")
    p.add_argument("--probe-dir", default=Path("data/probe"), type=Path)
    p.add_argument("--strategy", choices=["auto", "download", "html"], default="auto",
                   help="模式 A 的抓取方式")
    p.add_argument("--delay", type=float, default=1.5, help="模式 A 請求之間的延遲秒數")
    p.add_argument("--timeout", type=int, default=45)
    p.add_argument("--probe", action="store_true", help="只做端點探查（模式 A），不抓資料")
    p.add_argument("--no-unit-prices", action="store_true")
    p.add_argument("--validate-only", type=Path, help="對既有 JSON 重跑驗證，不碰網路也不讀 raw")
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

    if args.validate_only:
        records = json.loads(args.validate_only.read_text(encoding="utf-8"))
        result = validate_mod.run_all(records)
        print(validate_mod.format_report(result))
        return 0 if result["all_passed"] else 1

    # 模式 A 才需要 HTTP session；模式 B 完全不建立連線
    session = None
    if args.probe or args.mode != "local":
        session = PoliteSession(base_url=args.base_url, delay=args.delay, timeout=args.timeout)

    try:
        if args.probe:
            log.info("開始探查端點 -> %s", args.probe_dir)
            report = probe_mod.probe(session, args.probe_dir)
            print(probe_mod.summarise(report))
            print(f"\n完整報告：{args.probe_dir / 'probe_report.json'}")
            return 0

        source = build_source(
            args.mode,
            raw_dir=args.raw_dir,
            as_of=args.as_of,
            session=session,
            strategy=args.strategy,
            with_unit_prices=not args.no_unit_prices,
        )
        outcome = pipeline.run(source, args.out_dir)

        print(outcome["report_text"])
        print("\n輸出檔案：")
        for key, path in outcome["paths"].items():
            print(f"  {key:14} {path}")
        meta = outcome["metadata"]
        print(f"\n資料截止日期：{meta['data_as_of_date'] or '（未能判定）'}"
              f"　總行數：{meta['total_rows']}　方式：{meta['scrape_method']}")
        return 0 if outcome["validation"]["all_passed"] else 1

    except BlockedError as e:
        log.error("網路被阻擋，已停止，未嘗試繞過：\n%s", e)
        log.error("改用模式 B：把平台下載的檔案放進 %s，然後執行 --mode local", args.raw_dir)
        return 3
    except FileNotFoundError as e:
        log.error("%s", e)
        return 4
    except RuntimeError as e:
        log.error("%s", e)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
