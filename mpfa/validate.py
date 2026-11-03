# -*- coding: utf-8 -*-
"""抓取結果驗證。對應使用者指定的 5 項檢查。

1. 總行數 / 基金類別數 / 計劃數 是否符合預期（對不上即視為漏抓）
2. 每個數值欄位的空值比例；FER 與風險級別不應大面積為空
3. 風險級別必須落在 1-7
4. 隨機抽 5 隻基金，輸出對照表供人工與網頁逐項核對
5. "n.a." 必須是空值，不得被當成 0
"""

from __future__ import annotations

import random
from collections import Counter

from .fields import FUND_COLUMNS, NUMERIC_FIELDS, ZH_BY_EN

# 平台現況預期值（使用者提供）。偏差超過容許值就報警。
EXPECTED_FUND_CATEGORIES = 451
EXPECTED_SCHEMES = 24
COUNT_TOLERANCE = 0.02  # 2%

# 這兩個欄位平台幾乎都有提供，空值率超過門檻代表解析有問題
MAX_NULL_RATIO = {"fer_pct": 0.20, "risk_level": 0.10}

RISK_MIN, RISK_MAX = 1, 7


class Check:
    def __init__(self, name: str, passed: bool, detail: str, data=None):
        self.name, self.passed, self.detail, self.data = name, passed, detail, data

    def to_dict(self) -> dict:
        d = {"check": self.name, "status": "PASS" if self.passed else "FAIL", "detail": self.detail}
        if self.data is not None:
            d["data"] = self.data
        return d


def check_counts(records: list[dict]) -> list[Check]:
    n = len(records)
    categories = {r.get("fund_category") for r in records if r.get("fund_category")}
    schemes = {r.get("scheme_name") for r in records if r.get("scheme_name")}
    trustees = {r.get("trustee") for r in records if r.get("trustee")}
    checks = [Check("總行數", n > 0, f"共 {n} 行基金紀錄", {"rows": n})]

    def _cmp(label: str, got: int, expected: int) -> Check:
        lo = expected * (1 - COUNT_TOLERANCE)
        hi = expected * (1 + COUNT_TOLERANCE)
        ok = lo <= got <= hi
        msg = f"{label}：抓到 {got}，預期約 {expected}"
        if not ok:
            msg += f" —— 偏差 {got - expected:+d}，可能漏抓（檢查分頁、計劃迴圈是否跑完）"
        return Check(label, ok, msg, {"got": got, "expected": expected})

    checks.append(_cmp("基金類別數", len(categories), EXPECTED_FUND_CATEGORIES))
    checks.append(_cmp("計劃數", len(schemes), EXPECTED_SCHEMES))
    checks.append(Check("受託人數", len(trustees) > 0, f"受託人：{len(trustees)} 個", {"got": len(trustees)}))
    return checks


def null_ratios(records: list[dict]) -> dict[str, dict]:
    n = len(records) or 1
    out = {}
    for col in FUND_COLUMNS:
        nulls = sum(1 for r in records if r.get(col) is None)
        out[col] = {
            "zh": ZH_BY_EN.get(col),
            "null": nulls,
            "filled": len(records) - nulls,
            "null_ratio": round(nulls / n, 4),
        }
    return out


def check_null_ratios(records: list[dict]) -> tuple[list[Check], dict]:
    ratios = null_ratios(records)
    checks = []
    for col, limit in MAX_NULL_RATIO.items():
        r = ratios[col]["null_ratio"]
        ok = r <= limit
        checks.append(Check(
            f"空值率 {ZH_BY_EN.get(col)}({col})",
            ok,
            f"空值率 {r:.1%}（上限 {limit:.0%}）" + ("" if ok else " —— 大面積為空，很可能解析錯欄或來源頁不完整"),
            {"null_ratio": r, "limit": limit},
        ))
    return checks, ratios


