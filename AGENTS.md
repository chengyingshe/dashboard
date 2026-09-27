# AGENTS.md

## 项目概览

这是一个基于 Plotly Dash 的本地数字营销 KPI dashboard。页面使用英文界面，视觉参考 `Digital Marketing KPI Dashboard` 类运营看板，重点展示日粒度营销漏斗、来源贡献和付费媒体效率。

项目目录：`/Users/shechengying/workspace/dashboard/dashboard-py`

默认数据目录：`/Users/shechengying/workspace/dashboard/数据底表V1`

## 运行环境

优先使用项目指定虚拟环境：

```bash
/Users/shechengying/workspace/dashboard/.venv/bin/python
```

安装依赖：

```bash
/Users/shechengying/workspace/dashboard/.venv/bin/python -m pip install -r requirements.txt
```

启动应用：

```bash
cd /Users/shechengying/workspace/dashboard/dashboard-py
/Users/shechengying/workspace/dashboard/.venv/bin/python app.py \
  --data-dir ../数据底表V1 \
  --port 8050
```

浏览器地址：`http://127.0.0.1:8050`

也可以通过环境变量指定数据目录：

```bash
DASHBOARD_DATA_DIR=/path/to/csv-folder \
/Users/shechengying/workspace/dashboard/.venv/bin/python app.py
```

## 文件职责

- `app.py`：Dash 应用入口、数据初始化、回调注册和命令行参数。
- `config.py`：默认数据目录、目标参考值和路径解析。
- `data_loader.py`：递归遍历 CSV、按列名识别业务表、日期/数值清洗、来源分类和诊断信息。
- `metrics.py`：KPI、漏斗、日趋势、来源占比、地区热力图和安全比率计算。
- `charts.py`：Plotly Figure 工厂、颜色主题和空状态图表。
- `layout.py`：页面结构、筛选器、KPI 卡片和图表容器。
- `assets/styles.css`：深蓝 header、浅色 dashboard、KPI 网格和响应式布局。
- `tests/test_data_loader.py`：文件识别、递归扫描、日期解析、广告成本归一化测试。
- `tests/test_metrics.py`：核心 KPI、比率和空表筛选测试。
- `docs/superpowers/specs/2026-09-22-digital-marketing-dashboard-design.md`：已确认的设计规格。
- `docs/superpowers/plans/2026-09-22-digital-marketing-dashboard-plan.md`：实现计划。

## 数据识别约定

不要根据文件名判断表的业务作用。`data_loader.py` 会递归扫描目标目录下所有 `.csv` 文件，并按列名识别：

- Traffic：`Date`、`Region`、`Session default channel group`、`Sessions`
- Leads：`Record ID`、`Create Date`、`Lifecycle Stage`、`Original Traffic Source`、`Region`
- Deals：`Record ID`、`Close Date`、`Deal Stage`、`Amount`、`Original Traffic Source`、`Region`
- Regional ad cost：`Day`、`Currency code`、`Cost`、`Region`
- Account-level ad cost：`Day`、`Currency code`、`Cost`、`Account name`

同一业务类型的多个 CSV 会合并。无法识别或读取失败的文件进入 `DataBundle.diagnostics`，不能静默覆盖或猜测字段。

标准化后的主要字段：

- Traffic：`date`、`region`、`source`、`source_class`、`sessions`
- Leads：`date`、`region`、`record_id`、`lifecycle_stage`、`source`、`source_class`
- Deals：`date`、`region`、`record_id`、`deal_stage`、`amount`、`source`、`source_class`
- Ad cost：`date`、`region`、`cost`

来源分类不区分大小写：包含 `Organic` 的来源为 `organic`，包含 `Paid` 的来源为 `paid`，其他为 `other`。

日期必须支持普通日期、带时间日期和 Traffic 中常见的 `YYYYMMDD`/`YYYYMMDD.0` 格式。Traffic 的 `Grand total` 汇总行不参与明细计算。

## 业务指标口径

所有指标先按 Date Range 和 Region 筛选，再计算：

