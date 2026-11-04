# 欄位映射表（繁體中文原文 ↔ 英文欄位名）

本檔由 `mpfa/fields.py` 產生，請勿手動編輯；改動請改 `mpfa/fields.py` 後執行
`python scripts/gen_field_doc.py`。

## 基金資訊表 `data/funds_latest.csv` / `.json`

| 英文欄位名 | 繁體中文原文 | 說明 |
|---|---|---|
| `scheme_name` | 計劃 | 強積金計劃名稱 |
| `fund_name` | 成分基金 | 成分基金名稱 |
| `trustee` | 受託人 | 受託人名稱 |
| `fund_category` | 基金類別 | 基金類別（含基金種類前綴，如「股票基金 - 亞洲股票基金」） |
| `launch_date` | 推出日期 | 基金推出日期（ISO 8601） |
| `fund_size_hkd_million` | 基金規模（百萬港元） | 基金規模（百萬港元） |
| `risk_level` | 風險級別 | 風險級別（整數 1-7） |
| `fer_pct` | 最近期基金開支比率 | 最近期基金開支比率 FER（%） |
| `return_1y_annualised` | 年率化回報 一年期 | 一年期年率化回報（% p.a.） |
| `return_5y_annualised` | 年率化回報 五年期 | 五年期年率化回報（% p.a.） |
| `return_10y_annualised` | 年率化回報 十年期 | 十年期年率化回報（% p.a.） |
| `return_since_launch_annualised` | 年率化回報 推出至今 | 推出至今年率化回報（% p.a.） |
| `return_1y_cumulative` | 累積回報 一年期 | 一年期累積回報（%） |
| `return_5y_cumulative` | 累積回報 五年期 | 五年期累積回報（%） |
| `return_10y_cumulative` | 累積回報 十年期 | 十年期累積回報（%） |
| `return_since_launch_cumulative` | 累積回報 推出至今 | 推出至今累積回報（%） |
| `return_cy2025` | 曆年回報 2025 | 2025 曆年回報（%） |
| `return_cy2024` | 曆年回報 2024 | 2024 曆年回報（%） |
| `return_cy2023` | 曆年回報 2023 | 2023 曆年回報（%） |
| `return_cy2022` | 曆年回報 2022 | 2022 曆年回報（%） |
| `return_cy2021` | 曆年回報 2021 | 2021 曆年回報（%） |
| `management_fee_raw` | 基金管理費（原文） | 基金管理費（% p.a.） —— 平台原文，可能是「最高 X」或「X - Y」區間 |
| `management_fee_pct` | 基金管理費（數值） | 基金管理費（% p.a.） —— 解析出的數值：區間取上限、「最高 X」取 X |
| `trustee_custodian_fee_raw` | 受託人費／保管人費（原文） | 基金管理費分項：受託人費／保管人費（% p.a.） —— 平台原文，可能是「最高 X」或「X - Y」區間 |
| `trustee_custodian_fee_pct` | 受託人費／保管人費（數值） | 基金管理費分項：受託人費／保管人費（% p.a.） —— 解析出的數值：區間取上限、「最高 X」取 X |
| `empf_platform_fee_raw` | 積金易平台費（原文） | 基金管理費分項：積金易平台費（% p.a.） —— 平台原文，可能是「最高 X」或「X - Y」區間 |
| `empf_platform_fee_pct` | 積金易平台費（數值） | 基金管理費分項：積金易平台費（% p.a.） —— 解析出的數值：區間取上限、「最高 X」取 X |
| `member_service_fee_raw` | 成員服務費（原文） | 基金管理費分項：成員服務費（% p.a.） —— 平台原文，可能是「最高 X」或「X - Y」區間 |
| `member_service_fee_pct` | 成員服務費（數值） | 基金管理費分項：成員服務費（% p.a.） —— 解析出的數值：區間取上限、「最高 X」取 X |
| `investment_management_fee_raw` | 投資管理費（原文） | 基金管理費分項：投資管理費（% p.a.） —— 平台原文，可能是「最高 X」或「X - Y」區間 |
| `investment_management_fee_pct` | 投資管理費（數值） | 基金管理費分項：投資管理費（% p.a.） —— 解析出的數值：區間取上限、「最高 X」取 X |
| `guarantee_fee_raw` | 保證費（原文） | 保證費（% p.a.） —— 平台原文，可能是「最高 X」或「X - Y」區間 |
| `guarantee_fee_pct` | 保證費（數值） | 保證費（% p.a.） —— 解析出的數值：區間取上限、「最高 X」取 X |

