# -*- coding: utf-8 -*-
"""可插拔的資料來源。

模式 A `NetworkSource`：直連 mfp.mpfa.org.hk 抓取。
模式 B `LocalSource`：讀取 data/raw/ 下手動下載的 CSV / XLSX / XLS / HTML。

兩者回傳相同的 `FetchResult`，下游的清洗、驗證、輸出完全共用，
因此域名放行與否不影響流水線其餘部分。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .fetch import BlockedError, PoliteSession
from .fields import FUND_COLUMNS, UNIT_PRICE_COLUMNS
from .normalize import parse_date
from .parse import (
    classify_table,
    dedupe,
    extract_as_of_date,
    rows_to_records,
    tables_from_bytes,
    _sniff_text,
)

log = logging.getLogger(__name__)

LIST_PAGE = "/tch/mpp_list.jsp"

# 站內候選下載端點（模式 A 優先嘗試）
FUND_DOWNLOAD_CANDIDATES = [
    "/tch/mpp_download_fund_info.jsp",
    "/tch/mpp_download_fundinfo.jsp",
    "/tch/mpp_download_list.jsp",
    "/tch/mpp_download.jsp",
    "/tch/mpp_download_performance.jsp",
]
UNIT_PRICE_DOWNLOAD_CANDIDATES = [
    "/tch/mpp_download_fund_price.jsp",
    "/tch/mpp_download_unit_price.jsp",
    "/tch/mpp_download_price.jsp",
]

RAW_SUFFIXES = {".csv", ".xlsx", ".xlsm", ".xls", ".html", ".htm", ".tsv", ".txt"}


@dataclass
class FetchResult:
    """來源層的統一回傳型別。"""
    funds: list[dict] = field(default_factory=list)
    unit_prices: list[dict] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    as_of_date: str | None = None
    method: str = ""
    file_report: list[dict] = field(default_factory=list)


# ------------------------------------------------------------------ 模式 B

class LocalSource:
    """模式 B：從本地目錄讀取手動下載的檔案。

    會自動辨識每個檔案（乃至 XLSX 的每個工作表）是「基金資訊表」還是
    「月末單位價格」，依表頭文字判斷，不靠檔名。

    資料截止日期的判定順序：
      1. 明確指定的 as_of 參數（CLI `--as-of`）
      2. 目錄下的 AS_OF.txt（內容為一個日期）
      3. 檔名中的日期（如 fund_info_2026-03-31.csv、20260331.xlsx）
      4. 檔案內容中的「截至 …」字樣
    """

    def __init__(self, raw_dir: Path, as_of: str | None = None) -> None:
        self.raw_dir = Path(raw_dir)
        self.as_of = parse_date(as_of) or as_of if as_of else None

    def _iter_files(self) -> list[Path]:
        if not self.raw_dir.exists():
            raise FileNotFoundError(
                f"找不到原始檔目錄：{self.raw_dir}\n"
                f"請建立該目錄，並把從平台手動下載的 CSV / XLSX 放進去。"
            )
        files = sorted(
            p for p in self.raw_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in RAW_SUFFIXES and not p.name.startswith((".", "~$"))
            and p.name.upper() != "AS_OF.TXT"
        )
        if not files:
            raise FileNotFoundError(
                f"{self.raw_dir} 裡沒有可解析的檔案（支援 {', '.join(sorted(RAW_SUFFIXES))}）。\n"
                f"請把從平台下載的檔案放進去後再執行。"
            )
        return files

    def _as_of_from_sidecar(self) -> str | None:
        side = self.raw_dir / "AS_OF.txt"
        if side.exists():
            return parse_date(side.read_text(encoding="utf-8").strip())
        return None

    @staticmethod
    def _as_of_from_filename(path: Path) -> str | None:
        import re
        name = path.stem
        for pat in (r"(\d{4}-\d{2}-\d{2})", r"(\d{4}_\d{2}_\d{2})", r"(\d{8})(?!\d)",
                    r"(\d{2}-\d{2}-\d{4})"):
            m = re.search(pat, name)
            if m:
                iso = parse_date(m.group(1).replace("_", "-"))
                if iso:
                    return iso
        return None

    def fetch(self) -> FetchResult:
        files = self._iter_files()
        log.info("模式 B：從 %s 讀取 %s 個檔案", self.raw_dir, len(files))

        funds: list[dict] = []
        prices: list[dict] = []
        sources: list[str] = []
        report: list[dict] = []
        as_of_candidates: list[str] = []

        for path in files:
            data = path.read_bytes()
            entry = {"file": str(path.relative_to(self.raw_dir)), "bytes": len(data)}
            try:
                tables = tables_from_bytes(data, filename=path.name)
            except Exception as e:  # noqa: BLE001
                entry["error"] = f"{type(e).__name__}: {e}"
                log.warning("無法解析 %s：%s", path.name, e)
                report.append(entry)
                continue

            if not tables:
                entry["error"] = "檔案中找不到表格"
                log.warning("%s：找不到表格", path.name)
                report.append(entry)
                continue

            f_n = p_n = 0
            kinds = []
            for rows in tables:
                kind = classify_table(rows)
                kinds.append(kind)
                if kind == "unit_prices":
                    recs = rows_to_records(rows, UNIT_PRICE_COLUMNS)
                    prices.extend(recs)
                    p_n += len(recs)
                elif kind == "funds":
                    recs = rows_to_records(rows, FUND_COLUMNS)
                    funds.extend(recs)
                    f_n += len(recs)

            entry.update({"tables": len(tables), "kinds": kinds,
                          "fund_rows": f_n, "unit_price_rows": p_n})
            if f_n == 0 and p_n == 0:
                entry["warning"] = "表頭無法對應到任何已知欄位；請確認檔案內容或在 fields.ALIASES 補別名"
                log.warning("%s：表頭無法辨識，已跳過", path.name)
            else:
                log.info("  %s -> 基金 %s 筆，單位價格 %s 筆", path.name, f_n, p_n)

            report.append(entry)
            sources.append(f"local:{path.relative_to(self.raw_dir)}")

            fn_date = self._as_of_from_filename(path)
            if fn_date:
                as_of_candidates.append(fn_date)
            if path.suffix.lower() in (".csv", ".html", ".htm", ".txt", ".tsv"):
                c = extract_as_of_date(_sniff_text(data[:200_000]))
                if c:
                    as_of_candidates.append(c)

        as_of = (
            self.as_of
            or self._as_of_from_sidecar()
            or (max(as_of_candidates) if as_of_candidates else None)
        )
        if not as_of:
            log.warning(
                "無法判定資料截止日期。metadata.json 的 data_as_of_date 會是 null；"
                "可用 --as-of YYYY-MM-DD 指定，或在 %s 放一個 AS_OF.txt。", self.raw_dir
            )

        return FetchResult(
            funds=dedupe(funds),
            unit_prices=dedupe(prices, keys=("trustee", "scheme_name", "fund_name", "price_date")),
            sources=sources,
            as_of_date=as_of,
            method="local_files",
            file_report=report,
        )


# ------------------------------------------------------------------ 模式 A

class NetworkSource:
    """模式 A：直連平台抓取。先試下載端點，再回退解析 HTML。"""

    def __init__(self, session: PoliteSession, strategy: str = "auto",
                 with_unit_prices: bool = True) -> None:
        self.session = session
        self.strategy = strategy
        self.with_unit_prices = with_unit_prices

    def _try_downloads(self, paths: list[str], columns: list[str]) -> tuple[list[dict], str | None]:
        for path in paths:
            try:
                r = self.session.get(path, allow_redirects=True)
            except BlockedError:
                raise
            except Exception as e:  # noqa: BLE001
                log.debug("下載端點 %s 無法取得：%s", path, e)
                continue
            if r.status_code != 200 or not r.content:
                continue
            try:
                recs: list[dict] = []
                for rows in tables_from_bytes(r.content, r.headers.get("Content-Type", ""), path):
                    recs.extend(rows_to_records(rows, columns))
            except Exception as e:  # noqa: BLE001
                log.debug("下載端點 %s 解析失敗：%s", path, e)
                continue
            if recs:
                log.info("下載端點可用：%s（%s 筆）", path, len(recs))
                return recs, f"{self.session.base_url}{path}"
        return [], None

    def _scheme_options(self, html: str) -> list[tuple[str, str, str, str]]:
        from bs4 import BeautifulSoup
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
                if len(opts) >= 5:
                    out.extend((action, method, name, v) for v in opts)
        return out

    def _scrape_html(self) -> tuple[list[dict], list[str], str | None]:
        html = self.session.get_text(LIST_PAGE)
        sources = [f"{self.session.base_url}{LIST_PAGE}"]
        as_of = extract_as_of_date(html)

        records: list[dict] = []
        for rows in tables_from_bytes(html.encode("utf-8"), "text/html", "list.html"):
            if classify_table(rows) == "funds":
                records.extend(rows_to_records(rows, FUND_COLUMNS))
        log.info("列表頁直接解析到 %s 筆", len(records))

        options = self._scheme_options(html)
        if options:
            log.info("偵測到 %s 個查詢選項，逐一送出（有延遲、不併發）", len(options))
        for action, method, fieldname, value in options:
            try:
                r = (self.session.post(action, data={fieldname: value}) if method == "POST"
                     else self.session.get(action, params={fieldname: value}))
            except BlockedError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("查詢 %s=%s 失敗：%s", fieldname, value, e)
                continue
            page = [rec for rows in tables_from_bytes(r.content, r.headers.get("Content-Type", ""), "p.html")
                    if classify_table(rows) == "funds"
                    for rec in rows_to_records(rows, FUND_COLUMNS)]
            if page:
                records.extend(page)
                sources.append(f"{action}?{fieldname}={value}")
        return records, sources, as_of

    def fetch(self) -> FetchResult:
        sources: list[str] = []
        as_of = None
        method = ""
        records: list[dict] = []

        if self.strategy in ("auto", "download"):
            records, url = self._try_downloads(FUND_DOWNLOAD_CANDIDATES, FUND_COLUMNS)
            if records:
                try:
                    as_of = extract_as_of_date(self.session.get_text(LIST_PAGE))
                    sources.append(f"{self.session.base_url}{LIST_PAGE}")
                except Exception:  # noqa: BLE001
                    pass
                sources.append(url)
                method = "network_download_endpoint"
            elif self.strategy == "download":
                raise RuntimeError(
                    "指定了 download 策略，但沒有任何下載端點可用。"
                    "請先執行 --probe 查看平台實際提供的端點。"
                )

        if not records:
            records, sources, as_of = self._scrape_html()
            method = "network_html_parse"

        prices: list[dict] = []
        price_src = None
        if self.with_unit_prices:
            try:
                prices, price_src = self._try_downloads(UNIT_PRICE_DOWNLOAD_CANDIDATES, UNIT_PRICE_COLUMNS)
                if price_src:
                    sources.append(price_src)
            except BlockedError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("單位價格抓取失敗（不影響主檔）：%s", e)

        return FetchResult(
            funds=dedupe(records),
            unit_prices=dedupe(prices, keys=("trustee", "scheme_name", "fund_name", "price_date")),
            sources=sources,
            as_of_date=as_of,
            method=method,
        )


def build_source(mode: str, *, raw_dir: Path, as_of: str | None = None,
                 session: PoliteSession | None = None, strategy: str = "auto",
                 with_unit_prices: bool = True):
    """依模式建立來源。mode='auto' 時：有本地檔就用本地，否則走網路。"""
    if mode == "local":
        return LocalSource(raw_dir, as_of)
    if mode == "network":
        if session is None:
            raise ValueError("模式 A 需要一個 PoliteSession")
        return NetworkSource(session, strategy, with_unit_prices)
    # auto
    if Path(raw_dir).exists() and any(
        p.suffix.lower() in RAW_SUFFIXES and p.name.upper() != "AS_OF.TXT"
        for p in Path(raw_dir).rglob("*") if p.is_file()
    ):
        log.info("模式 auto：偵測到 %s 有檔案，使用模式 B（本地）", raw_dir)
        return LocalSource(raw_dir, as_of)
    log.info("模式 auto：%s 無檔案，使用模式 A（直連平台）", raw_dir)
    if session is None:
        raise ValueError("模式 A 需要一個 PoliteSession")
    return NetworkSource(session, strategy, with_unit_prices)
