#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生「樣例」原始檔，用來驗證模式 B 的整條流水線。

產生的檔案刻意模仿平台下載檔的形狀：標題與截止日期的前導列、繁體中文欄位
標題、大量 "n.a."、括號負數、千分位。資料本身是合成的，受託人與基金名稱
都帶「示例」字樣，不可當作真實強積金資料使用。

用法：
  python scripts/make_sample_raw.py --out-dir /tmp/sample_raw
  python scripts/scrape_mpfa_funds.py --mode local --raw-dir /tmp/sample_raw --out-dir /tmp/sample_out
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

AS_OF = "31-03-2026"
N_FUNDS = 451          # 與 validate.EXPECTED_FUND_ROWS 一致
N_SCHEMES = 24         # 與 validate.EXPECTED_SCHEMES 一致

HEADER = [
    "受託人", "計劃名稱", "基金名稱", "基金類別", "基金種類", "成立日期",
    "基金規模\n(百萬港元)", "基金開支比率 (FER)\n(%)", "風險級別",
    "1年年率化回報", "5年年率化回報", "10年年率化回報", "成立以來年率化回報",
    "1年累積回報", "5年累積回報", "10年累積回報", "成立以來累積回報",
]

FUND_TYPES = [
    ("股票基金", "股票基金－環球"), ("股票基金", "股票基金－香港"),
    ("股票基金", "股票基金－亞洲"), ("混合資產基金", "混合資產基金－60-80%股票"),
    ("混合資產基金", "混合資產基金－40-60%股票"), ("債券基金", "債券基金－環球"),
    ("債券基金", "債券基金－亞洲"), ("強積金保守基金", "強積金保守基金"),
    ("保證基金", "保證基金"), ("貨幣市場基金", "貨幣市場基金－港元"),
]
RISK_BY_TYPE = {
    "股票基金": (5, 7), "混合資產基金": (3, 5), "債券基金": (2, 4),
    "強積金保守基金": (1, 1), "保證基金": (1, 2), "貨幣市場基金": (1, 2),
}


def _num(v: float | None, dp: int = 2, thousands: bool = False) -> str:
    """格式化成平台風格：None -> n.a.、負數用括號、可加千分位。"""
    if v is None:
        return "n.a."
    if v < 0:
        inner = f"{abs(v):,.{dp}f}" if thousands else f"{abs(v):.{dp}f}"
        return f"({inner})"
    return f"{v:,.{dp}f}" if thousands else f"{v:.{dp}f}"


def build_rows(seed: int = 42) -> list[list[str]]:
    rng = random.Random(seed)
    rows = []
    for i in range(N_FUNDS):
        scheme_no = i % N_SCHEMES
        trustee = f"示例受託人{chr(0x7532 + scheme_no % 10)}{scheme_no // 10 + 1}有限公司"
        scheme = f"示例強積金計劃 {scheme_no + 1:02d}"
        ftype, fcat = FUND_TYPES[i % len(FUND_TYPES)]
        fund = f"示例{fcat}基金 {i + 1:03d}"

        age_years = rng.choice([0.5, 1.5, 3, 6, 9, 12, 18, 24])
        year = 2026 - int(age_years)
        launch = f"{rng.randint(1, 28):02d}-{rng.randint(1, 12):02d}-{year}"

        # 新基金沒有長期回報 -> n.a.（不是 0）
        has_5y = age_years >= 5
        has_10y = age_years >= 10
        conservative = ftype in ("強積金保守基金", "貨幣市場基金")

        size = None if rng.random() < 0.03 else round(rng.uniform(8, 9500), 2)
        fer = None if rng.random() < 0.08 else round(rng.uniform(0.35, 2.6), 2)
        lo, hi = RISK_BY_TYPE[ftype]
        risk = rng.randint(lo, hi)

        def ret(scale: float) -> float:
            return round(rng.uniform(-scale, scale * 1.4), 2)

        r1 = 0.00 if conservative and rng.random() < 0.25 else ret(14)
        r5 = round(rng.uniform(-4, 11), 2) if has_5y else None
        r10 = round(rng.uniform(-2, 9), 2) if has_10y else None
        rsl = round(rng.uniform(-3, 10), 2)
        c1 = r1
        c5 = round(((1 + r5 / 100) ** 5 - 1) * 100, 2) if r5 is not None else None
        c10 = round(((1 + r10 / 100) ** 10 - 1) * 100, 2) if r10 is not None else None
        csl = round(((1 + rsl / 100) ** age_years - 1) * 100, 2)

        rows.append([
            trustee, scheme, fund, fcat, ftype, launch,
            _num(size, 2, thousands=True), _num(fer), str(risk),
            _num(r1), _num(r5), _num(r10), _num(rsl),
            _num(c1), _num(c5), _num(c10), _num(csl),
        ])
    return rows


def write_csv_file(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        # 前導列：模仿平台下載檔的標題與截止日期
        w.writerow(["強積金基金平台 － 基金資訊表（示例合成資料，非真實資料）"])
        w.writerow([f"資料截至 {AS_OF}"])
        w.writerow([])
        w.writerow(HEADER)
        w.writerows(rows)


def write_xlsx_file(path: Path, rows: list[list[str]]) -> None:
    import openpyxl
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "基金資訊表"
    ws.append(["強積金基金平台 － 基金資訊表（示例合成資料，非真實資料）"])
    ws.append([f"資料截至 {AS_OF}"])
    ws.append([])
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    wb.save(path)
    wb.close()


def write_unit_prices(path: Path, rows: list[list[str]], months: int = 12, seed: int = 7) -> int:
    """為前 40 隻基金產生月末單位價格。"""
    rng = random.Random(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = []
    for r in rows[:40]:
        trustee, scheme, fund = r[0], r[1], r[2]
        price = rng.uniform(9, 260)
        for m in range(months):
            month = 3 - m
            year = 2026 + (month - 1) // 12
            month = (month - 1) % 12 + 1
            last_day = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
            price *= 1 + rng.uniform(-0.05, 0.05)
            out.append([trustee, scheme, fund,
                        f"{last_day:02d}-{month:02d}-{year}",
                        f"{price:.4f}", "HKD"])
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["強積金基金平台 － 基金月末單位價格（示例合成資料，非真實資料）"])
        w.writerow([f"資料截至 {AS_OF}"])
        w.writerow([])
        w.writerow(["受託人", "計劃名稱", "基金名稱", "日期", "單位價格", "貨幣"])
        w.writerows(out)
    return len(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="產生模式 B 的樣例原始檔（合成資料）")
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rows = build_rows(args.seed)
    # 刻意拆成兩個檔案、兩種格式，以驗證多檔案合併與 CSV/XLSX 雙路徑
    split = 300
    write_csv_file(args.out_dir / f"fund_info_part1_{AS_OF[-4:]}-{AS_OF[3:5]}-{AS_OF[:2]}.csv", rows[:split])
    write_xlsx_file(args.out_dir / "fund_info_part2.xlsx", rows[split:])
    n_prices = write_unit_prices(args.out_dir / "unit_prices.csv", rows)

    print(f"已產生樣例原始檔於 {args.out_dir}")
    print(f"  fund_info_part1_*.csv   {split} 隻基金（CSV，含前導列）")
    print(f"  fund_info_part2.xlsx    {len(rows) - split} 隻基金（XLSX）")
    print(f"  unit_prices.csv         {n_prices} 列月末單位價格")
    print(f"  合計 {len(rows)} 隻基金 / {N_SCHEMES} 個計劃，資料截至 {AS_OF}")
    print("\n注意：這是合成資料，僅用於驗證流水線，不可當作真實強積金資料。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
