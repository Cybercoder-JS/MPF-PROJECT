# 強積金基金平台資料抓取 (MPFA MPF Fund Platform Scraper)

抓取積金局「強積金基金平台」(https://mfp.mpfa.org.hk) 的基金資訊表，輸出乾淨的結構化檔案。

> ## ⚠️ 目前狀態：尚未取得資料
>
> 本倉庫已完成抓取程式、驗證模組與測試，但**尚未產出 `data/funds_latest.csv`**，
> 因為本雲端工作階段的出口網路策略拒絕連線到資料來源主機。詳見
> [「網路阻擋」](#網路阻擋目前的阻塞點)。解封後執行
> `python scripts/scrape_mpfa_funds.py --probe` 即可接續。

---

## 資料來源

| 來源 | 用途 | 狀態 |
|---|---|---|
| `https://mfp.mpfa.org.hk/tch/mpp_list.jsp` | 基金資訊表（繁體中文版），本專案主要來源 | 待解封 |
| `https://mfp.mpfa.org.hk/tch/mpp_download_*.jsp` | 站內下載端點，若可用則優先使用 | 待探查 |
| `https://data.gov.hk`（積金局開放資料） | 僅有**彙總統計**，無基金層面欄位 | 待解封 |
| [`lotused-ai/mpfa-open-data`](https://github.com/lotused-ai/mpfa-open-data) | 參考鏡像；內容為 7 個彙總統計集 | 可讀取，但**不含**本專案所需欄位 |

### 關於鏡像倉庫的重要說明

`lotused-ai/mpfa-open-data` 鏡像的是 data.gov.hk 上積金局的七個**彙總統計**資料集
（受託人/計劃/基金數目、供款與給付、賬戶數目、核准成分基金淨資產值、DIS 相關、中介人數目）。
即使是其中最接近的「核准成分基金淨資產值」，粒度也是**按季度 × 7 個基金種類**的合計：

```
季度,股票基金,混合資產基金,債券基金,保證基金,強積金保守基金,...,總淨資產值
31-03-2020,331407,306526,41458,75775,108210,4406,867781
```

因此它**無法**提供本專案要求的受託人、計劃名稱、基金名稱、FER、風險級別、
各期回報等基金層面欄位。它可作為交叉核對的參考，不能作為資料來源。

---

## 輸出檔案

| 檔案 | 內容 |
|---|---|
| `data/funds_latest.csv` | 基金資訊表，每隻基金一行（UTF-8 with BOM，Excel 可直接開） |
| `data/funds_latest.json` | 同上，JSON 陣列；空值為 `null` |
| `data/metadata.json` | 資料截止日期、抓取時間、來源 URL、總行數、抓取方式、欄位說明、驗證結果 |
| `data/unit_prices_latest.csv` / `.json` | 月末單位價格（若平台提供） |
| `data/validation_report.txt` | 驗證報告（行數、空值率、風險級別、抽樣核對） |
| `data/probe/probe_report.json` | 端點探查結果（表單、下載連結、表格結構） |

### 欄位

完整的繁體中文原文 ↔ 英文欄位名映射表見 **[`docs/FIELDS.md`](docs/FIELDS.md)**，
該檔由 `mpfa/fields.py` 產生。摘要：

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

---

## 如何執行

```bash
pip install -r requirements.txt

# 1) 先探查：確認是靜態頁、表單 POST、還是有現成下載端點
python scripts/scrape_mpfa_funds.py --probe
#    結果寫到 data/probe/probe_report.json，原始回應存於 data/probe/raw/

# 2) 正式抓取 + 驗證 + 輸出
python scripts/scrape_mpfa_funds.py

# 其他常用選項
python scripts/scrape_mpfa_funds.py --strategy download   # 只走下載端點
python scripts/scrape_mpfa_funds.py --strategy html       # 只解析 HTML
python scripts/scrape_mpfa_funds.py --delay 3.0           # 加大請求間延遲
python scripts/scrape_mpfa_funds.py --no-unit-prices      # 跳過單位價格
python scripts/scrape_mpfa_funds.py --validate-only data/funds_latest.json  # 只重跑驗證（不連網）
```

結束碼：`0` 全部通過 / `1` 驗證有失敗項 / `2` 一筆都沒抓到 / `3` 網路被阻擋。

### 離線自我測試

```bash
python tests/test_offline.py   # 不連網，驗證解析、正規化、輸出、驗證全鏈路
```

---

## 抓取策略

`--strategy auto`（預設）：

1. **先試站內下載端點** `mpp_download_*.jsp`。若能取回 CSV/XLSX，直接使用 —— 比解析
   HTML 穩定，且一次取得全量。
2. **回退解析 HTML**：解析 `mpp_list.jsp` 的表格；若頁面以下拉選單分計劃查詢，
   則逐一計劃送出請求。

解析以**欄位標題文字**對應，而非欄位位置（見 `mpfa/parse.py`），
因此平台調整欄位順序不會造成錯位；只有標題改成未知寫法時，才需在
`mpfa/fields.py` 的 `ALIASES` 補別名。

### 抓取禮儀

- 固定 User-Agent
- 請求之間強制延遲（預設 1.5 秒 + 隨機抖動），**單執行緒、不併發**
- 5xx / 429 / 連線錯誤才重試，指數退避（2s, 4s, 8s, 16s）
- 4xx（含 403）**不重試**，直接中止並回報，不嘗試繞過

---

## 驗證

`mpfa/validate.py` 每次抓取後自動執行，報告寫入 `data/validation_report.txt`
並嵌入 `data/metadata.json`：

1. **行數核對** — 總行數、基金類別數（預期約 451）、計劃數（預期約 24）。
   偏差超過 2% 即標記為可能漏抓，並提示檢查分頁與計劃迴圈。
2. **空值比例** — 列出每個欄位的已填/空值/空值率；`fer_pct` 空值率上限 20%、
   `risk_level` 上限 10%，超過即判定解析可能錯欄。
3. **風險級別範圍** — 必須落在 1–7，超出範圍逐筆列出。
4. **隨機抽樣 5 隻基金** — 輸出完整欄位對照，供與網頁逐項人工核對
   （固定亂數種子，結果可重現）。
5. **`n.a.` 未被當成 0** — 檢查數值欄位 0 值是否異常集中（>30%），
   以偵測空值被誤轉為 0；樣本數低於 30 時不做此判斷以免假警報。

預期值定義在 `mpfa/validate.py` 頂部（`EXPECTED_FUND_CATEGORIES`、
`EXPECTED_SCHEMES`、`MAX_NULL_RATIO`），平台數字變動時在該處調整。

---

## 網路阻擋（目前的阻塞點）

本雲端工作階段的出口代理在 CONNECT 階段拒絕了下列主機（HTTP 403，
與 User-Agent 或站點反爬蟲無關）：

| 主機 | 結果 |
|---|---|
| `mfp.mpfa.org.hk` | 403 connect_rejected |
| `www.mpfa.org.hk` | 403 connect_rejected |
| `data.gov.hk` | 403 connect_rejected |
| `api.data.gov.hk` | 403 connect_rejected |
| `raw.githubusercontent.com` | 200 可達 |

**解封方式**：於工作階段標題列的雲端環境選單 → Edit → Network access，
把上述主機加入 Allowed domains（保留 Allow package managers 勾選），
或改用更寬鬆的存取層級。
說明文件：https://code.claude.com/docs/en/cloud-environments#network-access

程式在遇到此情況時會拋出 `BlockedError` 並以結束碼 `3` 中止，
**不會嘗試繞過**，也不會以假資料填補。

---

## 專案結構

```
mpfa/
  fields.py      欄位定義與繁中↔英文映射、標題別名
  normalize.py   標題比對、n.a. 處理、數值/日期/百分比正規化
  fetch.py       有禮貌的 HTTP 層（UA、延遲、退避重試、阻擋偵測）
  probe.py       端點探查（表單、下載連結、表格結構、下拉選項）
  parse.py       表頭驅動的表格解析（HTML / CSV / XLSX 共用）
  validate.py    五項驗證與報告格式化
  pipeline.py    流程編排與 CSV/JSON/metadata 輸出
scripts/
  scrape_mpfa_funds.py   CLI 入口
  gen_field_doc.py       由 fields.py 重新產生 docs/FIELDS.md
tests/
  test_offline.py        離線全鏈路自我測試
docs/FIELDS.md           欄位映射表（產生檔）
```

## 資料使用聲明

資料來源為香港強制性公積金計劃管理局（積金局）。使用前請參閱積金局網站的
使用條款與資料定義。本倉庫僅作資料抓取與整理，不對資料正確性作保證。
