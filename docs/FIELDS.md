# 欄位映射表（繁體中文原文 ↔ 英文欄位名）

本檔由 `mpfa/fields.py` 產生，請勿手動編輯；改動請改 `mpfa/fields.py` 後執行
`python scripts/gen_field_doc.py`。

## 基金資訊表 `data/funds_latest.csv` / `.json`

| 英文欄位名 | 繁體中文原文 | 說明 |
|---|---|---|
| `trustee` | 受託人 | 受託人（信託人）名稱 |
| `scheme_name` | 計劃名稱 | 強積金計劃名稱 |
| `fund_name` | 基金名稱 | 成分基金名稱 |
| `fund_category` | 基金類別 | 基金類別（平台分類，約 451 項） |
| `fund_type` | 基金種類 | 基金種類（股票/混合資產/債券/保證/保守等） |
| `launch_date` | 成立日期 | 基金成立日期（ISO 8601） |
| `fund_size_hkd_million` | 基金規模 | 基金規模（百萬港元） |
| `fer_pct` | 基金開支比率 | 基金開支比率 FER（%） |
| `risk_level` | 風險級別 | 風險級別（整數 1-7） |
| `return_1y_annualised` | 1年年率化回報 | 1 年年率化回報（%） |
| `return_5y_annualised` | 5年年率化回報 | 5 年年率化回報（%） |
| `return_10y_annualised` | 10年年率化回報 | 10 年年率化回報（%） |
| `return_since_launch_annualised` | 成立以來年率化回報 | 成立以來年率化回報（%） |
| `return_1y_cumulative` | 1年累積回報 | 1 年累積回報（%） |
| `return_5y_cumulative` | 5年累積回報 | 5 年累積回報（%） |
| `return_10y_cumulative` | 10年累積回報 | 10 年累積回報（%） |
| `return_since_launch_cumulative` | 成立以來累積回報 | 成立以來累積回報（%） |

## 月末單位價格 `data/unit_prices_latest.csv` / `.json`

| 英文欄位名 | 繁體中文原文 | 說明 |
|---|---|---|
| `trustee` | 受託人 | 受託人名稱 |
| `scheme_name` | 計劃名稱 | 強積金計劃名稱 |
| `fund_name` | 基金名稱 | 成分基金名稱 |
| `price_date` | 日期 | 月末日期（ISO 8601） |
| `unit_price` | 單位價格 | 每單位價格 |
| `currency` | 貨幣 | 計價貨幣 |

## 標題別名

解析時以「欄位標題文字」比對（非欄位位置），因此平台調整欄位順序不會造成錯位。
下列為各欄位可接受的標題寫法；平台若改用新寫法，只需在 `mpfa/fields.py` 的 `ALIASES` 追加。

| 英文欄位名 | 可辨識的標題寫法 |
|---|---|
| `trustee` | 受託人, 受托人, 信託人, trustee |
| `scheme_name` | 計劃名稱, 计划名称, 強積金計劃名稱, 計劃, scheme, schemename, mpfscheme |
| `fund_name` | 基金名稱, 基金名称, 成分基金名稱, 成分基金, constituentfund, fundname |
| `fund_category` | 基金類別, 基金类别, fundcategory, category |
| `fund_type` | 基金種類, 基金种类, fundtype, type |
| `launch_date` | 成立日期, 推出日期, launchdate, inceptiondate, dateofinception |
| `fund_size_hkd_million` | 基金規模, 基金规模, 基金規模百萬港元, 基金資產淨值, 淨資產值, fundsize, fundsizemillion, netassetvalue, nav |
| `fer_pct` | 基金開支比率, 基金开支比率, 基金開支比率fer, 開支比率, fer, fundexpenseratio, expenseratio |
| `risk_level` | 風險級別, 风险级别, 風險指標, risklevel, riskindicator, riskclass |
| `return_1y_annualised` | 1年年率化回報, 1年年化回報, 一年年率化回報, 1yearannualisedreturn, 1yearannualizedreturn |
| `return_5y_annualised` | 5年年率化回報, 5年年化回報, 五年年率化回報, 5yearannualisedreturn, 5yearannualizedreturn |
| `return_10y_annualised` | 10年年率化回報, 10年年化回報, 十年年率化回報, 10yearannualisedreturn, 10yearannualizedreturn |
| `return_since_launch_annualised` | 成立以來年率化回報, 成立以來年化回報, 自成立以來年率化回報, sincelaunchannualisedreturn, sinceinceptionannualisedreturn |
| `return_1y_cumulative` | 1年累積回報, 1年累计回报, 一年累積回報, 1yearcumulativereturn |
| `return_5y_cumulative` | 5年累積回報, 5年累计回报, 五年累積回報, 5yearcumulativereturn |
| `return_10y_cumulative` | 10年累積回報, 10年累计回报, 十年累積回報, 10yearcumulativereturn |
| `return_since_launch_cumulative` | 成立以來累積回報, 自成立以來累積回報, sincelaunchcumulativereturn, sinceinceptioncumulativereturn |
| `price_date` | 日期, 月末日期, 截至, date, monthenddate, asofdate |
| `unit_price` | 單位價格, 单位价格, 基金單位價格, 每單位價格, unitprice, navperunit |
| `currency` | 貨幣, 货币, 計價貨幣, currency, ccy |
