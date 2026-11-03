# 強積金基金平台資料抓取 (MPFA MPF Fund Platform Scraper)

抓取積金局「強積金基金平台」(https://mfp.mpfa.org.hk) 的基金資訊表，輸出乾淨的結構化檔案。

資料來源是**可插拔**的，清洗、驗證、輸出三段流水線兩種模式完全共用：

| 模式 | 來源 | 狀態 |
|---|---|---|
| **A `network`** | 直連 `mfp.mpfa.org.hk` 抓取 | 待域名放行（見[網路阻擋](#網路阻擋)） |
| **B `local`** | 讀取 `data/raw/` 下手動下載的 CSV / XLSX / XLS / HTML | **現在就能跑** |

> **目前狀態**：`data/funds_latest.csv` 尚未產出，因為本工作階段的出口網路策略
> 拒絕連線到平台（模式 A 不可用），且尚未有人把手動下載的檔案放進 `data/raw/`。
> 流水線本身已完整實作並測試通過 —— 放幾個檔案進 `data/raw/` 就能立刻產出資料。

---

## 快速開始（模式 B，不需要網路）

```bash
pip install -r requirements.txt

# 1) 把從平台手動下載的檔案放進 data/raw/（檔名不重要，程式看表頭自動辨識）
# 2) 跑流水線
python scripts/scrape_mpfa_funds.py --mode local
```

就這樣。輸出會寫到 `data/`，驗證報告直接印在終端機。
詳細說明見 **[`data/raw/README.md`](data/raw/README.md)**。

### 先確認流水線能不能跑（用合成樣例資料）

不必等真實檔案，也不必等域名放行：

```bash
python scripts/make_sample_raw.py --out-dir /tmp/sample_raw
python scripts/scrape_mpfa_funds.py --mode local --raw-dir /tmp/sample_raw --out-dir /tmp/sample_out
```

合成資料有 451 隻基金、24 個計劃，拆成 CSV + XLSX 兩個檔，刻意包含大量 `n.a.`、
括號負數、千分位與前導列。受託人與基金名稱都帶「示例」字樣，**不可當作真實資料**。

### 模式 A（域名放行後）

```bash
python scripts/scrape_mpfa_funds.py --probe      # 先探查：是靜態頁、表單 POST、還是有下載端點
python scripts/scrape_mpfa_funds.py --mode network
```

### 常用選項

```bash
--mode auto|network|local   # 預設 auto：data/raw/ 有檔案就用 B，否則用 A
--raw-dir data/raw          # 模式 B 的來源目錄
--as-of 2026-03-31          # 手動指定資料截止日期
--out-dir data              # 輸出目錄
--strategy download|html    # 模式 A 的抓取方式
--delay 3.0                 # 模式 A 請求間延遲（秒）
--no-unit-prices            # 跳過月末單位價格
--validate-only data/funds_latest.json   # 只重跑驗證，不碰網路也不讀 raw
-v                          # 詳細日誌
```

結束碼：`0` 全部通過 / `1` 驗證有失敗項 / `2` 一筆都沒抓到 / `3` 網路被阻擋 / `4` 找不到原始檔。

### 測試

```bash
python tests/test_offline.py         # 解析、正規化、輸出、驗證的單元測試
python tests/test_local_pipeline.py  # 模式 B 端到端（含失敗路徑）
```

兩者都不連網。

---

## 輸出檔案

| 檔案 | 內容 |
|---|---|
| `data/funds_latest.csv` | 基金資訊表，每隻基金一行（UTF-8 with BOM，Excel 可直接開） |
| `data/funds_latest.json` | 同上，JSON 陣列；空值為 `null` |
| `data/metadata.json` | 資料截止日期、抓取時間、來源、總行數、方式、欄位說明、每個輸入檔的解析結果、驗證結果 |
| `data/unit_prices_latest.csv` / `.json` | 月末單位價格（若來源有提供） |
| `data/validation_report.txt` | 驗證報告（行數、空值率、風險級別、抽樣核對） |
| `data/probe/probe_report.json` | 模式 A 的端點探查結果 |

### 欄位

完整的繁體中文原文 ↔ 英文欄位名映射表見 **[`docs/FIELDS.md`](docs/FIELDS.md)**
（由 `mpfa/fields.py` 產生，執行 `python scripts/gen_field_doc.py` 重新產生）。摘要：

| 英文欄位名 | 繁中原文 | | 英文欄位名 | 繁中原文 |
|---|---|---|---|---|
| `trustee` | 受託人 | | `risk_level` | 風險級別（1–7） |
| `scheme_name` | 計劃名稱 | | `return_1y_annualised` | 1年年率化回報 |
| `fund_name` | 基金名稱 | | `return_5y_annualised` | 5年年率化回報 |
| `fund_category` | 基金類別 | | `return_10y_annualised` | 10年年率化回報 |
| `fund_type` | 基金種類 | | `return_since_launch_annualised` | 成立以來年率化回報 |
| `launch_date` | 成立日期（ISO 8601） | | `return_1y_cumulative` | 1年累積回報 |
| `fund_size_hkd_million` | 基金規模（百萬港元） | | `return_5y_cumulative` | 5年累積回報 |
| `fer_pct` | 基金開支比率 FER（%） | | `return_10y_cumulative` | 10年累積回報 |
| | | | `return_since_launch_cumulative` | 成立以來累積回報 |

### 空值約定（重要）

平台上大量欄位顯示 `n.a.`。本專案**一律將其視為空值，絕不轉成 0**：

- CSV：輸出為空字串
- JSON：輸出為 `null`

真實的 `0.00`（例如強積金保守基金的回報）會原樣保留為 `0.0`。
`mpfa/normalize.py` 的 `NA_TOKENS` 列出所有被視為「無資料」的寫法
（`n.a.`、`n/a`、`-`、`不適用`、`無` 等），刻意不包含 `0`。

驗證階段還會反向檢查：若某個數值欄位的 `0` 值比例異常高（>30%），
會判定為「疑似把 n.a. 轉成了 0」並報出來。

### 原文保真

文字欄位（受託人、計劃名稱、基金名稱等）**只壓縮空白，不做 NFKC 正規化**，
因為 NFKC 會把全角標點改寫成半角（如基金名稱裡的 `股票基金－環球` 的 `－` 變成 `-`），
那等於篡改平台原文。NFKC 只用於欄位標題比對與空值偵測，不會寫進輸出。

---

## 設計

### 表頭驅動解析

解析以**欄位標題文字**對應，而非欄位位置（`mpfa/parse.py`）。因此：

- 平台調整欄位順序、增刪欄位，解析不會錯位
- CSV / XLSX / HTML 三種格式共用同一套映射邏輯
- 檔案是「基金資訊表」還是「月末單位價格」，依表頭自動判斷，不看檔名
- 只有當標題改成未知寫法時，才需在 `mpfa/fields.py` 的 `ALIASES` 補別名，解析層不動

表頭不在第一列也沒問題（平台下載檔常有標題與截止日期的前導列），
`find_header_row` 會在前 15 列裡找出辨識欄位最多的那一列。

### 抓取禮儀（模式 A）

- 固定 User-Agent
- 請求之間強制延遲（預設 1.5 秒 + 隨機抖動），**單執行緒、不併發**
- 5xx / 429 / 連線錯誤才重試，指數退避（2s, 4s, 8s, 16s）
- 4xx（含 403）**不重試**，直接中止並回報，不嘗試繞過

---

## 驗證

每次抓取後自動執行（`mpfa/validate.py`），報告寫入 `data/validation_report.txt`
並嵌入 `data/metadata.json`：

1. **行數核對** — 基金總行數（預期約 451）、計劃數（預期約 24）。偏差超過 2%
   即標記為可能漏抓，並提示檢查分頁、計劃迴圈，或下載檔是否只含部分計劃。
   受託人數與去重後的基金類別數另作資訊性輸出。
2. **空值比例** — 列出每個欄位的已填/空值/空值率；`fer_pct` 空值率上限 20%、
   `risk_level` 上限 10%，超過即判定解析可能錯欄。
3. **風險級別範圍** — 必須落在 1–7，超出範圍逐筆列出。
4. **隨機抽樣 5 隻基金** — 輸出完整欄位對照，供與網頁逐項人工核對
   （固定亂數種子，結果可重現）。
5. **`n.a.` 未被當成 0** — 檢查數值欄位 0 值是否異常集中（>30%）；
   樣本數低於 30 時不做此判斷以免假警報。

預期值定義在 `mpfa/validate.py` 頂部，平台數字變動時在該處調整。

> **關於「451 個基金類別」**：平台上「基金類別」一詞的確切粒度要見到真實資料
> 才能確認，因此目前把 451 當作**基金總行數**做硬性檢查（最可能的解讀），
> 而去重後的「基金類別數」只作資訊性輸出，不判定成敗，以免誤報。
> 見到真實資料後若確認 451 指的是去重後的類別數，把
> `EXPECTED_FUND_CATEGORIES` 設為 451 即可啟用該項檢查。

---

## 資料來源

| 來源 | 用途 | 狀態 |
|---|---|---|
| `https://mfp.mpfa.org.hk/tch/mpp_list.jsp` | 基金資訊表（繁體中文版），主要來源 | 待放行 |
| `https://mfp.mpfa.org.hk/tch/mpp_download_*.jsp` | 站內下載端點，若可用則優先使用 | 待探查 |
| `https://data.gov.hk`（積金局開放資料） | 僅有**彙總統計**，無基金層面欄位 | 待放行 |
| [`lotused-ai/mpfa-open-data`](https://github.com/lotused-ai/mpfa-open-data) | 參考鏡像；內容為 7 個彙總統計集 | 可讀取，但**不含**所需欄位 |

### 關於鏡像倉庫的重要說明

`lotused-ai/mpfa-open-data` 鏡像的是 data.gov.hk 上積金局的七個**彙總統計**資料集
（受託人/計劃/基金數目、供款與給付、賬戶數目、核准成分基金淨資產值、DIS 相關、中介人數目）。
即使是其中最接近的「核准成分基金淨資產值」，粒度也是**按季度 × 7 個基金種類**的合計：

```
季度,股票基金,混合資產基金,債券基金,保證基金,強積金保守基金,...,總淨資產值
31-03-2020,331407,306526,41458,75775,108210,4406,867781
```

因此它**無法**提供本專案要求的受託人、計劃名稱、基金名稱、FER、風險級別、
各期回報等基金層面欄位。可作交叉核對的參考，不能作為資料來源。

---

## 網路阻擋

本雲端工作階段的出口代理在 CONNECT 階段拒絕了下列主機（HTTP 403，
與 User-Agent 或站點反爬蟲無關）：

| 主機 | 結果 |
|---|---|
| `mfp.mpfa.org.hk` | 403 connect_rejected |
| `www.mpfa.org.hk` | 403 connect_rejected |
| `data.gov.hk` | 403 connect_rejected |
| `api.data.gov.hk` | 403 connect_rejected |
| `raw.githubusercontent.com` | 200 可達 |

**若要啟用模式 A**：於工作階段標題列的雲端環境選單 → Edit → Network access，
把上述主機加入 Allowed domains（保留 Allow package managers 勾選），
或改用更寬鬆的存取層級。
說明：https://code.claude.com/docs/en/cloud-environments#network-access

程式遇到此情況時會拋出 `BlockedError`、以結束碼 `3` 中止並提示改用模式 B，
**不會嘗試繞過**，也不會以假資料填補。

**若域名放行不了**，模式 B 就是正式路徑，不是權宜之計 —— 兩種模式共用同一條
清洗/驗證/輸出流水線，產出的檔案與驗證報告完全一致。

---

## 專案結構

```
mpfa/
  fields.py      欄位定義與繁中↔英文映射、標題別名
  normalize.py   標題比對、n.a. 處理、數值/日期正規化（值不做 NFKC）
  parse.py       表頭驅動的表格解析（HTML / CSV / XLSX / XLS 共用）、檔案類型判斷
  sources.py     可插拔來源：NetworkSource（模式 A）、LocalSource（模式 B）
  fetch.py       有禮貌的 HTTP 層（UA、延遲、退避重試、阻擋偵測）
  probe.py       模式 A 的端點探查（表單、下載連結、表格結構、下拉選項）
  validate.py    五項驗證與報告格式化
  pipeline.py    流程編排與 CSV/JSON/metadata 輸出
scripts/
  scrape_mpfa_funds.py   CLI 入口
  make_sample_raw.py     產生合成樣例原始檔（驗證流水線用）
  gen_field_doc.py       由 fields.py 重新產生 docs/FIELDS.md
tests/
  test_offline.py        解析/正規化/輸出/驗證單元測試
  test_local_pipeline.py 模式 B 端到端測試（含失敗路徑）
data/raw/README.md       模式 B 的投放目錄說明
docs/FIELDS.md           欄位映射表（產生檔）
```

## 資料使用聲明

資料來源為香港強制性公積金計劃管理局（積金局）。使用前請參閱積金局網站的
使用條款與資料定義。本倉庫僅作資料抓取與整理，不對資料正確性作保證。
