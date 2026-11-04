# -*- coding: utf-8 -*-
"""抓取結果驗證。

檢查項：
1. 行數區間 —— 總行數落在 [MIN_FUND_ROWS, MAX_FUND_ROWS] 算通過；
   超出範圍報 WARN 並印出實際值（不是硬性失敗，但會明顯標示）。計劃數同理。
2. 每個欄位的空值比例；FER 與風險級別不應大面積為空（硬性檢查）。
3. 風險級別必須落在 1-7（硬性檢查）。
4. 隨機抽 5 隻基金，輸出對照表供人工與網頁逐項核對。
5. "n.a." 必須是空值，不得被當成 0（反向偵測 0 值是否異常集中）。
"""

from __future__ import annotations

import random
from collections import Counter

from .fields import (
    FEE_PCT_FIELDS,
    FEE_RAW_FIELDS,
    FUND_COLUMNS,
    numeric_fields,
    zh_for,
)

# 行數預期：用區間而非精確值，超出範圍只報警告並印出實際值。
#
# 註：平台頁面自報「已選擇的成分基金總數: 382」，但同一頁的資料表實際列出
# 451 列基金。經核實以**表格為準**（451 列全部唯一、無隱藏列、無客戶端篩選，
# 且已用結構不變量全量驗證內部一致），頁面計數器與表格不一致屬頁面自身問題。
# 詳見 README 的「頁面計數器與表格不一致」一節。
EXPECTED_FUND_ROWS = 451      # 已核實的實際基金數（以表格為準）
PAGE_REPORTED_TOTAL = 382     # 頁面計數器自報值，僅作記錄，不用於判定
MIN_FUND_ROWS = 380
MAX_FUND_ROWS = 470

EXPECTED_SCHEMES = 24
SCHEME_TOLERANCE = 0.10  # 計劃數容許 ±10%

# 這兩個欄位平台幾乎都有提供，空值率超過門檻代表解析有問題（硬性檢查）
MAX_NULL_RATIO = {"fer_pct": 0.20, "risk_level": 0.10}

RISK_MIN, RISK_MAX = 1, 7

# 0 值比例啟發式的最小樣本數。樣本太小時比例沒有意義（3 筆裡有 1 筆 0 就是 33%），
# 會產生假警報，故低於此數不做判斷。
MIN_SAMPLE_FOR_ZERO_HEURISTIC = 30

PASS, FAIL, WARN, INFO = "PASS", "FAIL", "WARN", "INFO"


class Check:
    def __init__(self, name: str, level: str, detail: str, data=None):
        self.name, self.level, self.detail, self.data = name, level, detail, data

    @property
    def passed(self) -> bool:
        """只有 FAIL 算不通過；WARN 與 INFO 不影響 all_passed。"""
        return self.level != FAIL

    @property
    def status(self) -> str:
        return self.level

    def to_dict(self) -> dict:
        d = {"check": self.name, "status": self.level, "detail": self.detail}
        if self.data is not None:
            d["data"] = self.data
        return d