- Organic Traffic：Traffic 中 `source_class == organic` 的 Sessions 总和。
- All Traffic：Traffic Sessions 总和。
- All Leads：有效 Leads `record_id` 数量；按当前 Excel 口径不再额外限制生命周期。
- All MQLs：生命周期为 `Marketing Qualified Lead`、`Sales Qualified Lead` 或 `Customer` 的记录数。
- All SQLs：生命周期为 `Sales Qualified Lead` 或 `Customer` 的记录数。
- All Revenue：Deal Stage 为 `Closed Won` 的 Amount 总和。
- Ad Spend：所有 regional/account-level ad cost 的 Cost 总和，展示为 USD。
- Paid Traffic：Paid 来源 Traffic Sessions 总和。
- Paid Leads：来源为 Paid 且生命周期为 `Lead` 的记录数。
- Paid MQLs：来源为 Paid 且生命周期为 `Marketing Qualified Lead` 的记录数。
- Paid SQLs：来源为 Paid 且生命周期为 `Sales Qualified Lead` 的记录数。
- Paid Deals：`Closed Won` 且来源为 Paid 的 Deal 数量。
- Paid Revenue：`Closed Won` 且来源为 Paid 的 Amount 总和。
- Cost per Lead：`Ad Spend / Paid Leads`。
- Cost per MQL：`Ad Spend / Paid MQLs`。
- ROAS：`Paid Revenue / Ad Spend`。

漏斗顺序：`Traffic -> Leads -> MQLs -> SQLs -> Deals -> Revenue`。付费漏斗使用对应的 `Paid` 指标。分母为空或为 0 时返回 `None`，页面显示 `N/A`，不能显示无穷值或伪造的 0。

环比/日变化按照前一日值计算。当前回调将筛选区间起始日前一天作为 prior day；如果 prior day 缺失或分母为 0，则显示 `N/A`。

## 页面和交互约定

- 页面语言为英文。
- 默认日期范围为最大可用日期往前 29 天，即最近 30 天。
- 全局筛选器只有 `Date Range` 和 `Region`，没有全局 Channel 筛选器。
- Dashboard 区块包括：KPI cards、overall/paid funnel、conversion trend、source share、paid media efficiency 和 regional heatmap。
- 所有 KPI 和图表必须由同一个 Date Range/Region 回调联动更新。
- 无数据时使用空状态 Figure；筛选器不能因为无数据而消失。
- 数据加载状态显示识别出的表类型、错误数和最大数据日期。

## 开发和验证

每次修改数据加载或指标计算后运行：

```bash
/Users/shechengying/workspace/dashboard/.venv/bin/python -m pytest -q
/Users/shechengying/workspace/dashboard/.venv/bin/python -m compileall -q .
```

当前已验证：测试套件 `7 passed`。曾经发现并修复的边界问题包括：

- `YYYYMMDD` 数值日期被误解析成 1970 年纳秒时间。
- Region 筛选后某类表为空，趋势计算缺失 `all_deals` 等列导致 callback error。

启动后至少验证：

1. 首页和 Dash layout 接口可访问。
2. 默认最近 30 天能显示 KPI 或明确空状态。
3. 选择单个 Region 后 KPI、漏斗、趋势和热力图都能更新。
4. 空表/无数据日期不会产生 callback error、Infinity 或异常崩溃。

## 修改边界

- 保持数据加载、指标计算、图表生成和页面布局分层，不要把业务口径直接写进 Dash callback。
- 新增指标时先在 `metrics.py` 添加明确函数和测试，再接入 `app.py`。
- 新增底表类型时先扩展列名识别、标准化字段和数据加载测试。
- 不根据用户提供的参考图片数字写死业务结果；图片只作为视觉参考。
- 不做跨表去重，除非后续提供可靠的统一联系人/成交关联键。
- 目标配置当前只是参考值，因目标年份与数据年份不完全一致，不要把它描述为当前年度承诺。
- 当前目录不是 Git 仓库，不要伪造 commit hash 或假设存在分支历史。
