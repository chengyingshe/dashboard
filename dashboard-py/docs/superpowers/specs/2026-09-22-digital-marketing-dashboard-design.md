# Digital Marketing Dashboard Design

> **历史文档**：本规格写于 2026-09-22，其中的指标定义已被 `数据口径.xlsx` Sheet1 取代。
> 取数方式、生命周期集合、漏斗层级一律以 AGENTS.md「业务指标口径」一节为准；本文档仅保留
> 视觉与页面结构的设计意图。差异要点：COUNT 全部按行计数、来源按 Organic/Paid 前缀匹配、
> All Revenue 求和不再限定 Closed Won、漏斗第 5 层由 Deals 改为 Customers。

## 1. Goal

Build a local Plotly Dash application that provides a daily digital marketing performance dashboard. The visual direction follows the supplied reference image: a dark blue header, KPI cards, funnel diagnostics, trend charts, source contribution charts, paid media efficiency, and regional performance diagnosis.

The dashboard uses CSV files from a configurable upload folder. It identifies each source table from its column names rather than relying on filenames.

## 2. Scope

### Included in the first version

- Local Plotly Dash application.
- English UI.
- Daily aggregation.
- Default date range: latest 30 available days.
- Date range filter.
- Multi-select region filter.
- Automatic recursive discovery of CSV files in a configured folder.
- Column-based table identification and validation.
- KPI cards, overall funnel, paid funnel, daily conversion trends, source contribution, paid media efficiency, and regional heatmap diagnosis.
- Empty states and actionable data-quality errors.
- Unit tests for file recognition and metric calculations.

### Excluded from the first version

- Database persistence.
- Authentication or multi-user access.
- Scheduled refresh.
- Mobile-first layout.
- Global channel filter.
- Cross-table entity deduplication, because the supplied tables do not expose a reliable shared contact/deal key.

## 3. Data Ingestion

The application receives a configurable folder path. At startup it recursively scans all `.csv` files below that path.

### Table identification

Identification is based on required column sets:

- Traffic: `Session default channel group`, `Sessions`, and `Date`.
- Leads: `Lifecycle Stage`, `Original Traffic Source`, `Create Date`, and `Record ID`.
- Deals: `Deal Stage`, `Amount`, `Close Date`, and `Record ID`.
- Regional ad cost: `Currency code`, `Cost`, `Day`, and a region column.
- Account-level ad cost: `Currency code`, `Cost`, `Day`, and `Account name`, without a region column.

Filenames are retained for diagnostics only and are not used for business classification.

### Cleaning rules

- Parse all dates to calendar-day granularity. Datetimes are truncated to their date.
- Exclude rows with unparseable dates from time-series metrics and report the excluded count.
- Remove Traffic summary rows such as `Grand total` from detail calculations.
- Normalize numeric fields using tolerant parsing and report invalid-row counts.
- Normalize source matching as case-insensitive substring matching:
  - contains `Organic` -> Organic
  - contains `Paid` -> Paid
- Map `Account name` to region for account-level advertising cost tables.
- Add a `source_file` field to normalized records for diagnostics.
- Merge multiple files of the same recognized type only when their normalized schemas are compatible. Conflicting schemas stop that table from participating in calculations and show an error.

## 4. Metric Definitions

All metrics are recalculated for the active date and region filters.

- Organic Traffic = sum of Traffic `Sessions` where channel group contains `Organic`.
- All Traffic = sum of Traffic `Sessions`.
- All Leads = count of valid Leads `Record ID`, following the workbook note that all records are counted directly.
- All MQLs = count of Leads records whose lifecycle is `Marketing Qualified Lead`, `Sales Qualified Lead`, or `Customer`.
- All SQLs = count of Leads records whose lifecycle is `Sales Qualified Lead` or `Customer`.
- All Revenue = sum of Deal `Amount` where Deal Stage is `Closed Won`.
- Ad Spend = sum of regional and account-level ad cost `Cost` values. Display currency is USD.
- Paid Traffic = sum of Traffic `Sessions` where channel group contains `Paid`.
- Paid Leads = count of Leads records whose lifecycle is `Lead` and source contains `Paid`.
- Paid MQLs = count of Leads records whose lifecycle is `Marketing Qualified Lead` and source contains `Paid`.
- Paid SQLs = count of Leads records whose lifecycle is `Sales Qualified Lead` and source contains `Paid`.
- Paid Deals = count of Deals records whose Deal Stage is `Closed Won` and source contains `Paid`.
- Paid Revenue = sum of Deal `Amount` where Deal Stage is `Closed Won` and source contains `Paid`.
- Cost per Lead = Ad Spend / Paid Leads.
- Cost per MQL = Ad Spend / Paid MQLs.
- ROAS = Paid Revenue / Ad Spend.

