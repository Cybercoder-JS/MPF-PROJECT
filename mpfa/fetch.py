# -*- coding: utf-8 -*-
"""有禮貌的 HTTP 取得層。

規則：固定 User-Agent、請求之間強制延遲、單執行緒不併發、對 5xx/連線錯誤
做指數退避重試。對 4xx（含被代理拒絕的 403）不重試，直接拋出，由上層回報。
"""

from __future__ import annotations

import logging
import random
import time

import requests

log = logging.getLogger(__name__)

BASE = "https://mfp.mpfa.org.hk"
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class BlockedError(RuntimeError):
    """網路層被策略或站點拒絕。不要嘗試繞過，向使用者回報。"""


class PoliteSession:
    def __init__(
        self,
        base_url: str = BASE,
        user_agent: str = DEFAULT_UA,
        delay: float = 1.5,
        jitter: float = 0.5,
        timeout: int = 45,
        max_retries: int = 4,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.delay = delay
        self.jitter = jitter
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request_at = 0.0
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh-HK;q=0.9,zh;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        })

    def _throttle(self) -> None:
        wait = self.delay + random.uniform(0, self.jitter) - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)

    def request(self, method: str, url: str, **kw) -> requests.Response:
        if not url.startswith("http"):
            url = f"{self.base_url}/{url.lstrip('/')}"
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                r = self.s.request(method, url, timeout=self.timeout, **kw)
            except requests.exceptions.ProxyError as e:
                raise BlockedError(
                    f"連線被代理拒絕：{url}\n"
                    f"這通常代表該主機不在本工作階段的允許清單內。請勿繞過，"
                    f"請在雲端環境設定的 Network access / Allowed domains 加入該主機。\n原始錯誤：{e}"
                ) from e
            except requests.RequestException as e:
                last_exc = e
                self._last_request_at = time.monotonic()
                backoff = 2 ** (attempt + 1)
                log.warning("請求失敗（%s），%ss 後重試：%s", type(e).__name__, backoff, url)
                time.sleep(backoff)
                continue
            self._last_request_at = time.monotonic()

            if r.status_code in (403, 407):
                raise BlockedError(
                    f"HTTP {r.status_code}：{url}\n"
                    f"可能是出口代理策略拒絕，或站點拒絕自動化存取。請勿繞過，向使用者回報。"
                )
            if r.status_code >= 500 or r.status_code == 429:
                backoff = 2 ** (attempt + 1)
                log.warning("HTTP %s，%ss 後重試：%s", r.status_code, backoff, url)
                time.sleep(backoff)
                last_exc = requests.HTTPError(f"HTTP {r.status_code}")
                continue
            r.raise_for_status()
            return r
        raise RuntimeError(f"重試 {self.max_retries} 次後仍失敗：{url}（{last_exc}）")

    def get(self, url: str, **kw) -> requests.Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> requests.Response:
        return self.request("POST", url, **kw)

    def get_text(self, url: str, **kw) -> str:
        r = self.get(url, **kw)
        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
            r.encoding = r.apparent_encoding or "utf-8"
        return r.text