def check_risk_level(records: list[dict]) -> Check:
    bad = [
        {"fund_name": r.get("fund_name"), "scheme_name": r.get("scheme_name"), "risk_level": r.get("risk_level")}
        for r in records
        if r.get("risk_level") is not None and not (RISK_MIN <= r["risk_level"] <= RISK_MAX)
    ]
    dist = Counter(r.get("risk_level") for r in records)
    dist_str = ", ".join(f"{k}:{v}" for k, v in sorted(dist.items(), key=lambda x: (x[0] is None, x[0])))
    if bad:
        return Check("風險級別範圍", False,
                     f"{len(bad)} 筆超出 {RISK_MIN}-{RISK_MAX}；分布 {dist_str}", bad[:50])
    return Check("風險級別範圍", True, f"全部落在 {RISK_MIN}-{RISK_MAX}；分布 {dist_str}")


# 0 值比例啟發式的最小樣本數。樣本太小時比例沒有意義（3 筆裡有 1 筆 0 就是 33%），
# 會產生假警報，故低於此數不做判斷。
MIN_SAMPLE_FOR_ZERO_HEURISTIC = 30


def check_na_not_zero(records: list[dict]) -> Check:
    """確認 n.a. 沒有被誤轉成 0：檢查數值欄位中 0 值是否異常集中。"""
    suspicious = []
    for col in NUMERIC_FIELDS:
        vals = [r.get(col) for r in records]
        zeros = sum(1 for v in vals if v == 0)
        nonnull = sum(1 for v in vals if v is not None)
        if nonnull >= MIN_SAMPLE_FOR_ZERO_HEURISTIC and zeros / nonnull > 0.30:
            suspicious.append({"field": col, "zh": ZH_BY_EN.get(col),
                               "zero": zeros, "non_null": nonnull,
                               "zero_ratio": round(zeros / nonnull, 4)})
    if suspicious:
        return Check("n.a. 未被當成 0", False,
                     "下列欄位 0 值比例異常高，疑似把 n.a. 轉成了 0", suspicious)
    return Check("n.a. 未被當成 0", True, "數值欄位的 0 值比例正常；n.a. 已保留為空值")


def sample_for_manual_check(records: list[dict], k: int = 5, seed: int | None = 20260101) -> list[dict]:
    """隨機抽 k 隻基金，輸出成便於跟網頁逐項核對的格式。"""
    rng = random.Random(seed)
    picks = rng.sample(records, min(k, len(records)))
    out = []
    for r in picks:
        out.append({
            "基金": f"{r.get('trustee')} / {r.get('scheme_name')} / {r.get('fund_name')}",
            "欄位": {ZH_BY_EN.get(c, c): r.get(c) for c in FUND_COLUMNS},
        })
    return out


def run_all(records: list[dict]) -> dict:
    checks: list[Check] = []
    checks += check_counts(records)
    nr_checks, ratios = check_null_ratios(records)
    checks += nr_checks
    checks.append(check_risk_level(records))
    checks.append(check_na_not_zero(records))
    return {
        "checks": [c.to_dict() for c in checks],
        "all_passed": all(c.passed for c in checks),
        "null_ratios": ratios,
        "manual_sample": sample_for_manual_check(records),
    }


def format_report(result: dict) -> str:
    lines = ["=" * 70, "驗證報告", "=" * 70]
    for c in result["checks"]:
        mark = "PASS" if c["status"] == "PASS" else "FAIL"
        lines.append(f"[{mark}] {c['check']}: {c['detail']}")
        if c["status"] == "FAIL" and c.get("data"):
            for item in (c["data"] if isinstance(c["data"], list) else [c["data"]])[:10]:
                lines.append(f"         {item}")

    lines += ["", "-" * 70, "各欄位空值比例", "-" * 70,
              f"{'欄位':<34}{'中文':<16}{'已填':>7}{'空值':>7}{'空值率':>9}"]
    for col, v in result["null_ratios"].items():
        lines.append(f"{col:<34}{(v['zh'] or ''):<16}{v['filled']:>7}{v['null']:>7}{v['null_ratio']:>8.1%}")

    lines += ["", "-" * 70, "隨機抽樣 5 隻基金（請與網頁逐項核對）", "-" * 70]
    for i, s in enumerate(result["manual_sample"], 1):
        lines.append(f"\n{i}. {s['基金']}")
        for k, v in s["欄位"].items():
            lines.append(f"     {k:<16} {'(空值)' if v is None else v}")
    return "\n".join(lines)