## 月末單位價格 `data/unit_prices_latest.csv` / `.json`

| 英文欄位名 | 繁體中文原文 | 說明 |
|---|---|---|
| `trustee` | 受託人 | 受託人名稱 |
| `scheme_name` | 計劃 | 強積金計劃名稱 |
| `fund_name` | 成分基金 | 成分基金名稱 |
| `price_date` | 日期 | 月末日期（ISO 8601） |
| `unit_price` | 單位價格 | 每單位價格 |
| `currency` | 貨幣 | 計價貨幣 |

## 標題別名

解析時以「欄位標題文字」比對（非欄位位置），因此平台調整欄位順序不會造成錯位。
下列為各欄位可接受的標題寫法；平台若改用新寫法，只需在 `mpfa/fields.py` 的 `ALIASES` 追加。

| 英文欄位名 | 可辨識的標題寫法 |
|---|---|
| `trustee` | 受託人, 受托人, 信託人, trustee |
| `scheme_name` | 計劃, 計劃名稱, 计划名称, 強積金計劃名稱, scheme, schemename, mpfscheme |
| `fund_name` | 成分基金, 基金名稱, 基金名称, 成分基金名稱, constituentfund, fundname |
| `fund_category` | 基金類別, 基金类别, fundcategory, category |
| `fund_type` | 基金種類, 基金种类, fundtype |
| `launch_date` | 推出日期, 成立日期, launchdate, inceptiondate, dateofinception |
| `fund_size_hkd_million` | 基金規模, 基金规模, 基金規模百萬港元, 基金資產淨值, 淨資產值, fundsize, fundsizemillion, netassetvalue, nav |
| `fer_pct` | 最近期基金開支比率, 最近期基金開支比率, 基金開支比率, 基金开支比率, 基金開支比率fer, 開支比率, fer, fundexpenseratio, expenseratio |
| `risk_level` | 風險級別, 风险级别, 風險指標, risklevel, riskindicator, riskclass |
| `return_1y_annualised` | 1年年率化回報, 一年期年率化回報, 1yearannualisedreturn |
| `return_5y_annualised` | 5年年率化回報, 五年期年率化回報, 5yearannualisedreturn |
| `return_10y_annualised` | 10年年率化回報, 十年期年率化回報, 10yearannualisedreturn |
| `return_since_launch_annualised` | 成立以來年率化回報, 推出至今年率化回報, sincelaunchannualisedreturn |
| `return_1y_cumulative` | 1年累積回報, 一年期累積回報, 1yearcumulativereturn |
| `return_5y_cumulative` | 5年累積回報, 五年期累積回報, 5yearcumulativereturn |
| `return_10y_cumulative` | 10年累積回報, 十年期累積回報, 10yearcumulativereturn |
| `return_since_launch_cumulative` | 成立以來累積回報, 推出至今累積回報, sincelaunchcumulativereturn |
| `management_fee_raw` | 基金管理費, 基金管理费, managementfee |
| `trustee_custodian_fee_raw` | 受託人費保管人費, 受託人費／保管人費, 受託人費, 保管人費, trusteecustodianfee, trusteefee |
| `empf_platform_fee_raw` | 積金易平台費, 积金易平台费, empfplatformfee, empffee |
| `member_service_fee_raw` | 成員服務費, 成员服务费, memberservicefee |
| `investment_management_fee_raw` | 投資管理費, 投资管理费, investmentmanagementfee |
| `guarantee_fee_raw` | 保證費, 保证费, guaranteefee |
| `price_date` | 日期, 月末日期, 截至, date, monthenddate, asofdate |
| `unit_price` | 單位價格, 单位价格, 基金單位價格, 每單位價格, unitprice, navperunit |
| `currency` | 貨幣, 货币, 計價貨幣, currency, ccy |