Adjacent funnel conversion rates are calculated as the next stage divided by the previous stage. The overall funnel is Traffic -> Leads -> MQLs -> SQLs -> Deals -> Revenue. The paid funnel is Paid Traffic -> Paid Leads -> Paid MQLs -> Paid SQLs -> Paid Deals -> Paid Revenue.

Day-over-day change is `(current day - previous day) / previous day`. If the previous value is missing or zero, the result is `N/A`.

Target values from the workbook are retained as configurable reference values. Because the workbook target years do not align consistently with the supplied 2026 data, the UI labels them `Target Reference` rather than presenting them as current-year commitments.

## 5. Page Layout

### Header and filters

- Dark blue header with `Digital Marketing KPI Dashboard` and `Daily performance overview`.
- Date range selector with shortcuts: `Last 7 Days`, `Last 30 Days`, and `All Available Dates`.
- Multi-select Region selector with `All Regions` as the default.
- Data-status indicator showing loaded file count, recognized table types, and refresh timestamp.

### Dashboard sections

1. KPI cards: Organic Traffic, All Traffic, All Leads, All MQLs, All SQLs, and All Revenue.
2. Funnel diagnosis: overall funnel, paid funnel, and daily conversion-rate trend.
3. Channel contribution: source-share donut charts for Traffic, Leads, and MQLs. Small sources may be grouped under `Other`.
4. Paid media efficiency: Ad Spend, Cost per Lead, Cost per MQL, ROAS, and daily spend versus paid revenue.
5. Performance diagnosis: region-by-day conversion heatmap and a data-backed key-finding panel.

All charts and cards update when Date Range or Region changes. Plotly hover labels include date, region, metric, and value.

## 6. Error Handling

- Missing folder or no CSV files: show `No CSV files found`.
- Unreadable CSV: show filename, ingestion stage, and parser error.
- Missing required columns: show the file and missing columns.
- Excessive invalid numeric/date rows: prevent that table from contributing to metrics and show the invalid-row count.
- Zero denominator: show `N/A`, never infinity or a misleading zero.
- No data in the selected range: preserve filters and show an empty state.
- Conflicting files of one table type: report the conflict and do not silently overwrite data.

## 7. Project Structure

```text
dashboard-py/
├── app.py
├── config.py
├── data_loader.py
├── metrics.py
├── layout.py
├── charts.py
├── styles.css
├── tests/
│   ├── test_data_loader.py
│   └── test_metrics.py
└── requirements.txt
```

The data folder path is configurable in `config.py` and may also be supplied as a startup argument. The existing `数据底表V1` folder is the default local example path.

## 8. Verification Criteria

- The app starts locally and serves a browser page.
- The supplied CSV folder is discovered without relying on filenames.
- Each provided table is recognized by columns and normalized successfully, or produces a clear diagnostic.
- Metric unit tests cover the main KPI, paid KPI, funnel, efficiency, and day-over-day calculations.
- Date and Region filters update every dependent card and chart.
- Empty, invalid, and zero-denominator states are visible and do not produce misleading values.
- A desktop screenshot at 1280px or wider confirms the header, filters, KPI row, and major chart sections render without overlap.

## 9. Known Assumptions

- `Closed Won` is the valid deal stage for deal count and revenue.
- Regional and account-level advertising cost files can be combined after region normalization.
- Source classification is keyword-based and case-insensitive.
- The supplied exports are not deduplicated across tables.
- The first version is optimized for desktop use.
