#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由 mpfa/fields.py 重新產生 docs/FIELDS.md。"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from mpfa.fields import ALIASES, FUND_FIELDS, UNIT_PRICE_FIELDS  # noqa: E402

L = ["# 欄位映射表（繁體中文原文 ↔ 英文欄位名）", "",
     "本檔由 `mpfa/fields.py` 產生，請勿手動編輯；改動請改 `mpfa/fields.py` 後執行",
     "`python scripts/gen_field_doc.py`。", "",
     "## 基金資訊表 `data/funds_latest.csv` / `.json`", "",
     "| 英文欄位名 | 繁體中文原文 | 說明 |", "|---|---|---|"]
L += [f"| `{en}` | {zh} | {d} |" for en, zh, d in FUND_FIELDS]
L += ["", "## 月末單位價格 `data/unit_prices_latest.csv` / `.json`", "",
      "| 英文欄位名 | 繁體中文原文 | 說明 |", "|---|---|---|"]
L += [f"| `{en}` | {zh} | {d} |" for en, zh, d in UNIT_PRICE_FIELDS]
L += ["", "## 標題別名", "",
      "解析時以「欄位標題文字」比對（非欄位位置），因此平台調整欄位順序不會造成錯位。",
      "下列為各欄位可接受的標題寫法；平台若改用新寫法，只需在 `mpfa/fields.py` 的 `ALIASES` 追加。", "",
      "| 英文欄位名 | 可辨識的標題寫法 |", "|---|---|"]
L += [f"| `{en}` | {', '.join(v)} |" for en, v in ALIASES.items()]

out = ROOT / "docs/FIELDS.md"
out.parent.mkdir(exist_ok=True)
out.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"已寫入 {out}")
