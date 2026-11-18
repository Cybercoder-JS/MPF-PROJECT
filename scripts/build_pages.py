#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由 data/funds_latest.json 批量生成 docs/funds/ 下的静态页面。

生成内容
--------
* 每只成分基金一页           docs/funds/{计划slug}-{基金slug}.html
* 每个基金类别一张汇总表     docs/funds/category-{slug}.html
* 每个计划一张汇总表         docs/funds/scheme-{slug}.html
* 每个受托人一张汇总表       docs/funds/trustee-{slug}.html
* 全部基金总表（搜索/筛选）  docs/funds/index.html
* 站点地图（覆盖全站）       docs/sitemap.xml
* 共享样式与脚本             docs/funds/assets/{style.css,app.js}

说明
----
* 页面文案一律用简体中文；基金／计划／受托人／类别等**数据原文保持不变**
  （平台原文为繁体，属官方名称，不作转换）。
* 表格排序、搜索、筛选皆为原生 JS；所有数据行同时由本脚本写入 HTML，
  即使停用 JavaScript 也能完整读到内容（利于收录）。
* 页面只做数据整理与展示，不含任何投资建议性措辞。

用法
----
    python scripts/build_pages.py [--base-url https://your-domain.example]

--base-url 用于 <link rel=canonical>、og:url 与 sitemap.xml 的绝对网址。
站点部署在 GitHub Pages 的子路径下（.../MPF-PROJECT/），因此页面之间、
以及对 CSS／JS／JSON 的引用一律使用相对路径，绝不以 / 开头；只有
canonical、og:url 与 sitemap.xml 里才出现绝对网址。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import statistics
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
DATA_JSON = ROOT / "data" / "funds_latest.json"
META_JSON = ROOT / "data" / "metadata.json"
SITE_DIR = ROOT / "docs"          # GitHub Pages 的发布根目录
OUT_DIR = SITE_DIR / "funds"
ASSET_DIR = OUT_DIR / "assets"

DEFAULT_BASE_URL = "https://cybercoder-js.github.io/MPF-PROJECT"
SITE_NAME = "强积金成分基金资料库"
SITE_ROOT_PATH = "/funds/"

# ---------------------------------------------------------------- 字段标签（简体）

LABELS = {
    "scheme_name": "计划",
    "fund_name": "成分基金",
    "trustee": "受托人",
    "fund_category": "基金类别",
    "launch_date": "推出日期",
    "fund_size_hkd_million": "基金规模",
    "risk_level": "风险级别",
    "fer_pct": "基金开支比率（FER）",
    "return_1y_annualised": "一年期年率化回报",
    "return_5y_annualised": "五年期年率化回报",
    "return_10y_annualised": "十年期年率化回报",
    "return_since_launch_annualised": "推出至今年率化回报",
    "return_1y_cumulative": "一年期累积回报",
    "return_5y_cumulative": "五年期累积回报",
    "return_10y_cumulative": "十年期累积回报",
    "return_since_launch_cumulative": "推出至今累积回报",
    "return_cy2025": "2025 历年回报",
    "return_cy2024": "2024 历年回报",
    "return_cy2023": "2023 历年回报",
    "return_cy2022": "2022 历年回报",
    "return_cy2021": "2021 历年回报",
    "management_fee": "基金管理费",
    "trustee_custodian_fee": "受托人费／保管人费",
    "empf_platform_fee": "积金易平台费",
    "member_service_fee": "成员服务费",
    "investment_management_fee": "投资管理费",
    "guarantee_fee": "保证费",
}

FEE_KEYS = [
    "management_fee",
    "trustee_custodian_fee",
    "empf_platform_fee",
    "member_service_fee",
    "investment_management_fee",
    "guarantee_fee",
]

# 基金管理费的分项（平台口径）
FEE_COMPONENT_KEYS = [
    "trustee_custodian_fee",
    "empf_platform_fee",
    "member_service_fee",
    "investment_management_fee",
]

RETURN_PERIODS = [
    ("一年期", "return_1y_annualised", "return_1y_cumulative"),
    ("五年期", "return_5y_annualised", "return_5y_cumulative"),
    ("十年期", "return_10y_annualised", "return_10y_cumulative"),
    ("推出至今", "return_since_launch_annualised", "return_since_launch_cumulative"),
]

CALENDAR_YEARS = [2025, 2024, 2023, 2022, 2021]

# 同类别内参与排名的指标：(字段, 显示名, 低者在前)
RANK_METRICS = [
    ("fer_pct", "基金开支比率（FER）", True),
    ("return_1y_annualised", "一年期年率化回报", False),
    ("return_5y_annualised", "五年期年率化回报", False),
    ("return_10y_annualised", "十年期年率化回报", False),
    ("return_since_launch_annualised", "推出至今年率化回报", False),
]

DISCLAIMER = (
    "本页内容由公开披露的强积金成分基金资料整理而成，仅供一般参考及数据查询之用，"
    "并非投资建议、要约或任何招揽。所有数值以受托人及监管机构的正式披露文件为准；"
    "过往回报数据不代表将来表现，基金价格可升可跌。本站不就资料的准确性、完整性"
    "或及时性作出任何保证，亦不承担因使用本页资料而产生的任何责任。"
)

RISK_NOTE = (
    "风险级别为 1 至 7 的整数，数字越大代表该基金过往的价格波动幅度越大，"
    "属对历史波动程度的描述。"
)

RANK_NOTE = (
    "排名只是同一基金类别内、同一指标的数值排序，用于横向对照数据；"
    "名次高低不代表任何优劣评价。空值不参与排名。"
)

# ---------------------------------------------------------------- 工具函数


def e(value) -> str:
    """HTML 转义。"""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def slugify(text: str) -> str:
    """生成保留中日韩字符、其余转连字符的 slug。

    平台原文为中文，保留汉字可得到稳定、可读且可逆的网址；
    百分号等有语义的符号先转为可读写法再处理。
    """
    s = unicodedata.normalize("NFKC", str(text)).strip().lower()
    s = s.replace("%", "pct").replace("&", "and").replace("+", "plus")
    s = "".join(ch if ch.isalnum() else "-" for ch in s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"


def fmt_num(value, dp: int = 2, suffix: str = "") -> str:
    if value is None:
        return '<span class="na" title="平台未提供数据">—</span>'
    return f"{value:,.{dp}f}{suffix}"


def fmt_pct(value, dp: int = 2) -> str:
    return fmt_num(value, dp, "%")


def fmt_signed_pct(value, dp: int = 2) -> str:
    """带正负号与涨跌配色的百分比。"""
    if value is None:
        return '<span class="na" title="平台未提供数据">—</span>'
    cls = "pos" if value > 0 else ("neg" if value < 0 else "flat")
    return f'<span class="{cls}">{value:+,.{dp}f}%</span>'


def data_v(value) -> str:
    """排序用的 data-v 属性；空值留空，排序时一律置后。"""
    if value is None:
        return ' data-v=""'
    if isinstance(value, (int, float)):
        return f' data-v="{value}"'
    return f' data-v="{e(value)}"'


def plain(value, dp: int = 2, suffix: str = "") -> str:
    """供 meta description 使用的纯文本数值。"""
    if value is None:
        return "暂无数据"
    return f"{value:,.{dp}f}{suffix}"


def to_yi(value_in_million):
    """百万港元 -> 亿港元。"""
    if value_in_million is None:
        return None
    return value_in_million / 100.0


# ---------------------------------------------------------------- 载入与派生


def load() -> tuple[list[dict], dict]:
    funds = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    meta = json.loads(META_JSON.read_text(encoding="utf-8"))
    return funds, meta


def build_index(funds: list[dict]) -> dict:
    """为每只基金补上 slug、网址与同类别排名。"""
    used: dict[str, dict] = {}
    for f in funds:
        base = f"{slugify(f['scheme_name'])}-{slugify(f['fund_name'])}"
        name = base
        n = 2
        while name in used:
            name = f"{base}-{n}"
            n += 1
        used[name] = f
        f["_slug"] = name
        f["_href"] = f"{name}.html"

    groups: dict[str, list[dict]] = {}
    for f in funds:
        groups.setdefault(f["fund_category"], []).append(f)

    for cat, rows in groups.items():
        for field, _label, lower_first in RANK_METRICS:
            valued = [r for r in rows if r.get(field) is not None]
            valued.sort(key=lambda r: r[field], reverse=not lower_first)
            total = len(valued)
            for i, r in enumerate(valued, start=1):
                r.setdefault("_ranks", {})[field] = (i, total)
            med = statistics.median([r[field] for r in valued]) if valued else None
            for r in rows:
                r.setdefault("_medians", {})[field] = med
        for r in rows:
            r["_category_size"] = len(rows)
    return groups


# ---------------------------------------------------------------- 页面骨架


class Builder:
    def __init__(self, base_url: str, funds: list[dict], meta: dict):
        self.base = base_url.rstrip("/")
        self.funds = funds
        self.meta = meta
        self.as_of = meta.get("data_as_of_date", "")
        self.page_updated = meta.get("page_last_updated") or self.as_of
        self.pages: list[tuple[str, str, float]] = []  # (filename, lastmod, priority)

    # -- 网址

    def abs_url(self, filename: str) -> str:
        """把 funds/ 目录内的相对链接换成绝对网址。

        以 ``../`` 开头的链接指向站点根（即 docs/），例如 ``../index.html``
        与 ``../guides/``；其余一律视为 funds/ 目录内的文件名。
        """
        if filename.startswith("../"):
            return self.site_url(filename[3:])
        return f"{self.base}{SITE_ROOT_PATH}{quote(filename)}"

    def site_url(self, path: str) -> str:
        """站点根（docs/）下某个路径的绝对网址。"""
        return f"{self.base}/{quote(path.lstrip('/'))}"

    # -- 公共片段

    def head(
        self,
        *,
        title: str,
        description: str,
        filename: str,
        jsonld: list[dict],
        extra_head: str = "",
    ) -> str:
        url = self.abs_url(filename)
        ld = json.dumps(
            {"@context": "https://schema.org", "@graph": jsonld},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return f"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
<link rel="canonical" href="{e(url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(SITE_NAME)}">
<meta property="og:locale" content="zh_HK">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{e(url)}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(description)}">
<link rel="stylesheet" href="assets/style.css">
{extra_head}<script type="application/ld+json">{ld}</script>
</head>
<body>
<a class="skip" href="#main">跳至主要内容</a>
"""

    def breadcrumb_html(self, trail: list[tuple[str, str | None]]) -> str:
        items = []
        for label, href in trail:
            if href:
                items.append(f'<li><a href="{e(href)}">{e(label)}</a></li>')
            else:
                items.append(f'<li><span aria-current="page">{e(label)}</span></li>')
        return (
            '<nav class="crumbs" aria-label="面包屑导航">\n<ol>\n'
            + "\n".join(items)
            + "\n</ol>\n</nav>\n"
        )

    def breadcrumb_ld(self, trail: list[tuple[str, str | None]], filename: str) -> dict:
        elements = []
        for i, (label, href) in enumerate(trail, start=1):
            target = self.abs_url(href) if href else self.abs_url(filename)
            elements.append(
                {"@type": "ListItem", "position": i, "name": label, "item": target}
            )
        return {"@type": "BreadcrumbList", "itemListElement": elements}

    def footer(self) -> str:
        return f"""</main>
<footer class="site-foot">
<h2 class="foot-h">数据说明与免责声明</h2>
<dl class="foot-meta">
<dt>数据截止日期</dt><dd><time datetime="{e(self.as_of)}">{e(self.as_of)}</time></dd>
<dt>来源页最后更新</dt><dd><time datetime="{e(self.page_updated)}">{e(self.page_updated)}</time></dd>
<dt>收录基金数目</dt><dd>{len(self.funds)} 只成分基金</dd>
<dt>本页生成时间</dt><dd><time datetime="{e(self.generated_at)}">{e(self.generated_at[:10])}</time></dd>
</dl>
<p class="disclaimer"><strong>免责声明：</strong>{e(DISCLAIMER)}</p>
<p class="foot-nav"><a href="../index.html">返回首页</a> · <a href="index.html">全部基金总表</a> · <a href="../fee-calculator.html">费用计算器</a> · <a href="../guides/index.html">强积金科普指南</a></p>
</footer>
<script src="assets/app.js" defer></script>
</body>
</html>
"""

    @property
    def generated_at(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def write(self, filename: str, content: str, priority: float = 0.5) -> None:
        (OUT_DIR / filename).write_text(content, encoding="utf-8")
        self.pages.append((filename, self.page_updated, priority))

    # -- 表格

    TABLE_COLUMNS = [
        ("fund", "成分基金", "str"),
        ("scheme", "计划", "str"),
        ("trustee", "受托人", "str"),
        ("category", "基金类别", "str"),
        ("risk", "风险级别", "num"),
        ("fer", "FER（%）", "num"),
        ("r1y", "一年年率化（%）", "num"),
        ("r5y", "五年年率化（%）", "num"),
        ("r10y", "十年年率化（%）", "num"),
        ("rsl", "推出至今年率化（%）", "num"),
        ("size", "基金规模（百万港元）", "num"),
    ]

    def table(
        self,
        rows: list[dict],
        *,
        table_id: str = "fund-table",
        hide: tuple[str, ...] = (),
        caption: str = "",
    ) -> str:
        cols = [c for c in self.TABLE_COLUMNS if c[0] not in hide]
        head_cells = []
        for key, label, typ in cols:
            head_cells.append(
                f'<th scope="col" data-type="{typ}" data-col="{key}" aria-sort="none">'
                f'<button type="button" class="sort-btn">{e(label)}'
                f'<span class="arrow" aria-hidden="true"></span></button></th>'
            )
        body = []
        for f in rows:
            search_blob = " ".join(
                [f["fund_name"], f["scheme_name"], f["trustee"], f["fund_category"]]
            ).lower()
            attrs = (
                f' data-search="{e(search_blob)}"'
                f' data-trustee="{e(f["trustee"])}"'
                f' data-scheme="{e(f["scheme_name"])}"'
                f' data-category="{e(f["fund_category"])}"'
                f' data-risk="{e(f["risk_level"]) if f["risk_level"] is not None else ""}"'
                f' data-fer="{e(f["fer_pct"]) if f["fer_pct"] is not None else ""}"'
            )
            cells = {
                "fund": f'<th scope="row"{data_v(f["fund_name"])}>'
                f'<a href="{e(f["_href"])}">{e(f["fund_name"])}</a></th>',
                "scheme": f'<td{data_v(f["scheme_name"])}>{e(f["scheme_name"])}</td>',
                "trustee": f'<td{data_v(f["trustee"])}>{e(f["trustee"])}</td>',
                "category": f'<td class="cat"{data_v(f["fund_category"])}>{e(f["fund_category"])}</td>',
                "risk": f'<td class="num"{data_v(f["risk_level"])}>'
                f'{fmt_num(f["risk_level"], 0)}</td>',
                "fer": f'<td class="num"{data_v(f["fer_pct"])}>{fmt_num(f["fer_pct"], 2)}</td>',
                "r1y": f'<td class="num"{data_v(f["return_1y_annualised"])}>'
                f'{fmt_signed_pct(f["return_1y_annualised"])}</td>',
                "r5y": f'<td class="num"{data_v(f["return_5y_annualised"])}>'
                f'{fmt_signed_pct(f["return_5y_annualised"])}</td>',
                "r10y": f'<td class="num"{data_v(f["return_10y_annualised"])}>'
                f'{fmt_signed_pct(f["return_10y_annualised"])}</td>',
                "rsl": f'<td class="num"{data_v(f["return_since_launch_annualised"])}>'
                f'{fmt_signed_pct(f["return_since_launch_annualised"])}</td>',
                "size": f'<td class="num"{data_v(f["fund_size_hkd_million"])}>'
                f'{fmt_num(f["fund_size_hkd_million"], 2)}</td>',
            }
            body.append(
                f"<tr{attrs}>" + "".join(cells[k] for k, _l, _t in cols) + "</tr>"
            )
        cap = f"<caption>{e(caption)}</caption>\n" if caption else ""
        return f"""<div class="table-wrap">
<table id="{e(table_id)}" class="data-table" data-sortable="1">
{cap}<thead><tr>
{chr(10).join(head_cells)}
</tr></thead>
<tbody>
{chr(10).join(body)}
</tbody>
</table>
</div>
<p class="table-hint">点击表头可按该列排序（再点一次切换升降序）。空值一律排在最后。</p>
"""

    def item_list_ld(self, rows: list[dict], name: str) -> dict:
        return {
            "@type": "ItemList",
            "name": name,
            "numberOfItems": len(rows),
            "itemListOrder": "https://schema.org/ItemListUnordered",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i,
                    "name": f["fund_name"],
                    "url": self.abs_url(f["_href"]),
                }
                for i, f in enumerate(rows, start=1)
            ],
        }

    # ------------------------------------------------------------ 基金详情页

    def fund_page(self, f: dict, groups: dict[str, list[dict]]) -> None:
        name = f["fund_name"]
        scheme = f["scheme_name"]
        trustee = f["trustee"]
        cat = f["fund_category"]
        filename = f["_href"]

        title = f"{name}（{scheme}）基金开支比率、回报与费用明细｜{SITE_NAME}"
        fer_rank = f.get("_ranks", {}).get("fer_pct")
        rank_txt = (
            f"同类别 {fer_rank[1]} 只基金中开支比率排第 {fer_rank[0]} 低"
            if fer_rank
            else "同类别开支比率排名暂无数据"
        )
        description = (
            f"{name}（{scheme}，受托人：{trustee}）属{cat}。"
            f"基金开支比率 {plain(f['fer_pct'], 2, '%')}，"
            f"一年期年率化回报 {plain(f['return_1y_annualised'], 2, '%')}，"
            f"基金规模 {plain(f['fund_size_hkd_million'], 2)} 百万港元，"
            f"风险级别 {plain(f['risk_level'], 0)}；{rank_txt}。"
            f"数据截止 {self.as_of}。"
        )

        trail = [
            ("首页", "../index.html"),
            ("全部基金", "index.html"),
            (trustee, f"trustee-{slugify(trustee)}.html"),
            (scheme, f"scheme-{slugify(scheme)}.html"),
            (name, None),
        ]

        fee_rows = []
        for key in FEE_KEYS:
            raw = f.get(f"{key}_raw")
            pct = f.get(f"{key}_pct")
            note = ""
            if raw and "最高" in str(raw):
                note = "原文为上限值"
            elif raw and "-" in str(raw):
                note = "原文为区间，数值取上限"
            fee_rows.append(
                f"<tr><th scope=\"row\">{e(LABELS[key])}</th>"
                f"<td>{e(raw) if raw not in (None, '') else fmt_num(None)}</td>"
                f'<td class="num">{fmt_num(pct, 4, "%")}</td>'
                f"<td>{e(note)}</td></tr>"
            )

        ret_rows = []
        for label, ann, cum in RETURN_PERIODS:
            ret_rows.append(
                f'<tr><th scope="row">{e(label)}</th>'
                f'<td class="num">{fmt_signed_pct(f[ann])}</td>'
                f'<td class="num">{fmt_signed_pct(f[cum])}</td></tr>'
            )

        cy_head = "".join(f'<th scope="col">{y}</th>' for y in CALENDAR_YEARS)
        cy_body = "".join(
            f'<td class="num">{fmt_signed_pct(f[f"return_cy{y}"])}</td>'
            for y in CALENDAR_YEARS
        )

        rank_rows = []
        for field, label, lower_first in RANK_METRICS:
            r = f.get("_ranks", {}).get(field)
            med = f.get("_medians", {}).get(field)
            order = "由低至高" if lower_first else "由高至低"
            rank_cell = f"第 {r[0]} / {r[1]}" if r else fmt_num(None)
            dp = 4 if field == "fer_pct" else 2
            rank_rows.append(
                f'<tr><th scope="row">{e(label)}</th>'
                f'<td class="num">{fmt_num(f.get(field), dp, "%")}</td>'
                f'<td class="num">{rank_cell}</td>'
                f'<td class="num">{fmt_num(med, dp, "%")}</td>'
                f"<td>{e(order)}</td></tr>"
            )

        peers = [p for p in groups[cat] if p["_slug"] != f["_slug"]]
        peers_sorted = sorted(
            peers, key=lambda p: (p["fer_pct"] is None, p["fer_pct"] or 0)
        )
        peer_links = "".join(
            f'<li><a href="{e(p["_href"])}">{e(p["fund_name"])}'
            f'<span class="meta">{e(p["scheme_name"])}</span></a></li>'
            for p in peers_sorted
        )

        same_scheme = [
            p
            for p in self.funds
            if p["scheme_name"] == scheme and p["_slug"] != f["_slug"]
        ]
        scheme_links = "".join(
            f'<li><a href="{e(p["_href"])}">{e(p["fund_name"])}'
            f'<span class="meta">{e(p["fund_category"])}</span></a></li>'
            for p in sorted(same_scheme, key=lambda p: p["fund_name"])
        )

        size_yi = to_yi(f["fund_size_hkd_million"])
        size_extra = f"（约 {size_yi:,.2f} 亿港元）" if size_yi is not None else ""

        fee_spec_bits = []
        if f["fer_pct"] is not None:
            fee_spec_bits.append(f"基金开支比率（FER）{plain(f['fer_pct'], 4, '%')}")
        if f.get("management_fee_raw"):
            fee_spec_bits.append(f"基金管理费原文：{f['management_fee_raw']}")

        # 结构化数据只收录有值的字段：null 对消费端没有意义，且会被当成脏数据。
        props = [
            {
                "@type": "PropertyValue",
                "name": LABELS["fer_pct"],
                "value": f["fer_pct"],
                "unitText": "PERCENT",
            },
            {
                "@type": "PropertyValue",
                "name": LABELS["risk_level"],
                "value": f["risk_level"],
                "minValue": 1,
                "maxValue": 7,
            },
            {
                "@type": "PropertyValue",
                "name": LABELS["fund_size_hkd_million"],
                "value": f["fund_size_hkd_million"],
                "unitText": "HKD million",
            },
            {
                "@type": "PropertyValue",
                "name": LABELS["launch_date"],
                "value": f["launch_date"],
            },
        ] + [
            {
                "@type": "PropertyValue",
                "name": LABELS[k],
                "value": f[k],
                "unitText": "PERCENT",
            }
            for k in (
                "return_1y_annualised",
                "return_5y_annualised",
                "return_10y_annualised",
                "return_since_launch_annualised",
            )
        ]
        props = [pv for pv in props if pv.get("value") is not None]

        fund_ld = {
            "@type": ["InvestmentFund", "FinancialProduct"],
            "@id": self.abs_url(filename) + "#fund",
            "name": name,
            "url": self.abs_url(filename),
            "category": cat,
            "inLanguage": "zh-Hant",
            "provider": {"@type": "Organization", "name": trustee},
            "isRelatedTo": {"@type": "Product", "name": scheme},
            "additionalProperty": props,
        }
        if fee_spec_bits:
            fund_ld["feesAndCommissionsSpecification"] = "；".join(fee_spec_bits)
        page_ld = {
            "@type": "WebPage",
            "@id": self.abs_url(filename),
            "name": title,
            "description": description,
            "inLanguage": "zh-Hans",
            "datePublished": self.as_of,
            "dateModified": self.page_updated,
            "mainEntity": {"@id": self.abs_url(filename) + "#fund"},
            "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": self.abs_url("index.html")},
        }

        html_out = self.head(
            title=title,
            description=description,
            filename=filename,
            jsonld=[self.breadcrumb_ld(trail, filename), page_ld, fund_ld],
        )
        html_out += self.breadcrumb_html(trail)
        html_out += f"""<main id="main">
<header class="page-head">
<h1>{e(name)}</h1>
<p class="lede">{e(scheme)}　·　受托人：{e(trustee)}　·　{e(cat)}</p>
</header>

<section class="cards" aria-label="关键数据">
<div class="card"><span class="k">{e(LABELS["fer_pct"])}</span><span class="v">{fmt_num(f["fer_pct"], 4, "%")}</span></div>
<div class="card"><span class="k">{e(LABELS["return_1y_annualised"])}</span><span class="v">{fmt_signed_pct(f["return_1y_annualised"])}</span></div>
<div class="card"><span class="k">{e(LABELS["fund_size_hkd_million"])}</span><span class="v">{fmt_num(f["fund_size_hkd_million"], 2)}<small> 百万港元</small></span></div>
<div class="card"><span class="k">{e(LABELS["risk_level"])}</span><span class="v">{fmt_num(f["risk_level"], 0)}<small> / 7</small></span></div>
<div class="card"><span class="k">{e(LABELS["launch_date"])}</span><span class="v"><time datetime="{e(f["launch_date"])}">{e(f["launch_date"])}</time></span></div>
</section>

<section id="basic">
<h2>基本资料</h2>
<table class="kv">
<tbody>
<tr><th scope="row">{e(LABELS["fund_name"])}</th><td>{e(name)}</td></tr>
<tr><th scope="row">{e(LABELS["scheme_name"])}</th><td><a href="scheme-{e(slugify(scheme))}.html">{e(scheme)}</a></td></tr>
<tr><th scope="row">{e(LABELS["trustee"])}</th><td><a href="trustee-{e(slugify(trustee))}.html">{e(trustee)}</a></td></tr>
<tr><th scope="row">{e(LABELS["fund_category"])}</th><td><a href="category-{e(slugify(cat))}.html">{e(cat)}</a></td></tr>
<tr><th scope="row">{e(LABELS["launch_date"])}</th><td><time datetime="{e(f["launch_date"])}">{e(f["launch_date"])}</time></td></tr>
<tr><th scope="row">{e(LABELS["fund_size_hkd_million"])}</th><td>{fmt_num(f["fund_size_hkd_million"], 2)} 百万港元{e(size_extra)}</td></tr>
<tr><th scope="row">{e(LABELS["risk_level"])}</th><td>{fmt_num(f["risk_level"], 0)} / 7<span class="note">{e(RISK_NOTE)}</span></td></tr>
</tbody>
</table>
</section>

<section id="returns">
<h2>回报数据</h2>
<h3>年率化回报与累积回报</h3>
<table class="kv">
<thead><tr><th scope="col">期间</th><th scope="col">年率化回报（% p.a.）</th><th scope="col">累积回报（%）</th></tr></thead>
<tbody>
{chr(10).join(ret_rows)}
</tbody>
</table>
<h3>历年回报</h3>
<div class="table-wrap">
<table class="kv">
<thead><tr><th scope="col">年度</th>{cy_head}</tr></thead>
<tbody><tr><th scope="row">回报（%）</th>{cy_body}</tr></tbody>
</table>
</div>
<p class="note">过往回报数据不代表将来表现。</p>
</section>

<section id="fees">
<h2>费用与开支</h2>
<p>{e(LABELS["fer_pct"])}：<strong>{fmt_num(f["fer_pct"], 4, "%")}</strong>。基金开支比率为基金于过往一个财政期间的总开支占基金资产净值的比率。</p>
<h3>费用明细</h3>
<div class="table-wrap">
<table class="kv">
<thead><tr><th scope="col">费用项目</th><th scope="col">平台原文</th><th scope="col">解析数值（% p.a.）</th><th scope="col">备注</th></tr></thead>
<tbody>
{chr(10).join(fee_rows)}
</tbody>
</table>
</div>
<p class="note">{e("其中「" + "」、「".join(LABELS[k] for k in FEE_COMPONENT_KEYS) + "」为基金管理费的分项。原文若为区间或「最高」写法，解析数值一律取上限。")}</p>
</section>

<section id="ranking">
<h2>同类别内的数值排名</h2>
<p>以下排名在基金类别「{e(cat)}」的 {f["_category_size"]} 只成分基金范围内计算。</p>
<div class="table-wrap">
<table class="kv">
<thead><tr><th scope="col">指标</th><th scope="col">本基金数值</th><th scope="col">类别内排名</th><th scope="col">类别中位数</th><th scope="col">排序方向</th></tr></thead>
<tbody>
{chr(10).join(rank_rows)}
</tbody>
</table>
</div>
<p class="note">{e(RANK_NOTE)}</p>
</section>

<section id="peers">
<h2>同基金类别的其他基金</h2>
<p>「{e(cat)}」类别下的其他 {len(peers_sorted)} 只基金（按基金开支比率由低至高排列）：</p>
<ul class="link-list">
{peer_links or '<li class="na">此类别内没有其他基金。</li>'}
</ul>
</section>

<section id="same-scheme">
<h2>同一计划的其他基金</h2>
<p>「{e(scheme)}」旗下的其他 {len(same_scheme)} 只成分基金：</p>
<ul class="link-list">
{scheme_links or '<li class="na">此计划没有其他基金。</li>'}
</ul>
</section>

<section id="related">
<h2>相关汇总页</h2>
<ul class="link-list">
<li><a href="category-{e(slugify(cat))}.html">{e(cat)} — 类别汇总表</a></li>
<li><a href="scheme-{e(slugify(scheme))}.html">{e(scheme)} — 计划汇总表</a></li>
<li><a href="trustee-{e(slugify(trustee))}.html">{e(trustee)} — 受托人汇总表</a></li>
<li><a href="index.html">全部 {len(self.funds)} 只成分基金总表</a></li>
</ul>
</section>
"""
        html_out += self.footer()
        self.write(filename, html_out, priority=0.8)

    # ------------------------------------------------------------ 汇总页

    def group_page(
        self,
        *,
        kind: str,
        key_label: str,
        value: str,
        rows: list[dict],
        filename: str,
        extra_intro: str = "",
        show_filters: bool = False,
        hide_cols: tuple[str, ...] = (),
    ) -> None:
        rows_sorted = sorted(
            rows, key=lambda r: (r["fer_pct"] is None, r["fer_pct"] or 0)
        )
        fers = [r["fer_pct"] for r in rows if r["fer_pct"] is not None]
        r1 = [r["return_1y_annualised"] for r in rows if r["return_1y_annualised"] is not None]
        sizes = [r["fund_size_hkd_million"] for r in rows if r["fund_size_hkd_million"] is not None]
        schemes = sorted({r["scheme_name"] for r in rows})
        trustees = sorted({r["trustee"] for r in rows})
        cats = sorted({r["fund_category"] for r in rows})

        title = f"{value}：{len(rows)} 只成分基金的费用与回报对照表｜{SITE_NAME}"
        description = (
            f"{key_label}「{value}」共收录 {len(rows)} 只强积金成分基金。"
            f"基金开支比率介于 {plain(min(fers) if fers else None, 2, '%')} 至 "
            f"{plain(max(fers) if fers else None, 2, '%')}，"
            f"中位数 {plain(statistics.median(fers) if fers else None, 2, '%')}；"
            f"一年期年率化回报中位数 {plain(statistics.median(r1) if r1 else None, 2, '%')}。"
            f"表格可按列排序，数据截止 {self.as_of}。"
        )

        trail = [("首页", "../index.html"), ("全部基金", "index.html"), (value, None)]

        stat_cards = f"""<section class="cards" aria-label="汇总统计">
<div class="card"><span class="k">收录基金</span><span class="v">{len(rows)}<small> 只</small></span></div>
<div class="card"><span class="k">FER 中位数</span><span class="v">{fmt_num(statistics.median(fers) if fers else None, 3, "%")}</span></div>
<div class="card"><span class="k">FER 范围</span><span class="v">{fmt_num(min(fers) if fers else None, 2, "%")} – {fmt_num(max(fers) if fers else None, 2, "%")}</span></div>
<div class="card"><span class="k">一年年率化回报中位数</span><span class="v">{fmt_signed_pct(statistics.median(r1) if r1 else None)}</span></div>
<div class="card"><span class="k">合计基金规模</span><span class="v">{fmt_num(sum(sizes) if sizes else None, 0)}<small> 百万港元</small></span></div>
</section>"""

        comp_bits = []
        if len(cats) > 1 or kind != "category":
            comp_bits.append(
                "<h3>涵盖基金类别</h3><ul class=\"link-list inline\">"
                + "".join(
                    f'<li><a href="category-{e(slugify(c))}.html">{e(c)}</a></li>'
                    for c in cats
                )
                + "</ul>"
            )
        if kind != "scheme":
            comp_bits.append(
                "<h3>涵盖计划</h3><ul class=\"link-list inline\">"
                + "".join(
                    f'<li><a href="scheme-{e(slugify(s))}.html">{e(s)}</a></li>'
                    for s in schemes
                )
                + "</ul>"
            )
        if kind != "trustee" and len(trustees) > 1:
            comp_bits.append(
                "<h3>涵盖受托人</h3><ul class=\"link-list inline\">"
                + "".join(
                    f'<li><a href="trustee-{e(slugify(t))}.html">{e(t)}</a></li>'
                    for t in trustees
                )
                + "</ul>"
            )
        elif kind != "trustee":
            comp_bits.append(
                "<h3>受托人</h3><ul class=\"link-list inline\">"
                + "".join(
                    f'<li><a href="trustee-{e(slugify(t))}.html">{e(t)}</a></li>'
                    for t in trustees
                )
                + "</ul>"
            )

        page_ld = {
            "@type": "CollectionPage",
            "@id": self.abs_url(filename),
            "name": title,
            "description": description,
            "inLanguage": "zh-Hans",
            "dateModified": self.page_updated,
            "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": self.abs_url("index.html")},
        }

        html_out = self.head(
            title=title,
            description=description,
            filename=filename,
            jsonld=[
                self.breadcrumb_ld(trail, filename),
                page_ld,
                self.item_list_ld(rows_sorted, f"{value} 的成分基金"),
            ],
        )
        html_out += self.breadcrumb_html(trail)
        html_out += f"""<main id="main">
<header class="page-head">
<h1>{e(value)}</h1>
<p class="lede">{e(key_label)}汇总　·　{len(rows)} 只成分基金　·　数据截止 {e(self.as_of)}</p>
{extra_intro}</header>

{stat_cards}

<section id="table">
<h2>成分基金对照表</h2>
{self.filter_bar(rows) if show_filters else ""}
{self.table(rows_sorted, hide=hide_cols, caption=f"{value}：成分基金费用与回报对照")}
</section>

<section id="composition">
<h2>构成与相关页面</h2>
{"".join(comp_bits)}
<p class="foot-nav"><a href="index.html">返回全部 {len(self.funds)} 只成分基金总表</a></p>
</section>
"""
        html_out += self.footer()
        self.write(filename, html_out, priority=0.7)

    def filter_bar(self, rows: list[dict]) -> str:
        def options(values):
            return "".join(f'<option value="{e(v)}">{e(v)}</option>' for v in values)

        specs = [
            ("f-trustee", "trustee", "受托人", sorted({r["trustee"] for r in rows})),
            ("f-scheme", "scheme", "计划", sorted({r["scheme_name"] for r in rows})),
            ("f-category", "category", "基金类别", sorted({r["fund_category"] for r in rows})),
            (
                "f-risk",
                "risk",
                "风险级别",
                [
                    str(v)
                    for v in sorted(
                        {r["risk_level"] for r in rows if r["risk_level"] is not None}
                    )
                ],
            ),
        ]
        # 只剩单一取值的维度（例如计划汇总页上的「计划」）没有筛选意义，略去。
        selects = "".join(
            f'<div class="f-item"><label for="{sid}">{e(label)}</label>\n'
            f'<select id="{sid}" data-filter-key="{key}"><option value="">全部</option>'
            f"{options(values)}</select></div>\n"
            for sid, key, label, values in specs
            if len(values) > 1
        )
        return f"""<form class="filters" id="filters" role="search" aria-label="基金搜索与筛选" onsubmit="return false;">
<div class="f-row">
<label class="f-grow" for="f-q">搜索基金、计划或受托人名称</label>
<input type="search" id="f-q" name="q" placeholder="输入关键字，例如：環球股票、滙豐" autocomplete="off">
</div>
<div class="f-row">
{selects}<div class="f-item"><label for="f-fer-max">FER 上限（%）</label>
<input type="number" id="f-fer-max" step="0.01" min="0" placeholder="例如 1.00"></div>
<div class="f-item f-actions"><button type="button" id="f-reset">清除筛选</button></div>
</div>
<p class="f-status" id="f-status" role="status" aria-live="polite">显示 {len(rows)} / {len(rows)} 只基金</p>
<noscript><p class="note">浏览器未启用 JavaScript：搜索、筛选与排序不可用，但下方表格仍列出全部基金数据。</p></noscript>
</form>"""

    # ------------------------------------------------------------ 总表页

    def index_page(
        self,
        groups: dict[str, list[dict]],
        schemes: dict[str, list[dict]],
        trustees: dict[str, list[dict]],
    ) -> None:
        filename = "index.html"
        rows = sorted(
            self.funds, key=lambda r: (r["fer_pct"] is None, r["fer_pct"] or 0)
        )
        fers = [r["fer_pct"] for r in self.funds if r["fer_pct"] is not None]
        title = (
            f"强积金成分基金总表：{len(self.funds)} 只基金的开支比率与回报对照"
            f"（数据截止 {self.as_of}）｜{SITE_NAME}"
        )
        description = (
            f"收录 {len(self.funds)} 只强积金成分基金，涵盖 {len(trustees)} 家受托人、"
            f"{len(schemes)} 个计划与 {len(groups)} 个基金类别。"
            f"可按基金开支比率、年率化回报、风险级别与基金规模排序及筛选；"
            f"FER 中位数 {plain(statistics.median(fers) if fers else None, 2, '%')}。"
            f"数据截止 {self.as_of}。"
        )
        trail = [("首页", "../index.html"), ("全部基金", None)]

        def group_nav(mapping: dict[str, list[dict]], prefix: str, heading: str, hid: str) -> str:
            items = "".join(
                f'<li><a href="{prefix}-{e(slugify(k))}.html">{e(k)}'
                f'<span class="meta">{len(v)} 只</span></a></li>'
                for k, v in sorted(mapping.items(), key=lambda kv: -len(kv[1]))
            )
            return f'<section id="{hid}">\n<h2>{e(heading)}</h2>\n<ul class="link-list grid">\n{items}\n</ul>\n</section>\n'

        dataset_ld = {
            "@type": "Dataset",
            "@id": self.abs_url(filename) + "#dataset",
            "name": f"强积金成分基金费用与回报数据（截止 {self.as_of}）",
            "description": description,
            "inLanguage": "zh-Hans",
            "temporalCoverage": f"../{self.as_of}",
            "dateModified": self.page_updated,
            "spatialCoverage": {"@type": "Place", "name": "中国香港特别行政区"},
            "variableMeasured": [
                {"@type": "PropertyValue", "name": LABELS["fer_pct"], "unitText": "PERCENT"},
                {"@type": "PropertyValue", "name": LABELS["return_1y_annualised"], "unitText": "PERCENT"},
                {"@type": "PropertyValue", "name": LABELS["return_5y_annualised"], "unitText": "PERCENT"},
                {"@type": "PropertyValue", "name": LABELS["return_10y_annualised"], "unitText": "PERCENT"},
                {"@type": "PropertyValue", "name": LABELS["fund_size_hkd_million"], "unitText": "HKD million"},
                {"@type": "PropertyValue", "name": LABELS["risk_level"]},
            ],
        }
        page_ld = {
            "@type": "CollectionPage",
            "@id": self.abs_url(filename),
            "name": title,
            "description": description,
            "inLanguage": "zh-Hans",
            "dateModified": self.page_updated,
            "mainEntity": {"@id": self.abs_url(filename) + "#dataset"},
        }
        site_ld = {
            "@type": "WebSite",
            "name": SITE_NAME,
            "url": self.abs_url(filename),
            "inLanguage": "zh-Hans",
        }

        html_out = self.head(
            title=title,
            description=description,
            filename=filename,
            jsonld=[self.breadcrumb_ld(trail, filename), site_ld, page_ld, dataset_ld],
        )
        html_out += self.breadcrumb_html(trail)
        html_out += f"""<main id="main">
<header class="page-head">
<h1>强积金成分基金总表</h1>
<p class="lede">{len(self.funds)} 只成分基金　·　{len(trustees)} 家受托人　·　{len(schemes)} 个计划　·　{len(groups)} 个基金类别　·　数据截止 {e(self.as_of)}</p>
</header>

<section class="cards" aria-label="总体统计">
<div class="card"><span class="k">成分基金</span><span class="v">{len(self.funds)}<small> 只</small></span></div>
<div class="card"><span class="k">FER 中位数</span><span class="v">{fmt_num(statistics.median(fers) if fers else None, 3, "%")}</span></div>
<div class="card"><span class="k">FER 最低</span><span class="v">{fmt_num(min(fers) if fers else None, 3, "%")}</span></div>
<div class="card"><span class="k">FER 最高</span><span class="v">{fmt_num(max(fers) if fers else None, 3, "%")}</span></div>
<div class="card"><span class="k">合计基金规模</span><span class="v">{fmt_num(sum(r["fund_size_hkd_million"] for r in self.funds if r["fund_size_hkd_million"] is not None), 0)}<small> 百万港元</small></span></div>
</section>

<section id="table">
<h2>搜索、筛选与排序</h2>
{self.filter_bar(self.funds)}
{self.table(rows, caption="全部强积金成分基金：费用与回报对照")}
</section>

{group_nav(groups, "category", "按基金类别浏览", "by-category")}
{group_nav(schemes, "scheme", "按计划浏览", "by-scheme")}
{group_nav(trustees, "trustee", "按受托人浏览", "by-trustee")}

<section id="howto">
<h2>字段说明</h2>
<dl class="kv-dl">
<dt>{e(LABELS["fer_pct"])}</dt><dd>基金于过往一个财政期间的总开支占基金资产净值的百分比。</dd>
<dt>年率化回报</dt><dd>相应期间内换算成每年的平均回报（% p.a.）。</dd>
<dt>累积回报</dt><dd>相应期间内的累计回报（%），未年率化。</dd>
<dt>历年回报</dt><dd>各个日历年度（1 月至 12 月）的回报（%）。</dd>
<dt>{e(LABELS["risk_level"])}</dt><dd>{e(RISK_NOTE)}</dd>
<dt>{e(LABELS["fund_size_hkd_million"])}</dt><dd>基金资产净值，单位为百万港元。</dd>
<dt>空值</dt><dd>平台标示为 n.a. 的数据一律保留为空值（显示为「—」），不会当作 0 处理。</dd>
</dl>
</section>
"""
        html_out += self.footer()
        self.write(filename, html_out, priority=1.0)

    # ------------------------------------------------------------ sitemap

    def site_pages(self) -> list[tuple[str, float]]:
        """funds/ 以外、同样要进 sitemap 的站点页面（相对 docs/ 的路径）。

        首页与费用计算器写死；docs/guides/ 下的页面按文件扫描，
        新增科普页后无须改动本脚本。
        """
        out: list[tuple[str, float]] = []
        for name, prio in (("index.html", 1.0), ("fee-calculator.html", 0.9)):
            if (SITE_DIR / name).exists():
                out.append((name, prio))
        guides = SITE_DIR / "guides"
        if guides.is_dir():
            for f in sorted(guides.glob("*.html")):
                out.append((f"guides/{f.name}", 0.8 if f.name == "index.html" else 0.7))
        return out

    def sitemap(self) -> int:
        """生成 docs/sitemap.xml —— 覆盖全站，而不只是 funds/。"""
        entries: list[tuple[str, str, float]] = [
            (self.site_url(path), self.page_updated, prio)
            for path, prio in self.site_pages()
        ]
        entries += [
            (self.abs_url(filename), lastmod, priority)
            for filename, lastmod, priority in self.pages
        ]
        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]
        for loc, lastmod, priority in sorted(entries, key=lambda x: (-x[2], x[0])):
            parts.append("  <url>")
            parts.append(f"    <loc>{html.escape(loc)}</loc>")
            if lastmod:
                parts.append(f"    <lastmod>{html.escape(lastmod)}</lastmod>")
            parts.append("    <changefreq>monthly</changefreq>")
            parts.append(f"    <priority>{priority:.1f}</priority>")
            parts.append("  </url>")
        parts.append("</urlset>")
        (SITE_DIR / "sitemap.xml").write_text("\n".join(parts) + "\n", encoding="utf-8")
        return len(entries)


# ---------------------------------------------------------------- 静态资源

STYLE_CSS = """/* 强积金成分基金资料库 — 共享样式（本文件由 scripts/build_pages.py 生成） */
:root{
  --bg:#ffffff; --fg:#15202b; --muted:#5a6472; --line:#e3e8ef; --line-strong:#cbd4e1;
  --accent:#1b5e9c; --accent-weak:#eef4fb; --pos:#0b6b3a; --neg:#a62020;
  --card:#f7f9fc; --radius:10px; --max:1180px;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#11161c; --fg:#e7edf4; --muted:#9aa7b6; --line:#263240; --line-strong:#38485a;
    --accent:#7db4e8; --accent-weak:#18222d; --pos:#5fd39b; --neg:#ff8e8e; --card:#171f28;
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--fg);
  font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB",
       "Microsoft YaHei","Noto Sans CJK SC","Source Han Sans SC",sans-serif;
}
main,.crumbs,.site-foot{max-width:var(--max);margin:0 auto;padding:0 16px}
a{color:var(--accent)}
a:hover{text-decoration-thickness:2px}
.skip{position:absolute;left:-9999px}
.skip:focus{left:8px;top:8px;background:var(--bg);padding:8px;z-index:10;border:2px solid var(--accent)}
.crumbs{padding-top:14px;font-size:.86rem;color:var(--muted)}
.crumbs ol{list-style:none;display:flex;flex-wrap:wrap;gap:.35em;margin:0;padding:0}
.crumbs li+li::before{content:"›";margin-right:.35em;color:var(--line-strong)}
.page-head{border-bottom:1px solid var(--line);padding:10px 0 18px;margin-bottom:22px}
h1{font-size:clamp(1.45rem,1.1rem + 1.6vw,2.1rem);line-height:1.3;margin:.2em 0 .25em}
h2{font-size:1.22rem;margin:2.2em 0 .6em;padding-bottom:.3em;border-bottom:1px solid var(--line)}
h3{font-size:1.03rem;margin:1.6em 0 .5em;color:var(--muted)}
.lede{color:var(--muted);margin:.2em 0 0}
.note{color:var(--muted);font-size:.86rem;margin:.6em 0}
th .note,td .note{display:block}
.na{color:var(--muted)}
.pos{color:var(--pos)}
.neg{color:var(--neg)}
.flat{color:var(--muted)}

/* 数据卡片 */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:18px 0 6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px}
.card .k{display:block;font-size:.8rem;color:var(--muted);margin-bottom:.3em}
.card .v{display:block;font-size:1.22rem;font-weight:650;font-variant-numeric:tabular-nums}
.card .v small{font-size:.72rem;font-weight:400;color:var(--muted)}

