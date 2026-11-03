# -*- coding: utf-8 -*-
"""抓取流程編排與輸出。

策略（auto）：
  1. 先試站內下載端點（mpp_download_*.jsp）。拿得到結構化檔案就用它 —— 比
     解析 HTML 穩定，且一次就能拿到全量。
  2. 拿不到才回退到解析 mpp_list.jsp 的 HTML 表格；若頁面以「計劃」下拉分頁，
     則逐一計劃送出查詢（單執行緒、請求間有延遲）。
輸出：data/funds_latest.csv、funds_latest.json、metadata.json、
      （若平台提供）unit_prices_latest.csv。
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

from .fetch import BlockedError, PoliteSession
from .fields import DESC_BY_EN, FUND_COLUMNS, UNIT_PRICE_COLUMNS, ZH_BY_EN
from .normalize import parse_date
from .parse import dedupe, parse_auto, parse_html_tables, parse_unit_prices
from .probe import CANDIDATE_DOWNLOADS
from .parse import _find_header_row  # noqa: F401  (供測試使用)

log = logging.getLogger(__name__)

LIST_PAGE = "/tch/mpp_list.jsp"
UNIT_PRICE_CANDIDATES = [
    "/tch/mpp_download_fund_price.jsp",
    "/tch/mpp_download_unit_price.jsp",
    "/tch/mpp_download_price.jsp",
]

AS_OF_PATTERNS = [
    r"截至\s*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{4})",
    r"截至\s*([0-9]{4}\s*年\s*[0-9]{1,2}\s*月\s*[0-9]{1,2}\s*日)",
    r"資料更新至\s*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{4})",
    r"(?i)as\s+at\s+([0-9]{1,2}\s+\w+\s+[0-9]{4})",
]


def extract_as_of_date(html: str) -> str | None:
    """從頁面文字抓出資料截止日期，轉成 ISO 格式。"""
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    for pat in AS_OF_PATTERNS:
        m = re.search(pat, text)
        if m:
            raw = re.sub(r"\s+", "", m.group(1))
            return parse_date(raw) or raw
    return None


def _try_downloads(session: PoliteSession, paths: list[str], columns: list[str]) -> tuple[list[dict], str | None]:
    """逐一試下載端點，回傳 (紀錄, 成功的 URL)。"""
    for path in paths:
        try:
            r = session.get(path, allow_redirects=True)
        except BlockedError:
            raise
        except Exception as e:  # noqa: BLE001
            log.debug("下載端點 %s 無法取得：%s", path, e)
            continue
        if r.status_code != 200 or not r.content:
            continue
        try:
            recs = parse_auto(r.content, r.headers.get("Content-Type", ""), columns=columns)
        except Exception as e:  # noqa: BLE001
            log.debug("下載端點 %s 解析失敗：%s", path, e)
            continue
        if recs:
            log.info("下載端點可用：%s（%s 筆）", path, len(recs))
            return recs, f"{session.base_url}{path}"
    return [], None


def _scheme_options(html: str) -> list[tuple[str, str, str, str]]:
    """從頁面找出「計劃」下拉選單，回傳 [(form_action, method, field_name, value)]。"""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for form in soup.find_all("form"):
        action = form.get("action") or LIST_PAGE
        method = (form.get("method") or "GET").upper()
        for sel in form.find_all("select"):
            name = sel.get("name")
            if not name:
                continue
            opts = [o.get("value") for o in sel.find_all("option") if (o.get("value") or "").strip()]
            # 選項很多的下拉，通常就是計劃/受託人清單
            if len(opts) >= 5:
                for v in opts:
                    out.append((action, method, name, v))
    return out


def _scrape_html(session: PoliteSession) -> tuple[list[dict], list[str], str | None]:
    """回退路徑：解析 mpp_list.jsp；必要時逐一計劃送出查詢。"""
    sources: list[str] = []
    html = session.get_text(LIST_PAGE)
    sources.append(f"{session.base_url}{LIST_PAGE}")
    as_of = extract_as_of_date(html)

    records = parse_html_tables(html, FUND_COLUMNS)
    log.info("列表頁直接解析到 %s 筆", len(records))

    # 若首頁只給了一部分，依下拉選項逐一查詢補齊
    options = _scheme_options(html)
    if options:
        log.info("偵測到 %s 個查詢選項，逐一送出（有延遲、不併發）", len(options))
    for action, method, field, value in options:
        try:
            if method == "POST":
                r = session.post(action, data={field: value})
            else:
                r = session.get(action, params={field: value})
        except BlockedError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("查詢 %s=%s 失敗：%s", field, value, e)
            continue
        page_recs = parse_html_tables(r.text, FUND_COLUMNS)
        if page_recs:
            records.extend(page_recs)
            sources.append(f"{action}?{field}={value}")

    return dedupe(records), sources, as_of


def scrape_funds(session: PoliteSession, strategy: str = "auto") -> dict:
    """抓取基金資訊表。回傳 {records, sources, as_of_date, method}。"""
    sources: list[str] = []
    as_of = None

    if strategy in ("auto", "download"):
        recs, url = _try_downloads(session, CANDIDATE_DOWNLOADS, FUND_COLUMNS)
        if recs:
            # 截止日期仍需從列表頁取得
            try:
                as_of = extract_as_of_date(session.get_text(LIST_PAGE))
                sources.append(f"{session.base_url}{LIST_PAGE}")
            except Exception:  # noqa: BLE001
                pass
            sources.append(url)
            return {"records": recs, "sources": sources, "as_of_date": as_of, "method": "download_endpoint"}
        if strategy == "download":
            raise RuntimeError("指定了 download 策略，但沒有任何下載端點可用。請先執行 --probe 查看實際端點。")

    recs, sources, as_of = _scrape_html(session)
    return {"records": recs, "sources": sources, "as_of_date": as_of, "method": "html_parse"}


def scrape_unit_prices(session: PoliteSession) -> dict:
    """抓取月末單位價格（平台若有提供）。"""
    recs, url = _try_downloads(session, UNIT_PRICE_CANDIDATES, UNIT_PRICE_COLUMNS)
    return {"records": recs, "source": url}


# ---------------------------------------------------------------- 輸出

def write_csv(records: list[dict], path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in records:
            # None -> 空字串（而非 0 或 "n.a."）
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})


def write_json(records: list[dict], path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [{c: r.get(c) for c in columns} for r in records]  # None -> null
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_metadata(path: Path, *, as_of_date, sources, row_count, method,
                   unit_price_rows=0, unit_price_source=None, validation=None) -> dict:
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
    if validation is not None:
        meta["validation"] = {
            "all_passed": validation["all_passed"],
            "checks": validation["checks"],
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta
