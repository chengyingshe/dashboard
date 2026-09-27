# 指标计算口径审计报告

审计对象：`dashboard-py` 全部指标与图表
审计日期：2026-09-27
验证环境：`dashboard-py/.venv/Scripts/python.exe -m pytest -q`
验证窗口：默认最近 30 天，即 **2026-08-23 ~ 2026-09-21**（max_date 由 leads 表决定）

> **状态：A1/A2/A3 与 B4/B5/B6 已修复，C7/C8/C9/C10 已修复，测试从 7 passed 增至 15 passed。**
> 修复过程中另外发现并修掉一个隐藏更深的日期解析缺陷（见 A4）。剩余未决项只有数据源问题（第 5 节），需要业务确认。
> 付费漏斗按「统一为集合口径」处理，广告地区按「配置化账户→国家映射」处理。

> **后续更新（同日）：口径已被 `数据口径.xlsx` Sheet1 覆盖。** 业务方重新定义了全部 COUNT 指标的取数方式，
> 本文档第 2~4 节的「正确值」仅作历史留档，实际口径以 AGENTS.md「业务指标口径」一节为准。主要变化：
> 所有 COUNT 改为**按行计数**（不再按 Email 去重）；All Leads 增加生命周期过滤（排除 Subscriber 与空值）；
> 新增 All Customers；All Revenue 去掉 Closed Won 限制；Paid Leads 改用 `LEAD_STAGES` 集合；
> Paid Deals 改从 Leads 表取（付费来源且生命周期为 Customer）；漏斗第 5 层统一为 Customers。

---

## 1. 计算管线总览

所有指标走同一条链路，任何一环出错都会同时污染 KPI、漏斗、趋势、占比和热力图：

```
CSV → _standardize（清洗/归类） → DataBundle
     → _selected（日期区间 + 地区筛选）
     → compute_kpis / compute_daily_trends / compute_source_share / compute_region_heatmap
     → make_*_figure → callback 输出
```

两个全局入口决定了所有指标的口径：

- **`_selected(frame, date_range, regions)`**（metrics.py:20）：`date.between(start, end)` + `region.isin(regions)`，地区为空表示全部。
- **`_count_records(frame, mask)`**（metrics.py:35）：`record_id.nunique()`，**这是所有线索类指标的计数基元**。

---

## 2. 逐指标说明

### 2.1 KPI 卡片（10 个）

| 指标 | 实现位置 | 计算方式 | 结论 |
|---|---|---|---|
| Organic Traffic | metrics.py:75 | traffic 中 `source_class == organic` 的 sessions 求和 | ✅ 正确 |
| All Traffic | metrics.py:76 | traffic sessions 全量求和 | ✅ 正确 |
| All Leads | metrics.py:77 | `leads.record_id.nunique()` | ❌ 主键损坏，严重低估 |
| All MQLs | metrics.py:50 | lifecycle ∈ {MQL, SQL, Customer} 的 record_id 去重数 | ❌ 同上 |
| All SQLs | metrics.py:51 | lifecycle ∈ {SQL, Customer} 的 record_id 去重数 | ❌ 同上 |
| All Revenue | metrics.py:72 | deals 中 `deal_stage.casefold() == "closed won"` 的 amount 求和 | ✅ 正确（Deal.csv 主键有效） |
| Ad Spend | metrics.py:71 | ad_cost 的 cost 全量求和 | ⚠️ 数值正确，但地区筛选后会归零（见 B4） |
| Cost per Lead | metrics.py:89 | `ad_spend / paid_leads` | ❌ 分母错误 |
| Cost per MQL | metrics.py:90 | `ad_spend / paid_mqls` | ❌ 分母错误 |
| ROAS | metrics.py:91 | `paid_revenue / ad_spend` | ⚠️ 算式正确，但 paid_revenue 与 paid_leads 不同源 |

### 2.2 漏斗（Overall / Paid）

`compute_funnel`（metrics.py:95）从 `compute_kpis` 的返回字典里按 `f"{prefix}traffic"` 等键取值，再逐级算转化率。

- Overall：`prefix = ""` → 取 `traffic / leads / mqls / sqls / deals / revenue`
- Paid：`prefix = "paid_"` → 取 `paid_traffic / paid_leads / ...`

**KPI 字典的实际键名是 `all_traffic / all_leads / all_mqls / all_sqls / all_deals / all_revenue`**，Overall 分支的键全部匹配不上，`kpi.get(key, 0)` 一律返回 0。

### 2.3 日趋势（Conversion Rate Trend / Spend vs Revenue）

`compute_daily_trends`（metrics.py:105）：

1. 用 `pd.date_range(start, end, freq="D")` 生成**午夜日历网格**；
2. 各表 `groupby("date")` 后 `merge` 到该网格；
3. 补齐缺失列为 0，再算 4 条转化率：`leads/traffic`、`mqls/leads`、`sqls/mqls`、`deals/sqls`。

traffic 与 ad_cost 的日期是纯日期（午夜），能对齐；**leads 与 deals 的日期带时分秒**，groupby 出来的索引是时间戳，与日历网格几乎不可能相等 → 合并后全为 NaN → 被 `fillna(0)` 抹平。

### 2.4 来源占比（Traffic / Leads / MQLs 三个环图）

`compute_source_share`（metrics.py:149）按 `source` 分组：

- traffic → `sessions.sum()`
- leads / mqls → `record_id.nunique()`

环图中心显示总量（取 `all_traffic / all_leads / all_mqls`）。因主键去重失效，会出现"各扇区之和 > 中心总量"的自相矛盾。

### 2.5 地区热力图（MQL Conversion by Region）

`compute_region_heatmap`（metrics.py:160）按 `(region, date)` 分组，算 `MQL 数 / Leads 数`，再 `pivot` 成矩阵。受日期时间分量影响，`date` 维度退化为"每个不同时间戳一列"。

### 2.6 环比（vs prior day）

app.py:51：取趋势表最小日期减一天作为 prior day，再单独算一次单日 KPI，与当前值比。

---

## 3. 实测对照（默认窗口 2026-08-23 ~ 2026-09-21）

| 指标 | 当前页面显示 | 独立复算（正确口径） | 偏差 |
|---|---|---|---|
| Organic Traffic | 84,532 | 84,532 | 一致 |
| All Traffic | 139,660 | 139,660 | 一致 |
| All Leads | **30** | **1,085** | -97.2% |
| All MQLs | **17** | **338** | -95.0% |
| All SQLs | **12** | **144** | -91.7% |
| All Revenue | 122,994 | 122,994 | 一致 |
| Ad Spend | 26,537.92 | 26,537.92 | 一致 |
| Cost per Lead | **2,211.49** | **83.45** | 26.5 倍 |
| Cost per MQL | **2,653.79** | **257.65** | 10.3 倍 |
| ROAS | 1.00 | 1.00 | 一致 |
| Overall Funnel | **全 0** | Traffic 139,660 → … → Revenue 122,994 | 完全失效 |
| 趋势图 all_leads 合计 | **2** | 1,085 | 失效 |
| 趋势图 all_deals / all_revenue | **0 / 0** | 11 / 122,994 | 失效 |
| 热力图 | **920 行 × 898 个日期列** | 47 地区 × 30 天 | 失效 |
| Leads 来源占比 | 各扇区之和 **68** | 应等于中心 1,085 | 自相矛盾 |

---

## 4. 缺陷清单

### P0 — 指标错误，必须修

**A1. leads 主键损坏（影响面最大）**

`leads.csv` 的 `Record ID` 被 Excel 存成了科学计数法文本（如 `2.05E+11`，原值 205000000000），精度丢失：**7,128 行只有 102 个不同 ID**，最大的一组 720 行共用一个 ID。pandas 再把它读成 float，`astype(str)` 后变成 `205000000000.0`。

受影响：All Leads / All MQLs / All SQLs / Paid Leads / Paid MQLs / Paid SQLs / Cost per Lead / Cost per MQL / 趋势的 leads·mqls·sqls / 热力图 / Leads 与 MQLs 来源占比。

修复建议：以 **Email 作为 leads 去重键**（窗口内 1,085 行对应 1,085 个独立邮箱，无空值，可安全替代）。即使把 `Record ID` 改成 `dtype=str` 也救不回精度，因为源文件本身已经丢精度。需与业务确认"一个邮箱 = 一个 Lead"。

**A2. 日期时间分量导致边界与分组错误**

`Create Date` 7,122/7,127 条带时分秒，`Close Date` 117/117 条带时分秒。

- `_selected` 的 end 边界是当日 00:00 → **区间最后一天的 leads 与 deals 整日丢失**（实测 2026-09-20 的 19 条 leads 命中 0 条）；
- `compute_daily_trends` 的 `groupby("date")` 用原始时间戳，与午夜日历网格对不上 → 趋势图基本全 0；
- 热力图 `(region, date)` 分组 → 898 个日期列。

修复建议：在 `_standardize` 里对 leads/deals 的 `date` 做 `.dt.normalize()`，最稳妥；同时把 `_selected` 的区间改成 `>= start & < end + 1 天`。改动小、收益最大，建议优先做。

**A3. Overall Funnel 键名拼接错误**

`prefix = ""` 时拼出 `traffic / leads / mqls / sqls / deals / revenue`，而 KPI 实际键是 `all_*`，全部落到默认值 0 → Overall Funnel 六个节点全 0（图表虽不报错，但完全无信息）。

修复建议：把 Overall 分支改成 `all_`，并注意 traffic 的键是 `all_traffic` 而非 `all_traffic` 之外的形式。

### P1 — 口径不一致，会误导判断

**B4. 地区维度不是同一套枚举**

ad_cost 表的 `region` 实际是**广告账户名**：`Hytera Mexico / Hytera LATAM South / Hytera Brazil / Hytera LATAM North / Canada`；而 traffic / leads / deals 的 `region` 是**国家名**（Brazil、Mexico、Colombia…）。地区下拉 248 个选项把两套混在一起。

后果：选中 `Brazil` → ad_cost 被筛空 → Ad Spend = 0 → Cost per Lead / Cost per MQL / ROAS 全部显示 N/A；选中 `Hytera Brazil` → traffic/leads/deals 被筛空。

修复建议：建立"广告账户 → 国家/大区"映射表（配置化，写进 config 或单独 CSV），或明确 ad_cost 不参与地区筛选并在页面标注。

**B5. 环比口径不成立**

current 是**整个区间**的聚合值，prior 是**区间起始日前一天**的单日值，两者不可比。实测：Organic Traffic "+3567.3%"、All Traffic "+3893.7%"、Ad Spend "+2885.4%"。

修复建议：改为等长前移区间（previous period：前 30 天 vs 最近 30 天）；仅当区间为单日时才用"前一日"。

**B6. 付费漏斗内部口径不自洽**

- `all_mqls` 用集合口径 `{MQL, SQL, Customer}`，`paid_mqls` 却用等值 `stage == "Marketing Qualified Lead"`；
- `paid_leads` 只算 `stage == "Lead"`，而 `all_leads` 不限制生命周期（Subscriber 2,266 条、空值 339 条都算进 all_leads）。

后果：出现 MQL(6) < SQL(7) 这类漏斗倒置，且付费转化率与整体转化率不可比。

修复建议：统一为同一套口径（推荐都用集合口径），并明确 Subscriber 是否计入 Leads。

### P2 — 健壮性与信息缺失

- **C7 死代码**：`compute_region_heatmap` 首行的 `trend = compute_daily_trends(...)` 从未使用；`compute_funnel` 算出的 `conversion` 列也没被漏斗图消费（图上只有绝对值，看不到转化率）。
- **C8 热力图色阶**：`zmin=0, zmax=1` 写死，而 MQL 转化率可能 > 1（实测 1.1667）会被截断显示。
- **C9 leads.csv 编码回退**：utf-8-sig / utf-8 / gb18030 全部解码失败（文件含非法字节），最终以 **latin-1** 读入。目前地区名是 ASCII 看起来正常，但非 ASCII 字段存在乱码风险，建议清洗源文件。
- **C10 币种未校验**：两份 cost 文件当前都是 USD，代码直接相加，没有按 `Currency code` 校验或换算；出现非 USD 会静默累加。
- **C11 跨表无关联键**：leads 与 deals 没有统一联系人键，漏斗 SQLs → Deals 是两张表独立计数之比，不代表同一批人的转化（AGENTS.md 已声明不做跨表去重，属已知取舍，但需在图上说明）。

---

### 修复时新发现

**A4. 日期解析的格式推断陷阱（已在修复中一并处理）**

`pd.to_datetime` 会按列的第一个值推断单一格式。同一列里混排 `2026-09-01 08:30` 和 `2026-09-02` 时，后者会被静默置为 NaT，再被 `date.notna()` 过滤掉整行。修复：`_flexible_to_datetime` 走 `format="mixed"` 逐值解析。这个缺陷不体现在旧测试里，因为 fixture 的日期格式是统一的。

---

## 5. 数据源层面的问题（需业务确认，非代码缺陷）

1. **Traffic.csv 合计对不上**：文件共 100,001 行数据，末尾一行 `Grand total = 2,194,968`（代码已正确剔除），但明细 sessions 合计仅 **1,285,027**，差约 41%。疑似 10 万行导出上限或抽样导出，需确认导出完整性——这直接决定 All Traffic / Organic Traffic 是否可信。
2. **Deal.csv 只有 Closed Won**：117 条记录的 Deal Stage 全部是 `Closed Won`，没有进行中/丢失阶段，因此漏斗 Deals 层无法体现流失，SQLs → Deals 转化率天然偏低。
3. **leads.csv 生命周期有空值**：339 条 `Lifecycle Stage` 为空，2266 条为 `Subscriber`，按当前口径都计入 All Leads。

---

## 6. 修复记录（2026-09-27 已完成）

| 编号 | 问题 | 处理 |
|---|---|---|
| A1 | leads 主键损坏 | `data_loader._dedupe_key` 生成 `record_key`：优先 Email（去空格/转小写），缺失回退 `record:<Record ID>`；`metrics.key_column()` 统一取键 |
| A2 | 日期带时分秒 | `_day()` 统一 `.dt.normalize()`；`_selected` 改半开区间 `[start, end+1d)` |
| A3 | 漏斗键名拼接 | `metrics.FUNNEL_KEYS` 显式声明 `all_*` 与 `paid_*`；Revenue 层不再算转化率 |
| A4 | 日期格式推断 | `_flexible_to_datetime` 走 `format="mixed"` |
| B4 | 广告地区口径 | `config.AD_ACCOUNT_REGION_MAP` + `metrics._selected_ad_cost`；账户名不进地区下拉 |
| B5 | 环比不成立 | `app._previous_period` 等长前移区间，文案改 `vs prior period` |
| B6 | 付费口径不自洽 | Paid MQLs/SQLs 改用与整体一致的生命周期集合 |
| C7 | 死代码 | 移除 `compute_region_heatmap` 里未使用的 `trend`；漏斗图现在真正消费 `conversion` |
| C8 | 色阶截断 | 热力图 `zmax` 取实际最大值，不再写死 1 |
| C9 | 编码回退 | 落到 latin-1 时写入 warning 诊断，状态栏展示 warning 数 |
| C10 | 币种未校验 | 保存 `currency` 列，出现非 USD 时写入 warning 诊断 |

### 修复后实测（窗口 2026-08-23 ~ 09-21）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| All Leads | 30 | **1,085** |
| All MQLs | 17 | **338** |
| All SQLs | 12 | **144** |
| Cost per Lead | $2,211 | **$83** |
| Cost per MQL | $2,654 | **$128** |
| Overall Funnel | 全 0 | 139,660 → 1,085 → 338 → 144 → 11 → $122,994 |
| Paid Funnel | MQL 6 < SQL 7（倒置） | 25,302 → 318 → 207 → 104 → 6 → $26,583（单调） |
| 趋势图 | leads 合计 2，deals/revenue 全 0 | 与 KPI 完全一致（1,085 / 338 / 11 / 122,994），30 行 |
| 热力图 | 898 个日期列 | 30 个日期列 × 28 个地区 |
| 环比 | +3893.7% 等 | -1.2% ~ +72.6% 的合理区间 |
| 地区=Brazil | Ad Spend 0 → CPL/ROAS 全 N/A | Spend $7,034，CPL $44，ROAS 2.6x |

### 仍需业务确认

1. **Email 是否等于一个 Lead**：当前按邮箱去重（窗口内 1,085 行正好对应 1,085 个独立邮箱）。若业务上允许同一邮箱多次计为不同线索，需改回行计数。
2. **`config.AD_ACCOUNT_REGION_MAP` 的映射内容**：默认把 LATAM North / South 映射到中南美国家，且**刻意不含 Brazil / Mexico**（避免与 `Hytera Brazil` / `Hytera Mexico` 重复计入）。若 LATAM 账户实际也投放这两国，需在列表里补上。
3. **Traffic.csv 合计缺口**：明细 1,285,027 vs Grand total 2,194,968（差 41%），需确认导出是否完整。