/* 表格 */
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:var(--radius)}
table{border-collapse:collapse;width:100%;font-size:.9rem}
caption{text-align:left;padding:10px 12px;color:var(--muted);font-size:.85rem;border-bottom:1px solid var(--line)}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
thead th{background:var(--accent-weak);font-size:.82rem;white-space:nowrap;position:sticky;top:0;z-index:2}
tbody tr:nth-child(even){background:color-mix(in srgb,var(--card) 60%,transparent)}
tbody tr:hover{background:var(--accent-weak)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.cat{color:var(--muted);font-size:.84rem}
.data-table{min-width:1000px}
.data-table td,.data-table tbody th[scope=row]{white-space:nowrap}
.data-table td.cat{white-space:normal;min-width:210px}
tbody th[scope=row]{font-weight:600}
table.kv{border:1px solid var(--line);border-radius:var(--radius)}
table.kv th[scope=row]{width:min(34%,250px);background:var(--card);font-weight:600}
.table-hint{color:var(--muted);font-size:.82rem;margin:.5em 0 0}
.sort-btn{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:.3em;font:inherit;color:inherit;width:100%}
.sort-btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
th[aria-sort] .arrow::after{content:"↕";opacity:.35;font-size:.85em}
th[aria-sort=ascending] .arrow::after{content:"↑";opacity:1}
th[aria-sort=descending] .arrow::after{content:"↓";opacity:1}

/* 筛选 */
.filters{border:1px solid var(--line);border-radius:var(--radius);padding:14px;margin:0 0 16px;background:var(--card)}
.f-row{display:flex;flex-wrap:wrap;gap:12px;align-items:end}
.f-row+.f-row{margin-top:12px}
.f-grow{flex:1 1 100%;font-size:.85rem;color:var(--muted)}
.f-item{display:flex;flex-direction:column;gap:4px;flex:0 1 200px}
#f-fer-max{max-width:200px}
.f-item label{font-size:.8rem;color:var(--muted)}
.f-actions{justify-content:end;flex:0 0 auto}
input,select,button{font:inherit;color:inherit;background:var(--bg);border:1px solid var(--line-strong);
  border-radius:8px;padding:7px 9px;max-width:100%}
#f-q{width:100%}
#f-reset{cursor:pointer;background:var(--accent-weak);border-color:var(--accent);color:var(--accent);font-size:.88rem}
.f-status{margin:12px 0 0;font-size:.85rem;color:var(--muted)}

/* 链接列表 */
.link-list{list-style:none;margin:.4em 0;padding:0}
.link-list li{padding:4px 0;border-bottom:1px solid var(--line)}
.link-list li.na{color:var(--muted)}
.link-list .meta{color:var(--muted);font-size:.82rem;margin-left:.6em}
.link-list.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:0 20px}
.link-list.inline{display:flex;flex-wrap:wrap;gap:6px 14px}
.link-list.inline li{border:none;padding:0;font-size:.9rem}
.kv-dl{margin:0}
.kv-dl dt{font-weight:650;margin-top:.9em}
.kv-dl dd{margin:.2em 0 0;color:var(--muted)}

