# `data/raw/` — 原始檔投放目錄（模式 B）

把從強積金基金平台取得的原始檔放進這個目錄，然後執行：

```bash
python scripts/scrape_mpfa_funds.py --mode local
```

## 主要用法：存下 mpp_list.jsp 網頁

平台的基金資訊表是伺服器端渲染的 HTML 表格。在瀏覽器開啟
<https://mfp.mpfa.org.hk/tch/mpp_list.jsp>，用「另存網頁」存成 HTML
（只存 HTML 就夠，不需要圖片與 CSS），放進本目錄即可。

目前倉庫內的 `mpp_list.html` 即為此方式取得（資料截至 2026-09-30）。

程式會自動辨識這是基金資訊表，改用 `mpfa/mpp_html.py` 的專用解析器
（表頭橫跨三列，通用解析對不齊），並從頁面讀出：

- 資料截止日期（「最新資料截至…」）
- 平台最後更新日期（「最後更新日期：…」）
- 頁面自報的成分基金總數（「已選擇的成分基金總數: …」，僅記錄，不用於判定）
- 曆年回報的實際年份（年份每年推移，不寫死）

## 也支援的格式

`.csv`、`.xlsx`、`.xlsm`、`.xls`、`.tsv`、`.txt`，以及非基金資訊表的一般 HTML 表格
（走通用的表頭文字驅動解析）。

- `.xls`（舊版 BIFF）需要額外安裝 `xlrd`。
- 目錄會被**遞迴**掃描，可自由分子目錄。
- 以 `.` 或 `~$` 開頭的檔案（暫存檔、Office 鎖定檔）會被略過。

## 不需要在意檔名

檔案是「基金資訊表」還是「月末單位價格」，程式依**內容與表頭文字**自動判斷，
不看檔名。多個檔案會自動合併去重（基金以 計劃+成分基金 為鍵），
所以分次存下的多個頁面全部丟進來即可。

## 資料截止日期

程式依下列順序判定，寫入 `data/metadata.json` 的 `data_as_of_date`：

1. 命令列 `--as-of 2026-09-30`
2. 本目錄下的 `AS_OF.txt`（內容只放一個日期）
3. 頁面內容中的「最新資料截至…」／「資料截至…」字樣
4. 檔名中的日期（如 `mpp_list_2026-09-30.html`）

都找不到時會留 `null` 並在日誌警告，**不會**猜一個日期填進去。

## 解析失敗時

- **表頭無法辨識**：該檔會被跳過並在日誌警告，情況記在
  `data/metadata.json` 的 `input_files`。把平台實際的欄位標題加進
  `mpfa/fields.py` 的 `ALIASES` 即可，解析層不需要改動。
- **欄位數量對不上**：拋 `MppStructureError` 並印出實際欄位索引與表頭文字，
  該檔不產出任何資料。這是刻意的 —— 寧可失敗，也不要產出錯位的資料。

## 關於版本控制

本目錄預設**不納入 git**（見 `.gitignore`），只保留這份說明。
例外是目前的 `mpp_list.html` 已被刻意提交，用於測試與重現
（`tests/test_mpp_html.py` 會對它做斷言）。

## 想先看流水線能不能跑？

不必有真實檔案：

```bash
python scripts/make_sample_raw.py --out-dir /tmp/sample_raw
python scripts/scrape_mpfa_funds.py --mode local --raw-dir /tmp/sample_raw --out-dir /tmp/sample_out
```

樣例是結構鏡像 `mpp_list.jsp` 的合成 HTML（382 隻基金 / 24 個計劃）。
計劃與基金名稱都帶「示例」字樣，**不可當作真實強積金資料**。
