# `data/raw/` — 模式 B 的原始檔投放目錄

把從強積金基金平台手動下載的檔案放進這個目錄，然後執行：

```bash
python scripts/scrape_mpfa_funds.py --mode local
```

## 支援的格式

`.csv`、`.xlsx`、`.xlsm`、`.xls`、`.html`、`.htm`、`.tsv`、`.txt`

- `.xls`（舊版 BIFF）需要額外安裝 `xlrd`；若平台同時提供 CSV 或 XLSX，建議直接下載那兩種。
- 目錄會被**遞迴**掃描，可自由分子目錄。
- 以 `.` 或 `~$` 開頭的檔案（暫存檔、Office 鎖定檔）會被略過。

## 不需要在意檔名

檔案是「基金資訊表」還是「月末單位價格」，程式依**表頭文字**自動判斷，不看檔名。
多個檔案會自動合併去重（基金以 受託人+計劃名稱+基金名稱 為鍵），
所以平台若把資料分成數頁、數個計劃分別下載，全部丟進來即可。

XLSX 的**每個工作表**都會單獨判斷類型，所以一個檔案裡同時放兩種表也沒問題。

## 資料截止日期

程式依下列順序判定，寫入 `data/metadata.json` 的 `data_as_of_date`：

1. 命令列 `--as-of 2026-03-31`
2. 本目錄下的 `AS_OF.txt`（內容只放一個日期，如 `31-03-2026`）
3. 檔名中的日期（如 `fund_info_2026-03-31.csv`、`20260331.xlsx`）
4. 檔案內容中的「資料截至 …」字樣

都找不到時會留 `null` 並在日誌警告，**不會**猜一個日期填進去。

## 表頭對不上怎麼辦

若某個檔案的表頭無法辨識，日誌會警告「表頭無法辨識，已跳過」，
且該檔的情況會記在 `data/metadata.json` 的 `input_files` 裡。
此時把平台實際的欄位標題加進 `mpfa/fields.py` 的 `ALIASES` 即可，
解析層不需要改動。

## 關於版本控制

本目錄的資料檔**不納入 git**（見 `.gitignore`），只保留這份說明。
原始下載檔可能很大，且屬於平台資料而非本專案程式碼。

## 想先看流水線能不能跑？

不必等真實檔案，可以用合成樣例資料驗證：

```bash
python scripts/make_sample_raw.py --out-dir /tmp/sample_raw
python scripts/scrape_mpfa_funds.py --mode local --raw-dir /tmp/sample_raw --out-dir /tmp/sample_out
```

那份合成資料有 451 隻基金、24 個計劃，刻意包含大量 `n.a.`、括號負數與前導列，
受託人與基金名稱都帶「示例」字樣，**不可當作真實強積金資料**。