/* 页脚 */
.site-foot{margin:46px auto 0;padding-top:20px;border-top:2px solid var(--line);font-size:.86rem;color:var(--muted);padding-bottom:40px}
.foot-h{font-size:1rem;border:none;margin:0 0 .6em;padding:0}
.foot-meta{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;margin:0 0 14px;max-width:520px}
.foot-meta dt{font-weight:600;color:var(--fg)}
.foot-meta dd{margin:0}
.disclaimer{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line-strong);
  border-radius:8px;padding:12px 14px;line-height:1.7}
.disclaimer strong{color:var(--fg)}
.foot-nav{margin:14px 0 0}
@media (max-width:640px){
  thead th{position:static}
  table{font-size:.84rem}
  table.kv th[scope=row]{width:auto;white-space:nowrap}
  .cards{grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}
}
"""

APP_JS = """/* 强积金成分基金资料库 — 表格排序与筛选（原生 JS，无依赖）
   本文件由 scripts/build_pages.py 生成。 */
(function () {
  'use strict';

  var collator = (typeof Intl !== 'undefined' && Intl.Collator)
    ? new Intl.Collator('zh-Hans', { numeric: true })
    : null;

  function cellValue(cell) {
    var v = cell.getAttribute('data-v');
    return v === null ? cell.textContent.trim() : v;
  }

  function compare(a, b, index, type, dir) {
    var va = cellValue(a.cells[index]);
    var vb = cellValue(b.cells[index]);
    var ea = va === '';
    var eb = vb === '';
    if (ea && eb) return 0;
    if (ea) return 1;          /* 空值永远排在最后 */
    if (eb) return -1;
    if (type === 'num') {
      var na = parseFloat(va);
      var nb = parseFloat(vb);
      if (isNaN(na) && isNaN(nb)) return 0;
      if (isNaN(na)) return 1;
      if (isNaN(nb)) return -1;
      return (na - nb) * dir;
    }
    return (collator ? collator.compare(va, vb) : (va < vb ? -1 : va > vb ? 1 : 0)) * dir;
  }

  function initSortable(table) {
    var headers = table.tHead ? table.tHead.rows[0].cells : [];
    Array.prototype.forEach.call(headers, function (th, index) {
      var type = th.getAttribute('data-type') || 'str';
      var btn = th.querySelector('.sort-btn') || th;
      btn.addEventListener('click', function () {
        var current = th.getAttribute('aria-sort');
        var dir = current === 'ascending' ? -1 : 1;
        Array.prototype.forEach.call(headers, function (other) {
          if (other.hasAttribute('aria-sort')) other.setAttribute('aria-sort', 'none');
        });
        th.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');
        var tbody = table.tBodies[0];
        var rows = Array.prototype.slice.call(tbody.rows);
        rows.sort(function (a, b) { return compare(a, b, index, type, dir); });
        var frag = document.createDocumentFragment();
        rows.forEach(function (r) { frag.appendChild(r); });
        tbody.appendChild(frag);
      });
    });
  }

  function initFilters(form, table) {
    var q = form.querySelector('#f-q');
    var ferMax = form.querySelector('#f-fer-max');
    var reset = form.querySelector('#f-reset');
    var status = form.querySelector('#f-status');
    var selects = Array.prototype.slice.call(form.querySelectorAll('[data-filter-key]'));
    var rows = Array.prototype.slice.call(table.tBodies[0].rows);
    var total = rows.length;

    function apply() {
      var needle = (q && q.value ? q.value : '').trim().toLowerCase();
      var limit = ferMax && ferMax.value !== '' ? parseFloat(ferMax.value) : null;
      var picks = selects.map(function (s) {
        return { key: s.getAttribute('data-filter-key'), value: s.value };
      });
      var shown = 0;
      rows.forEach(function (row) {
        var ok = true;
        if (needle && row.getAttribute('data-search').indexOf(needle) === -1) ok = false;
        if (ok) {
          for (var i = 0; i < picks.length; i++) {
            if (picks[i].value && row.getAttribute('data-' + picks[i].key) !== picks[i].value) {
              ok = false;
              break;
            }
          }
        }
        if (ok && limit !== null && !isNaN(limit)) {
          var fer = row.getAttribute('data-fer');
          if (fer === '' || parseFloat(fer) > limit) ok = false;
        }
        row.hidden = !ok;
        if (ok) shown++;
      });
      if (status) status.textContent = '显示 ' + shown + ' / ' + total + ' 只基金';
    }

    if (q) q.addEventListener('input', apply);
    if (ferMax) ferMax.addEventListener('input', apply);
    selects.forEach(function (s) { s.addEventListener('change', apply); });
    if (reset) {
      reset.addEventListener('click', function () {
        if (q) q.value = '';
        if (ferMax) ferMax.value = '';
        selects.forEach(function (s) { s.value = ''; });
        apply();
      });
    }
    apply();
  }

  document.addEventListener('DOMContentLoaded', function () {
    var tables = document.querySelectorAll('table[data-sortable]');
    Array.prototype.forEach.call(tables, initSortable);
    var form = document.getElementById('filters');
    var table = document.getElementById('fund-table');
    if (form && table) initFilters(form, table);
  });
})();
"""


# ---------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 docs/funds/ 下的静态基金页面")
    ap.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"canonical / sitemap 使用的站点绝对网址（默认 {DEFAULT_BASE_URL}）",
    )
    ap.add_argument(
        "--clean",
        action="store_true",
        help="生成前先清空 docs/funds/",
    )
    args = ap.parse_args()

    if not DATA_JSON.exists():
        print(f"找不到数据文件：{DATA_JSON}", file=sys.stderr)
        return 1

    funds, meta = load()
    if args.clean and OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    groups = build_index(funds)
    schemes: dict[str, list[dict]] = {}
    trustees: dict[str, list[dict]] = {}
    for f in funds:
        schemes.setdefault(f["scheme_name"], []).append(f)
        trustees.setdefault(f["trustee"], []).append(f)

    b = Builder(args.base_url, funds, meta)

    # 文件名冲突检查（基金页 vs 汇总页）
    planned = {f["_href"] for f in funds}
    for prefix, mapping in (("category", groups), ("scheme", schemes), ("trustee", trustees)):
        for key in mapping:
            fn = f"{prefix}-{slugify(key)}.html"
            if fn in planned:
                raise SystemExit(f"文件名冲突：{fn}")
            planned.add(fn)

    for f in funds:
        b.fund_page(f, groups)

    for cat, rows in sorted(groups.items()):
        b.group_page(
            kind="category",
            key_label="基金类别",
            value=cat,
            rows=rows,
            filename=f"category-{slugify(cat)}.html",
            hide_cols=("category",),
            show_filters=True,
            extra_intro=(
                f'<p class="note">本页列出全部受托人旗下属于此基金类别的成分基金，'
                f"基金详情页的同类别排名亦以此 {len(rows)} 只基金为范围。</p>\n"
            ),
        )

    for scheme, rows in sorted(schemes.items()):
        trustee = rows[0]["trustee"]
        b.group_page(
            kind="scheme",
            key_label="强积金计划",
            value=scheme,
            rows=rows,
            filename=f"scheme-{slugify(scheme)}.html",
            hide_cols=("scheme",),
            show_filters=True,
            extra_intro=(
                f'<p class="note">受托人：<a href="trustee-{e(slugify(trustee))}.html">'
                f"{e(trustee)}</a>。</p>\n"
            ),
        )

    for trustee, rows in sorted(trustees.items()):
        b.group_page(
            kind="trustee",
            key_label="受托人",
            value=trustee,
            rows=rows,
            filename=f"trustee-{slugify(trustee)}.html",
            hide_cols=("trustee",),
            show_filters=True,
            extra_intro=(
                f'<p class="note">此受托人旗下共 '
                f'{len({r["scheme_name"] for r in rows})} 个强积金计划、{len(rows)} 只成分基金。</p>\n'
            ),
        )

    b.index_page(groups, schemes, trustees)
    sitemap_urls = b.sitemap()
    (ASSET_DIR / "style.css").write_text(STYLE_CSS, encoding="utf-8")
    (ASSET_DIR / "app.js").write_text(APP_JS, encoding="utf-8")

    print(f"基金详情页 : {len(funds)}")
    print(f"基金类别页 : {len(groups)}")
    print(f"计划汇总页 : {len(schemes)}")
    print(f"受托人汇总页: {len(trustees)}")
    print(f"总表页     : 1")
    print(f"HTML 合计  : {len(b.pages)}")
    print(f"sitemap    : {sitemap_urls} 条 URL -> {SITE_DIR / 'sitemap.xml'}")
    print(f"base-url   : {b.base}")
    if "example.com" in b.base:
        print("提示：canonical / sitemap 仍使用占位域名，部署前请用 --base-url 重新生成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
