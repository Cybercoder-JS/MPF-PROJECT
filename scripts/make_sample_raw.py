#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生「樣例」基金資訊表 HTML，用來驗證整條流水線。

結構刻意鏡像 mpp_list.jsp 的真實標記：
  * 三列表頭（分組標題 / 主標題用 rowspan / 期間子標題）
  * 回報欄用 arCol / crCol / cyrCol class 標記三組視圖
  * 資料列固定 30 格，其中 3 格（勾選框、間隔、詳細內容）整表皆空
  * 費用欄混有「最高 X」、「X - Y」區間與純數字
  * 大量 "n.a."、千分位、負數
  * 頁面自報的「已選擇的成分基金總數」與「最新資料截至」字樣
  * 篩選器與註釋表格（解析時應被跳過）

資料本身是合成的，計劃與基金名稱都帶「示例」字樣，不可當作真實強積金資料。

用法：
  python scripts/make_sample_raw.py --out-dir /tmp/sample_raw
  python scripts/scrape_mpfa_funds.py --mode local --raw-dir /tmp/sample_raw --out-dir /tmp/sample_out
"""

from __future__ import annotations

import argparse
import html as _html
import random
from pathlib import Path

AS_OF_Y, AS_OF_M, AS_OF_D = 2026, 9, 30
N_FUNDS = 382      # 落在 validate.MIN_FUND_ROWS..MAX_FUND_ROWS 區間內
N_SCHEMES = 24
CALENDAR_YEARS = [2025, 2024, 2023, 2022, 2021]

CATEGORIES = [
    ("股票基金 - 亞洲股票基金", (5, 7)),
    ("股票基金 - 環球股票基金", (5, 7)),
    ("股票基金 - 香港股票基金", (6, 7)),
    ("混合資產基金 - 61% 至 80% 股票", (4, 6)),
    ("混合資產基金 - 41% 至 60% 股票", (3, 5)),
    ("混合資產基金 - 21% 至 40% 股票", (3, 4)),
    ("混合資產基金 - 預設投資策略-核心累積基金", (4, 5)),
    ("混合資產基金 - 預設投資策略-65歲後基金", (3, 4)),
    ("債券基金 - 環球債券基金", (2, 4)),
    ("貨幣市場基金 — 強積金保守基金", (1, 1)),
    ("保證基金", (1, 2)),
]


def _na_or(v, fmt="{:.2f}", thousands=False):
    if v is None:
        return "n.a."
    return (f"{v:,.2f}" if thousands else fmt.format(v))


def _fee(rng: random.Random, base: float) -> str:
    """隨機產生三種費用寫法之一。"""
    r = rng.random()
    if r < 0.35:
        return f"最高 {base:.4g}"
    if r < 0.45:
        lo = base * 0.85
        return f"{lo:.4g} - {base:.4g}"
    return f"{base:.4g}"


def build_rows(seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for i in range(N_FUNDS):
        sno = i % N_SCHEMES
        cat, (rlo, rhi) = CATEGORIES[i % len(CATEGORIES)]
        conservative = "強積金保守基金" in cat

        age = rng.choice([0.5, 1.5, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0])
        year = AS_OF_Y - int(age)
        launch = f"{rng.randint(1,28):02d}-{rng.randint(1,12):02d}-{year}"

        a1 = 0.00 if conservative and rng.random() < 0.3 else round(rng.uniform(-18, 26), 2)
        a5 = round(rng.uniform(-5, 13), 2) if age >= 5 else None
        a10 = round(rng.uniform(-2, 11), 2) if age >= 10 else None
        asl = round(rng.uniform(-3, 12), 2)
        comp = lambda a, n: None if a is None else round(((1 + a/100) ** n - 1) * 100, 2)

        rows.append(dict(
            scheme=f"示例強積金計劃 {sno+1:02d}",
            fund=f"示例{cat.split(' ')[0]}基金 {i+1:03d}",
            trustee=f"示例受託人{chr(0x7532 + sno % 8)}信託",
            category=cat,
            launch=launch,
            size=None if rng.random() < 0.02 else round(rng.uniform(8, 14000), 2),
            risk=None if rng.random() < 0.03 else rng.randint(rlo, rhi),
            fer=None if rng.random() < 0.02 else round(rng.uniform(0.35, 2.6), 5),
            a1=a1, a5=a5, a10=a10, asl=asl,
            c1=a1, c5=comp(a5, 5), c10=comp(a10, 10), csl=comp(asl, age),
            cy=[None if rng.random() < 0.04 else round(rng.uniform(-22, 34), 2)
                for _ in CALENDAR_YEARS],
            mgmt=_fee(rng, round(rng.uniform(0.4, 1.6), 4)),
            trustee_fee=_fee(rng, round(rng.uniform(0.05, 0.3), 4)),
            empf="0.29",
            member=_fee(rng, round(rng.uniform(0, 0.3), 4)) if rng.random() < 0.1 else f"{rng.choice([0, 0.1, 0.2]):g}",
            invest=_fee(rng, round(rng.uniform(0.2, 0.8), 4)),
            guarantee=f"{rng.choice([0, 0, 0, 0.75]):g}",
        ))
    return rows


def _td(text, cls=None, **attrs):
    a = "".join(f' {k.replace("_","-")}="{v}"' for k, v in attrs.items())
    c = f' class="{cls}"' if cls else ""
    return f"<td{c}{a}>{_html.escape(str(text))}</td>"


def render_html(rows: list[dict]) -> str:
    out = ["<html><head><meta charset='utf-8'><title>強積金基金平台</title></head><body>"]

    # 篩選器表格（解析時應被跳過）
    out.append("<table class='txt'><tr><td>基金類別</td><td>股票基金 混合資產基金 債券基金 保證基金</td>"
               "<td>基金種類</td><td>股票基金 - 亞洲 股票基金 - 中國</td></tr>"
               "<tr><td>受託人</td><td>示例受託人甲信託 示例受託人乙信託</td>"
               "<td>最高/最低的十個基金 (按回報 / 開支比率)</td></tr>"
               "<tr><td>計劃</td><td>示例強積金計劃 01 示例強積金計劃 02</td></tr></table>")

    # 頁面自報的總數與截止日期
    out.append(f"<table><tr><td></td><td>已選擇的成分基金總數: {len(rows)} / 風險標記</td>"
               f"<td>最新資料截至{AS_OF_Y}年{AS_OF_M:02d}月{AS_OF_D:02d}日</td><td></td><td></td></tr></table>")

    # 主表
    out.append("<table id='scrolltable' class='txt'>")
    out.append("<tr><td colspan='10'></td><td colspan='6'>回報, 風險, 開支, 基金規模及推出日期</td>"
               "<td colspan='10'>費用及收費</td></tr>")
    main = ["", "計劃", "", "成分基金", "受託人", "基金類別", "推出日期",
            "基金規模 （百萬港元）", "風險級別", "最近期基金 開支比率\n            (%)"]
    hdr = "<tr>" + "".join(f"<td rowspan='2'>{_html.escape(m)}</td>" for m in main)
    hdr += ("<td colspan='13' class='arCol_bak'>年率化回報 (% p.a.) 累積回報 (%) 曆年回報 (%)</td>"
            "<td rowspan='2'>基金管理費 (% p.a.)</td>"
            "<td colspan='4'>基金管理費分項 (% p.a.)</td>"
            "<td rowspan='2'>保證費 (% p.a.)</td>"
            "<td rowspan='2'>詳細內容</td></tr>")
    out.append(hdr)
    sub = (["一年期", "五年期", "十年期", "推出至今"] * 2
           + [str(y) for y in CALENDAR_YEARS]
           + ["受託人費／ 保管人費", "積金易平台費", "成員服務費", "投資管理費"])
    out.append("<tr>" + "".join(f"<td>{_html.escape(s)}</td>" for s in sub) + "</tr>")

    for r in rows:
        c = ["<tr class='wr'>"]
        c.append(_td(""))                                   # 0 勾選框（整表皆空）
        c.append(_td(r["scheme"], "txt"))                   # 1
        c.append(_td(""))                                   # 2 間隔（整表皆空）
        c.append(_td(r["fund"], "table"))                   # 3
        c.append(_td(r["trustee"]))                         # 4
        c.append(_td(r["category"], "table"))               # 5
        c.append(_td(r["launch"], "table mpp_tab_green"))   # 6
        c.append(_td(_na_or(r["size"], thousands=True), "table mpp_tab_green"))  # 7
        c.append(_td("n.a." if r["risk"] is None else r["risk"], "table mpp_tab_green"))  # 8
        c.append(_td("n.a." if r["fer"] is None else f"{r['fer']:.5f}", "table"))          # 9
        for v in (r["a1"], r["a5"], r["a10"], r["asl"]):
            c.append(_td(_na_or(v), "arCol mpp_tab_green"))
        for v in (r["c1"], r["c5"], r["c10"], r["csl"]):
            c.append(_td(_na_or(v), "crCol mpp_tab_green"))
        for v in r["cy"]:
            c.append(_td(_na_or(v), "cyrCol mpp_tab_green"))
        c.append(_td(r["mgmt"], "table mpp_tab_red"))       # 23
        c.append(_td(r["trustee_fee"], "mpp_tab_red"))      # 24
        c.append(_td(r["empf"], "mpp_tab_red"))             # 25
        c.append(_td(r["member"], "mpp_tab_red"))           # 26
        c.append(_td(r["invest"], "mpp_tab_red"))           # 27
        c.append(_td(r["guarantee"], "mpp_tab_red"))        # 28
        c.append(_td(""))                                   # 29 詳細內容（整表皆空）
        c.append("</tr>")
        out.append("".join(c))
    out.append("</table>")

    out.append(f"<table><tr><td>最後更新日期： {AS_OF_D:02d}/{AS_OF_M+1:02d}/{AS_OF_Y}</td></tr></table>")
    out.append("<table><tr><td>註釋</td><td></td></tr></table>")
    out.append("<table><tr><td>「n.a.」表示沒有提供有關資料。</td></tr></table>")
    out.append("</body></html>")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="產生模式 B 的樣例基金資訊表 HTML（合成資料）")
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rows = build_rows(args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "mpp_list_sample.html"
    path.write_text(render_html(rows), encoding="utf-8")

    print(f"已產生樣例基金資訊表：{path}")
    print(f"  {len(rows)} 隻基金 / {N_SCHEMES} 個計劃，資料截至 {AS_OF_Y}-{AS_OF_M:02d}-{AS_OF_D:02d}")
    print(f"  曆年回報年份：{CALENDAR_YEARS}")
    print("\n注意：這是合成資料，僅用於驗證流水線，不可當作真實強積金資料。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
