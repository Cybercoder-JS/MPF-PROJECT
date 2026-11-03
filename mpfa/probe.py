# -*- coding: utf-8 -*-
"""端點探查：解封網路後第一步執行，用真實證據決定抓取方式。

輸出到 --probe-dir：
  raw/            原始回應（HTML / CSV / XLSX）
  probe_report.json  表單、下載連結、表格標題、下拉選項、候選端點探測結果

有現成的下載端點就優先用（比解析 HTML 穩定）；沒有才回退到逐頁解析。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .fetch import BlockedError, PoliteSession
from .normalize import resolve_header

log = logging.getLogger(__name__)

# 站內常見的入口頁（繁體中文版）
ENTRY_PAGES = [
    "/tch/mpp_list.jsp",
    "/tch/index.jsp",
]

# 候選下載端點。探查時逐一試探，記錄狀態碼與 Content-Type，不猜測結果。
CANDIDATE_DOWNLOADS = [
    "/tch/mpp_download_fund_info.jsp",
    "/tch/mpp_download_fundinfo.jsp",
    "/tch/mpp_download_list.jsp",
    "/tch/mpp_download.jsp",
    "/tch/mpp_download_fund_price.jsp",
    "/tch/mpp_download_unit_price.jsp",
    "/tch/mpp_download_price.jsp",
    "/tch/mpp_download_performance.jsp",
]

DOWNLOAD_LINK_RE = re.compile(r"(mpp_download|\.csv|\.xlsx?|\.zip)", re.I)


def _describe_form(form, base: str) -> dict:
    inputs = []
    for el in form.find_all(["input", "select", "textarea"]):
        item = {"tag": el.name, "name": el.get("name"), "type": el.get("type")}
        if el.name == "select":
            opts = [
                {"value": o.get("value"), "text": (o.get_text() or "").strip()}
                for o in el.find_all("option")
            ]
            item["option_count"] = len(opts)
            item["options_sample"] = opts[:40]
        else:
            item["value"] = el.get("value")
        inputs.append(item)
    return {
        "action": urljoin(base, form.get("action") or ""),
        "method": (form.get("method") or "GET").upper(),
        "inputs": inputs,
    }


def _describe_tables(soup: BeautifulSoup) -> list[dict]:
    out = []
    for i, t in enumerate(soup.find_all("table")):
        rows = t.find_all("tr")
        if not rows:
            continue
        header_cells = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
        # 有些表頭在第二列
        if len(rows) > 1 and sum(1 for h in header_cells if resolve_header(h)) < 2:
            alt = [c.get_text(" ", strip=True) for c in rows[1].find_all(["th", "td"])]
            if sum(1 for h in alt if resolve_header(h)) > sum(1 for h in header_cells if resolve_header(h)):
                header_cells = alt
        mapped = {h: resolve_header(h) for h in header_cells}
        out.append({
            "index": i,
            "row_count": len(rows),
            "headers": header_cells,
            "header_mapping": mapped,
            "recognised_fields": sorted({v for v in mapped.values() if v}),
            "id": t.get("id"),
            "class": t.get("class"),
        })
    return out


def probe(session: PoliteSession, probe_dir: Path) -> dict:
    raw_dir = probe_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"base_url": session.base_url, "pages": [], "candidate_downloads": []}

    for page in ENTRY_PAGES:
        entry: dict = {"path": page}
        try:
            html = session.get_text(page)
        except BlockedError:
            raise
        except Exception as e:  # noqa: BLE001
            entry["error"] = f"{type(e).__name__}: {e}"
            report["pages"].append(entry)
            continue

        fname = page.strip("/").replace("/", "_") + ".html"
        (raw_dir / fname).write_text(html, encoding="utf-8")
        entry["saved_as"] = f"raw/{fname}"
        entry["bytes"] = len(html.encode("utf-8"))

        soup = BeautifulSoup(html, "lxml")
        entry["title"] = (soup.title.get_text(strip=True) if soup.title else None)
        entry["forms"] = [_describe_form(f, urljoin(session.base_url, page)) for f in soup.find_all("form")]
        entry["tables"] = _describe_tables(soup)
        entry["download_links"] = sorted({
            urljoin(urljoin(session.base_url, page), a.get("href"))
            for a in soup.find_all("a", href=True)
            if DOWNLOAD_LINK_RE.search(a["href"])
        })
        # 內嵌 JS 中出現的 .jsp / 下載路徑，常見於以 JS 組裝的查詢
        scripts = " ".join(s.get_text() for s in soup.find_all("script"))
        entry["js_endpoint_hints"] = sorted(set(re.findall(r"[\w/\.\-]+\.jsp[\w\?=&%\.\-]*", scripts)))[:60]
        # 分頁線索
        entry["pagination_hints"] = sorted(set(re.findall(
            r"(?i)(page|pageno|pageindex|currentpage|start|offset|rows|pagesize)\s*[=:]\s*['\"]?\d+", html
        )))[:40]
        report["pages"].append(entry)

    for path in CANDIDATE_DOWNLOADS:
        item: dict = {"path": path}
        try:
            r = session.get(path, allow_redirects=True)
            item.update({
                "status": r.status_code,
                "content_type": r.headers.get("Content-Type"),
                "content_disposition": r.headers.get("Content-Disposition"),
                "bytes": len(r.content),
                "looks_like_file": bool(r.headers.get("Content-Disposition"))
                or "text/html" not in (r.headers.get("Content-Type") or ""),
            })
            if item["looks_like_file"] and r.content:
                out = raw_dir / (path.strip("/").replace("/", "_") + ".bin")
                out.write_bytes(r.content)
                item["saved_as"] = f"raw/{out.name}"
        except BlockedError:
            raise
        except Exception as e:  # noqa: BLE001
            item["error"] = f"{type(e).__name__}: {e}"
        report["candidate_downloads"].append(item)

    (probe_dir / "probe_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def summarise(report: dict) -> str:
    lines = ["=== 探查摘要 ==="]
    for p in report.get("pages", []):
        lines.append(f"\n[頁面] {p['path']}  {p.get('error') or str(p.get('bytes')) + ' bytes'}")
        if p.get("error"):
            continue
        lines.append(f"  標題: {p.get('title')}")
        lines.append(f"  表單: {len(p.get('forms', []))}")
        for f in p.get("forms", []):
            names = [i["name"] for i in f["inputs"] if i.get("name")]
            lines.append(f"    - {f['method']} {f['action']}  欄位({len(names)}): {names[:12]}")
            for i in f["inputs"]:
                if i.get("option_count"):
                    lines.append(f"        select {i['name']}: {i['option_count']} 個選項")
        for t in p.get("tables", []):
            if t["recognised_fields"]:
                lines.append(
                    f"  表格#{t['index']}: {t['row_count']} 列, 可辨識欄位 "
                    f"{len(t['recognised_fields'])} 個 -> {t['recognised_fields']}"
                )
        if p.get("download_links"):
            lines.append(f"  下載連結: {p['download_links'][:10]}")
        if p.get("js_endpoint_hints"):
            lines.append(f"  JS 端點線索: {p['js_endpoint_hints'][:10]}")
    lines.append("\n[候選下載端點]")
    for c in report.get("candidate_downloads", []):
        if c.get("error"):
            lines.append(f"  {c['path']}: {c['error']}")
        else:
            flag = "★檔案" if c.get("looks_like_file") else " html"
            lines.append(
                f"  {flag} {c['path']}: HTTP {c['status']}, {c.get('content_type')}, {c.get('bytes')} bytes"
            )
    return "\n".join(lines)