def check_counts(records: list[dict]) -> list[Check]:
    n = len(records)
    categories = {r.get("fund_category") for r in records if r.get("fund_category")}
    schemes = {r.get("scheme_name") for r in records if r.get("scheme_name")}
    trustees = {r.get("trustee") for r in records if r.get("trustee")}

    # 總行數：區間判定
    if MIN_FUND_ROWS <= n <= MAX_FUND_ROWS:
        rows_check = Check("基金總行數", PASS,
                           f"實際 {n} 行，在預期區間 {MIN_FUND_ROWS}-{MAX_FUND_ROWS} 內",
                           {"actual": n, "min": MIN_FUND_ROWS, "max": MAX_FUND_ROWS})
    else:
        rows_check = Check("基金總行數", WARN,
                           f"實際 {n} 行，超出預期區間 {MIN_FUND_ROWS}-{MAX_FUND_ROWS}"
                           f" —— 偏離預期值 {EXPECTED_FUND_ROWS} 共 {n - EXPECTED_FUND_ROWS:+d}。"
                           f"請確認來源頁是否完整、是否含非預期的額外列，"
                           f"或平台基金數目本身已變動",
                           {"actual": n, "min": MIN_FUND_ROWS, "max": MAX_FUND_ROWS,
                            "expected_reference": EXPECTED_FUND_ROWS})

    got = len(schemes)
    lo, hi = EXPECTED_SCHEMES * (1 - SCHEME_TOLERANCE), EXPECTED_SCHEMES * (1 + SCHEME_TOLERANCE)
    if lo <= got <= hi:
        sch_check = Check("計劃數", PASS, f"實際 {got} 個，預期約 {EXPECTED_SCHEMES}",
                          {"actual": got, "expected": EXPECTED_SCHEMES})
    else:
        sch_check = Check("計劃數", WARN,
                          f"實際 {got} 個，預期約 {EXPECTED_SCHEMES} —— 偏離 "
                          f"{got - EXPECTED_SCHEMES:+d}，可能漏抓整個計劃",
                          {"actual": got, "expected": EXPECTED_SCHEMES})

    return [
        rows_check,
        sch_check,
        Check("基金類別數（資訊）", INFO, f"去重後 {len(categories)} 個不同的基金類別",
              {"actual": len(categories)}),
        Check("受託人數（資訊）", INFO, f"去重後 {len(trustees)} 個受託人",
              {"actual": len(trustees)}),
    ]


def null_ratios(records: list[dict], columns: list[str] | None = None) -> dict[str, dict]:
    columns = columns or FUND_COLUMNS
    n = len(records) or 1
    out = {}
    for col in columns:
        nulls = sum(1 for r in records if r.get(col) is None)
        out[col] = {
            "zh": zh_for(col),
            "null": nulls,
            "filled": len(records) - nulls,
            "null_ratio": round(nulls / n, 4),
        }
    return out


def check_null_ratios(records: list[dict], columns: list[str] | None = None):
    ratios = null_ratios(records, columns)
    checks = []
    for col, limit in MAX_NULL_RATIO.items():
        if col not in ratios:
            continue
        r = ratios[col]["null_ratio"]
        ok = r <= limit
        checks.append(Check(
            f"空值率 {zh_for(col)}({col})",
            PASS if ok else FAIL,
            f"空值率 {r:.1%}（上限 {limit:.0%}）"
            + ("" if ok else " —— 大面積為空，很可能解析錯欄或來源頁不完整"),
            {"null_ratio": r, "limit": limit},
        ))
    return checks, ratios


def check_risk_level(records: list[dict]) -> Check:
    bad = [
        {"fund_name": r.get("fund_name"), "scheme_name": r.get("scheme_name"),
         "risk_level": r.get("risk_level")}
        for r in records
        if r.get("risk_level") is not None and not (RISK_MIN <= r["risk_level"] <= RISK_MAX)
    ]
    dist = Counter(r.get("risk_level") for r in records)
    dist_str = ", ".join(f"{k}:{v}" for k, v in sorted(dist.items(), key=lambda x: (x[0] is None, x[0])))
    if bad:
        return Check("風險級別範圍", FAIL,
                     f"{len(bad)} 筆超出 {RISK_MIN}-{RISK_MAX}；分布 {dist_str}", bad[:50])
    return Check("風險級別範圍", PASS, f"全部落在 {RISK_MIN}-{RISK_MAX}；分布 {dist_str}")


def check_na_not_zero(records: list[dict], columns: list[str] | None = None) -> Check:
    """確認 n.a. 沒有被誤轉成 0：檢查數值欄位中 0 值是否異常集中。

    積金易平台費、保證費等本來就大量為 0，屬正常，故排除費用欄位。
    """
    years = _years_from_columns(columns)
    targets = [c for c in numeric_fields(years) if c not in FEE_PCT_FIELDS]
    suspicious = []
    for col in targets:
        vals = [r.get(col) for r in records]
        zeros = sum(1 for v in vals if v == 0)
        nonnull = sum(1 for v in vals if v is not None)
        if nonnull >= MIN_SAMPLE_FOR_ZERO_HEURISTIC and zeros / nonnull > 0.30:
            suspicious.append({"field": col, "zh": zh_for(col),
                               "zero": zeros, "non_null": nonnull,
                               "zero_ratio": round(zeros / nonnull, 4)})
    if suspicious:
        return Check("n.a. 未被當成 0", FAIL,
                     "下列欄位 0 值比例異常高，疑似把 n.a. 轉成了 0", suspicious)
    return Check("n.a. 未被當成 0", PASS,
                 "數值欄位的 0 值比例正常；n.a. 已保留為空值（費用欄位本就多為 0，已排除）")


