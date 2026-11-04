# 強積金基金平台資料抓取 (MPFA MPF Fund Platform Scraper)

抓取積金局「強積金基金平台」(https://mfp.mpfa.org.hk) `mpp_list.jsp` 基金資訊表，
輸出乾淨的結構化檔案。

資料來源是**可插拔**的，清洗、驗證、輸出三段流水線兩種模式完全共用：

| 模式 | 來源 | 狀態 |
|---|---|---|
| **A `network`** | 直連 `mfp.mpfa.org.hk` 抓取 | 域名未放行（見[網路阻擋](#網路阻擋)） |
| **B `local`** | 讀取 `data/raw/` 下手動下載的網頁或檔案 | **使用中** |

目前的資料來自手動存下的 `data/raw/mpp_list.html`（資料截至 **2026-09-30**，
平台最後更新 2026-10-12），共 **451 列基金**、24 個計劃。

> 頁面上的計數器顯示「已選擇的成分基金總數: 382」，與資料表實際列出的 451 列
> 不一致。經核實**以表格的 451 列為準**，詳見
> [頁面計數器與表格不一致](#頁面計數器與表格不一致以表格為準)。

---

## 快速開始

```bash
pip install -r requirements.txt

# 把從平台存下的 mpp_list.jsp 網頁（或 CSV/XLSX）放進 data/raw/，然後：
python scripts/scrape_mpfa_funds.py --mode local
```

輸出寫到 `data/`，驗證報告直接印在終端機並存成 `data/validation_report.txt`。
投放目錄的細節見 **[`data/raw/README.md`](data/raw/README.md)**。

### 先確認流水線能不能跑（合成樣例資料）

```bash
python scripts/make_sample_raw.py --out-dir /tmp/sample_raw
python scripts/scrape_mpfa_funds.py --mode local --raw-dir /tmp/sample_raw --out-dir /tmp/sample_out
```

樣例是一份結構鏡像 `mpp_list.jsp` 的合成 HTML（382 隻基金 / 24 個計劃，含三列表頭、
`arCol`/`crCol`/`cyrCol` class、「最高 X」與區間費用、大量 `n.a.`）。
計劃與基金名稱都帶「示例」字樣，**不可當作真實強積金資料**。

### 模式 A（域名放行後）

```bash
python scripts/scrape_mpfa_funds.py --probe          # 探查端點與頁面結構
python scripts/scrape_mpfa_funds.py --mode network
```

### 常用選項

```bash
--mode auto|network|local   # 預設 auto：data/raw/ 有檔案就用 B，否則用 A
--raw-dir data/raw          # 模式 B 的來源目錄
--as-of 2026-09-30          # 手動指定資料截止日期
--out-dir data              # 輸出目錄
--delay 3.0                 # 模式 A 請求間延遲（秒）
--validate-only data/funds_latest.json   # 只重跑驗證，不碰網路也不讀 raw
-v                          # 詳細日誌
```

結束碼：`0` 通過（可能含警告）/ `1` 有硬性檢查失敗 / `2` 一筆都沒抓到 /
`3` 網路被阻擋 / `4` 找不到原始檔。

### 測試

```bash
python tests/test_offline.py        # 單元：欄位比對、正規化、費用解析、輸出、驗證
python tests/test_mpp_html.py       # mpp_list.jsp HTML 解析器（含真實頁面）
python tests/test_local_pipeline.py # 模式 B 端到端（含失敗路徑）
```

三套都不連網。

---

## 輸出檔案

| 檔案 | 內容 |
|---|---|
| `data/funds_latest.csv` | 基金資訊表，每隻基金一行（UTF-8 with BOM，Excel 可直接開） |
| `data/funds_latest.json` | 同上，JSON 陣列；空值為 `null` |
| `data/metadata.json` | 截止日期、抓取時間、來源、總行數、曆年年份、頁面自報總數、欄位說明、解析診斷、驗證結果 |
| `data/validation_report.txt` | 驗證報告（行數、空值率、風險級別、抽樣核對） |
| `data/unit_prices_latest.csv` / `.json` | 月末單位價格（平台若另行提供） |
| `data/probe/probe_report.json` | 模式 A 的端點探查結果 |

### 欄位（33 個）

完整映射表見 **[`docs/FIELDS.md`](docs/FIELDS.md)**（由 `mpfa/fields.py` 產生，
執行 `python scripts/gen_field_doc.py` 重新產生）。

| 英文欄位名 | 繁中原文 | | 英文欄位名 | 繁中原文 |
|---|---|---|---|---|
| `scheme_name` | 計劃 | | `return_1y_cumulative` | 累積回報 一年期 |
| `fund_name` | 成分基金 | | `return_5y_cumulative` | 累積回報 五年期 |
| `trustee` | 受託人 | | `return_10y_cumulative` | 累積回報 十年期 |
| `fund_category` | 基金類別 | | `return_since_launch_cumulative` | 累積回報 推出至今 |
| `launch_date` | 推出日期（ISO 8601） | | `return_cy2025` … `return_cy2021` | 曆年回報 2025–2021 |
| `fund_size_hkd_million` | 基金規模（百萬港元） | | `management_fee_raw` / `_pct` | 基金管理費 |
| `risk_level` | 風險級別（1–7） | | `trustee_custodian_fee_raw` / `_pct` | 受託人費／保管人費 |
| `fer_pct` | 最近期基金開支比率（%） | | `empf_platform_fee_raw` / `_pct` | 積金易平台費 |
| `return_1y_annualised` | 年率化回報 一年期 | | `member_service_fee_raw` / `_pct` | 成員服務費 |
| `return_5y_annualised` | 年率化回報 五年期 | | `investment_management_fee_raw` / `_pct` | 投資管理費 |
| `return_10y_annualised` | 年率化回報 十年期 | | `guarantee_fee_raw` / `_pct` | 保證費 |
| `return_since_launch_annualised` | 年率化回報 推出至今 | | | |

`基金種類` 不是這張表的欄目；它是 `fund_category` 的前綴
（如「股票基金 - 亞洲股票基金」的「股票基金」），需要時可自行切分。

**曆年回報的年份不寫死**：解析時從頁面子標題讀出實際年份，欄位名與輸出順序
隨之產生（`metadata.json` 的 `calendar_years` 會記錄）。年份往前推時程式不用改。

### 費用欄位：原文 + 數值

平台的費用欄位有三種寫法，不能當成純數字。每個費用都輸出成一對欄位：

| 平台原文 | `*_raw` | `*_pct` |
|---|---|---|
| `0.96` | `0.96` | `0.96` |
| `最高 1.205` | `最高 1.205` | `1.205`（取 X） |
| `0.84 - 0.96` | `0.84 - 0.96` | `0.96`（區間取上限） |
| `n.a.` | `null` | `null` |

原文一律保留，供人工核對與下游自行重新解讀；數值供計算使用。
出現看不懂的寫法時，原文保留、數值留空，並在驗證報告報 WARN，**不猜測**。

真實資料的寫法分布（451 筆）：

| 欄位 | 純數字 | 最高 X | 區間 |
|---|---|---|---|
| 基金管理費 | 264 | 170 | 17 |
| 受託人費／保管人費 | 301 | 135 | 15 |
| 積金易平台費 | 451 | 0 | 0 |
| 成員服務費 | 432 | 18 | 1 |
| 投資管理費 | 362 | 70 | 19 |
| 保證費 | 451 | 0 | 0 |

### 空值約定（重要）

平台上大量欄位顯示 `n.a.`。本專案**一律將其視為空值，絕不轉成 0**：
CSV 輸出空字串，JSON 輸出 `null`。真實的 `0.00`（例如強積金保守基金的回報、
多數基金的保證費）會原樣保留為 `0.0`。

`mpfa/normalize.py` 的 `NA_TOKENS` 列出所有被視為「無資料」的寫法，刻意不包含 `0`。
驗證階段還會反向檢查：若某個數值欄位的 `0` 值比例異常高（>30%），
會判定為「疑似把 n.a. 轉成了 0」並報出來（費用欄位本就多為 0，已排除）。

### 原文保真

文字欄位**只壓縮空白，不做 NFKC 正規化**，因為 NFKC 會把全角標點改寫成半角
（如「景順環球債券基金－單位類別H」的「－」變成「-」），那等於篡改平台原文。
NFKC 只用於欄位標題比對與空值偵測，不會寫進輸出。

---

## 解析設計

### 為什麼基金資訊表需要專用解析器

`mpp_list.jsp` 的表頭橫跨三列（分組標題 + 主標題用 `rowspan` + 期間子標題），
而且表頭與資料列的 `colspan` 並不一致 —— 把表格展開成矩形網格後兩者對不齊
（實測表頭 59/88 欄、資料列 92 欄）。所以通用的「表頭文字驅動」解析不適用。

`mpfa/mpp_html.py` 改用兩個穩定訊號，仍然**不寫死欄位位置**：

1. **資料格的 CSS class** —— 平台用 `arCol`（年率化）、`crCol`（累積）、
   `cyrCol`（曆年）標記三組回報欄，頁面上以 radio 切換顯示。
2. **表頭文字的順序** —— 非回報欄位依主標題（加上分項子標題）的出現順序，
   對應到資料列中「扣掉回報欄、且並非整表皆空」的欄位。

篩選器、註釋、提示在頁面上也是表格；解析時選的是「表頭能辨識出至少 5 個
已知欄位名、且資料列最多」的那一張，這些自然被跳過。

欄位數量對不上時直接拋 `MppStructureError` 並印出實際索引與表頭文字，
**不做猜測性映射** —— 寧可失敗，也不要產出錯位的資料。

欄位名稱改動時，只需在 `mpfa/fields.py` 的 `ALIASES` 補別名，解析層不用動。

### 抓取禮儀（模式 A）

- 固定 User-Agent
- 請求之間強制延遲（預設 1.5 秒 + 隨機抖動），**單執行緒、不併發**
- 5xx / 429 / 連線錯誤才重試，指數退避（2s, 4s, 8s, 16s）
- 4xx（含 403）**不重試**，直接中止並回報，不嘗試繞過

---

## 驗證

每次抓取後自動執行（`mpfa/validate.py`）。狀態分 `PASS` / `WARN` / `FAIL` / `INFO`；
只有 `FAIL` 會讓 `all_passed` 變 false 並使結束碼為 1，`WARN` 會在報告結尾單獨列出。

1. **行數區間** —— 總行數落在 **380–470** 算通過（已核實的實際值 451）；超出範圍報
   `WARN` 並印出實際值與偏離量。計劃數預期約 24（±10%），偏離報 `WARN`。
   受託人數與去重後的基金類別數作 `INFO` 輸出。
2. **空值比例** —— 列出每個欄位的已填／空值／空值率；`fer_pct` 空值率上限 20%、
   `risk_level` 上限 10%，超過報 `FAIL`（代表解析可能錯欄）。
3. **風險級別範圍** —— 必須是 1–7 的整數，超出範圍報 `FAIL` 並逐筆列出。
4. **隨機抽樣 5 隻基金** —— 輸出完整欄位對照，供與網頁逐項人工核對
   （固定亂數種子，結果可重現）。
5. **`n.a.` 未被當成 0** —— 偵測數值欄位的 0 值是否異常集中。
6. **費用欄位解析** —— 有原文卻解析不出數值時報 `WARN` 並列出原文。

門檻定義在 `mpfa/validate.py` 頂部（`MIN_FUND_ROWS`、`MAX_FUND_ROWS`、
`EXPECTED_SCHEMES`、`MAX_NULL_RATIO`），平台數字變動時在該處調整。

### 頁面計數器與表格不一致：以表格為準

`mpp_list.jsp` 的頁面文字寫著「已選擇的成分基金總數: **382**」，但同一頁的資料表
`#scrolltable` 實際列出 **451** 列基金。**經核實，以表格的 451 列為準** ——
頁面計數器與表格不一致屬頁面自身的問題，不是解析漏抓或多抓。

核實依據：

- 不是重複列 —— 451 個 `(計劃, 成分基金)` 組合全部唯一
- 不是隱藏列 —— 沒有任何資料列帶 `display:none`，`class="wr"` 正好 451 個
- 不是客戶端篩選 —— 頁面沒有任何操作資料列顯示狀態的 JS
- 不是分頁 —— 頁面沒有分頁參數
- 不是篩選器狀態 —— 篩選器沒有任何選中項（只有回報視圖的 radio）
- 試過的子集都不等於 382：去重基金名稱 395、排除預設投資策略 395、
  排除強積金保守基金 410、FER 非空 446、排除保證基金 442、
  去掉「單位類別」後去重 438
- 451 列資料內部一致 —— 已用結構不變量全量驗證通過（見下）

因此行數區間設為 **380–470**（涵蓋 451），此項不再報警告。
頁面計數器的值記錄在 `mpfa/validate.py` 的 `PAGE_REPORTED_TOTAL`
與 `data/metadata.json` 的 `page_reported_total`，僅作參考，不用於判定。

### 結構不變量（已全量通過）

除了上面的檢查，還用數學關係反向驗證欄位映射是否正確 —— 若欄位錯位，
這些關係會大面積破裂：

| 不變量 | 檢查筆數 | 不符 |
|---|---|---|
| 一年期：累積回報 == 年率化回報（定義上相同） | 447 | 0 |
| 五年期：`(1+年率化)^5 - 1 == 累積` | 427 | 0 |
| 十年期：`(1+年率化)^10 - 1 == 累積` | 358 | 0 |
| 推出至今：`(1+年率化)^年數 - 1 == 累積`（年數由推出日期算） | 447 | 0 |
| 風險級別 ∈ 1..7 且為整數 | 439 | 0 |
| FER ∈ [0,6]、各費用與基金規模在合理範圍 | 451 | 0 |

另外：費用分項之和等於基金管理費的有 408/451（90%）—— 頁面已註明
「因收費豁免或費用回扣，分項之和未必等於基金管理費」，故僅作觀察，不列為檢查。

---

## 資料來源

| 來源 | 用途 | 狀態 |
|---|---|---|
| `https://mfp.mpfa.org.hk/tch/mpp_list.jsp` | 基金資訊表（繁體中文版），主要來源 | 域名未放行；目前用手動存下的網頁 |
| `https://mfp.mpfa.org.hk/tch/mpp_download_*.jsp` | 站內下載端點，若可用則優先使用 | 待探查 |
| `https://data.gov.hk`（積金局開放資料） | 僅有**彙總統計**，無基金層面欄位 | 域名未放行 |
| [`lotused-ai/mpfa-open-data`](https://github.com/lotused-ai/mpfa-open-data) | 參考鏡像；內容為 7 個彙總統計集 | 可讀取，但**不含**所需欄位 |

### 關於鏡像倉庫

`lotused-ai/mpfa-open-data` 鏡像的是 data.gov.hk 上積金局的七個**彙總統計**資料集。
即使最接近的「核准成分基金淨資產值」，粒度也是按季度 × 7 個基金種類的合計：

```
季度,股票基金,混合資產基金,債券基金,保證基金,強積金保守基金,...,總淨資產值
31-03-2020,331407,306526,41458,75775,108210,4406,867781
```

它**無法**提供受託人、基金名稱、FER、風險級別、各期回報等基金層面欄位。
可作交叉核對的參考，不能作為資料來源。

---

## 網路阻擋

本雲端工作階段的出口代理在 CONNECT 階段拒絕了下列主機（HTTP 403，
與 User-Agent 或站點反爬蟲無關）：`mfp.mpfa.org.hk`、`www.mpfa.org.hk`、
`data.gov.hk`、`api.data.gov.hk`。

**若要啟用模式 A**：於工作階段標題列的雲端環境選單 → Edit → Network access，
把上述主機加入 Allowed domains（保留 Allow package managers 勾選），
或改用更寬鬆的存取層級。
說明：https://code.claude.com/docs/en/cloud-environments#network-access

程式遇到此情況時會拋出 `BlockedError`、以結束碼 `3` 中止並提示改用模式 B，
**不會嘗試繞過**，也不會以假資料填補。

模式 B 不是權宜之計 —— 兩種模式共用同一條清洗／驗證／輸出流水線，
產出的檔案與驗證報告完全一致。

---

## 專案結構

```
mpfa/
  fields.py      欄位定義與繁中↔英文映射、標題別名（曆年年份動態產生）
  normalize.py   標題比對、n.a. 處理、數值/日期正規化、費用三種寫法解析
  mpp_html.py    mpp_list.jsp 基金資訊表專用解析器（class + 表頭順序驅動）
  parse.py       通用表格解析（HTML / CSV / XLSX / XLS）、檔案類型判斷
  sources.py     可插拔來源：NetworkSource（模式 A）、LocalSource（模式 B）
  fetch.py       有禮貌的 HTTP 層（UA、延遲、退避重試、阻擋偵測）
  probe.py       模式 A 的端點探查
  validate.py    驗證與報告格式化（PASS/WARN/FAIL/INFO）
  pipeline.py    流程編排與 CSV/JSON/metadata 輸出
scripts/
  scrape_mpfa_funds.py   CLI 入口
  make_sample_raw.py     產生合成樣例基金資訊表 HTML
  gen_field_doc.py       由 fields.py 重新產生 docs/FIELDS.md
tests/
  test_offline.py        單元測試
  test_mpp_html.py       HTML 解析器測試（含真實頁面）
  test_local_pipeline.py 模式 B 端到端測試
data/raw/README.md       原始檔投放目錄說明
docs/FIELDS.md           欄位映射表（產生檔）
```

## 資料使用聲明

資料來源為香港強制性公積金計劃管理局（積金局）。使用前請參閱積金局網站的
使用條款與資料定義。本倉庫僅作資料抓取與整理，不對資料正確性作保證。