def check_fee_parsing(records: list[dict]) -> Check:
    """費用欄位：有原文就該有數值，否則代表出現了看不懂的寫法。"""
    unparsed = []
    for r in records:
        for raw_f in FEE_RAW_FIELDS:
            pct_f = raw_f[:-4] + "_pct"
            if r.get(raw_f) is not None and r.get(pct_f) is None:
                unparsed.append({"fund_name": r.get("fund_name"),
                                 "scheme_name": r.get("scheme_name"),
                                 "field": raw_f, "raw": r.get(raw_f)})
    if unparsed:
        return Check("費用欄位解析", WARN,
                     f"{len(unparsed)} 個費用值有原文但無法解析成數值（原文已保留）",
                     unparsed[:20])
    return Check("費用欄位解析", PASS, "所有有原文的費用值都已解析出數值")


def _years_from_columns(columns: list[str] | None) -> list[int] | None:
    if not columns:
        return None
    ys = [int(c[len("return_cy"):]) for c in columns if c.startswith("return_cy")]
    return ys or None


def sample_for_manual_check(records: list[dict], k: int = 5, seed: int | None = 20260101,
                            columns: list[str] | None = None) -> list[dict]:
    """隨機抽 k 隻基金，輸出成便於跟網頁逐項核對的格式。"""
    columns = columns or FUND_COLUMNS
    rng = random.Random(seed)
    picks = rng.sample(records, min(k, len(records)))
    return [{
        "基金": f"{r.get('trustee')} / {r.get('scheme_name')} / {r.get('fund_name')}",
        "欄位": {zh_for(c) or c: r.get(c) for c in columns},
    } for r in picks]


def run_all(records: list[dict], columns: list[str] | None = None) -> dict:
    columns = columns or FUND_COLUMNS
    checks: list[Check] = []
    checks += check_counts(records)
    nr_checks, ratios = check_null_ratios(records, columns)
    checks += nr_checks
    checks.append(check_risk_level(records))
    checks.append(check_na_not_zero(records, columns))
    checks.append(check_fee_parsing(records))
    return {
        "checks": [c.to_dict() for c in checks],
        "all_passed": all(c.passed for c in checks),
        "warnings": [c.to_dict() for c in checks if c.level == WARN],
        "null_ratios": ratios,
        "manual_sample": sample_for_manual_check(records, columns=columns),
    }


def format_report(result: dict) -> str:
    lines = ["=" * 72, "驗證報告", "=" * 72]
    for c in result["checks"]:
        lines.append(f"[{c['status']:<4}] {c['check']}: {c['detail']}")
        if c["status"] in (FAIL, WARN) and c.get("data"):
            data = c["data"] if isinstance(c["data"], list) else [c["data"]]
            for item in data[:10]:
                lines.append(f"         {item}")

    lines += ["", "-" * 72, "各欄位空值比例", "-" * 72,
              f"{'欄位':<34}{'中文':<22}{'已填':>6}{'空值':>6}{'空值率':>9}"]
    for col, v in result["null_ratios"].items():
        lines.append(f"{col:<34}{(v['zh'] or ''):<22}{v['filled']:>6}{v['null']:>6}{v['null_ratio']:>8.1%}")

    lines += ["", "-" * 72, "隨機抽樣 5 隻基金（請與網頁逐項核對）", "-" * 72]
    for i, s in enumerate(result["manual_sample"], 1):
        lines.append(f"\n{i}. {s['基金']}")
        for k, v in s["欄位"].items():
            lines.append(f"     {k:<24} {'(空值)' if v is None else v}")

    if result.get("warnings"):
        lines += ["", "=" * 72, f"注意：有 {len(result['warnings'])} 項警告", "=" * 72]
        for w in result["warnings"]:
            lines.append(f"  [WARN] {w['check']}: {w['detail']}")
    return "\n".join(lines)
