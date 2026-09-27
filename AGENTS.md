# AGENTS.md

## 项目概览

这是一个基于 Plotly Dash 的本地数字营销 KPI dashboard。页面使用英文界面，视觉参考 `Digital Marketing KPI Dashboard` 类运营看板，重点展示日粒度营销漏斗、来源贡献和付费媒体效率。

项目目录：`/Users/shechengying/workspace/dashboard/dashboard-py`

默认数据目录：`/Users/shechengying/workspace/dashboard/数据底表V1`

## 运行环境

当前开发机是 Windows，虚拟环境在 `dashboard-py/.venv`：

```bash
cd dashboard-py
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe app.py --data-dir ../数据底表V1 --port 8050
```

仓库历史里记录的 macOS 路径（`/Users/shechengying/workspace/dashboard/.venv/bin/python`）在当前环境不存在，按上面的路径执行。

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
- `tests/test_metrics.py`：核心 KPI、比率、漏斗、趋势与空表筛选测试。
- `数据口径.xlsx`（仓库根目录）：业务口径的权威来源，Sheet1 是各 KPI 的计算公式，Sheet2 是派生指标与环比定义。修改 `metrics.py` 前先看它。
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
- Ad cost：`date`、`region`、`cost`、`currency`

来源分类不区分大小写，且**只看前缀**：以 `Organic` 开头的来源为 `organic`，以 `Paid` 开头的为 `paid`，其他为 `other`。不要用包含判断——口径要求是 `Organic xxx` / `Paid xxx`。

日期必须支持普通日期、带时间日期和 Traffic 中常见的 `YYYYMMDD`/`YYYYMMDD.0` 格式，且必须**归一到日历日**（`.dt.normalize()`）。HubSpot 导出的 `Create Date` / `Close Date` 带时分秒，不归一化会让区间最后一天整日丢失、按天分组错位。日期解析必须走 mixed 模式：`pd.to_datetime` 会按第一个值推断单一格式，同列混排 `2026-09-01 08:30` 与 `2026-09-02` 时后者会被静默置为 NaT 并整行丢弃。

Traffic 的 `Grand total` 汇总行不参与明细计算。

**不做去重，所有 COUNT 都按行计**：口径表（`数据口径.xlsx` Sheet1）里的 COUNT 一律是行数。Excel 会把 11 位 `Record ID` 存成科学计数法（`2.05E+11`）导致精度丢失，几千行会共用一个 ID，因此任何基于 `record_id` 的 `nunique()` 都是错的。计数一律用 `metrics._count_rows()`（即 `len(frame[mask])`）。

## 业务指标口径

口径以 `数据口径.xlsx` Sheet1 为准（Sheet2 是派生指标与环比定义）。所有指标先按 Date Range 和 Region 筛选，再计算：

生命周期集合（`metrics.py` 常量）：

- `LEAD_STAGES` = `Lead` / `Marketing Qualified Lead` / `Sales Qualified Lead` / `Customer`
- `MQL_STAGES` = `Marketing Qualified Lead` / `Sales Qualified Lead` / `Customer`
- `SQL_STAGES` = `Sales Qualified Lead` / `Customer`
- `CUSTOMER_STAGE` = `Customer`

`Subscriber` 和空值不属于任何一档，不参与任何计数。

| KPI | 来源 | 计算 |
|---|---|---|
| Organic Traffic | Traffic | `source_class == organic` 的 Sessions 求和 |
| All Traffic | Traffic | Sessions 求和 |
| All Leads | Leads | `Lifecycle Stage ∈ LEAD_STAGES` 的行数 |
| All MQLs | Leads | `∈ MQL_STAGES` 的行数 |
| All SQLs | Leads | `∈ SQL_STAGES` 的行数 |
| All Customers | Leads | `== Customer` 的行数 |
| All Revenue | Deals | Amount 求和（**不再限定 Closed Won**） |
| Ad Spend | Ad cost | Cost 求和，展示为 USD |
| Paid Traffic | Traffic | `source_class == paid` 的 Sessions 求和 |
| Paid Leads | Leads | 付费来源且 `∈ LEAD_STAGES` 的行数 |
| Paid MQLs | Leads | 付费来源且 `∈ MQL_STAGES` 的行数 |
| Paid SQLs | Leads | 付费来源且 `∈ SQL_STAGES` 的行数 |
| Paid Deals | **Leads** | 付费来源且 `== Customer` 的行数（不是 Deal 表） |
| Paid Revenue | Deals | 付费来源的 Amount 求和 |
| Cost per Lead | — | `Ad Spend / Paid Leads` |
| Cost per MQL | — | `Ad Spend / Paid MQLs` |
| ROAS | — | `Paid Revenue / Ad Spend` |

漏斗顺序：`Traffic -> Leads -> MQLs -> SQLs -> Customers -> Revenue`。第 5 层整体与付费都用 **Customers**（Sheet1 的 All Customers / Paid Deals 同源，`metrics.FUNNEL_KEYS`），不要再拿 Deal 表的成交笔数当漏斗层。最后一层 Revenue 是金额，与计数不同量纲，不计算环节转化率。分母为空或为 0 时返回 `None`，页面显示 `N/A`，不能显示无穷值或伪造的 0。

环比按**等长前移区间**计算：当前区间 N 天，则对比其前 N 天（`app._previous_period`）。不要用"区间聚合值 vs 前一日单日值"，那会得出几千个百分点的无意义数字。分母缺失或为 0 时显示 `N/A`。

广告花费的地区口径与其他表不同：ad cost 的 `region` 是**投放账户名**（如 `Hytera Brazil`），不是国家名。地区筛选时经 `config.AD_ACCOUNT_REGION_MAP` 把账户映射到覆盖国家；未配置映射的列按普通地区名直接匹配。账户名不进入 Region 下拉选项。

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
cd dashboard-py
.venv/Scripts/python.exe -m pytest -q          # Windows
.venv/Scripts/python.exe -m compileall -q .
```

（`AGENTS.md` 里记录的 macOS 路径 `/Users/shechengying/workspace/dashboard/.venv/bin/python` 在新环境不存在，按上面的 Windows 路径执行。）

当前已验证：测试套件 `20 passed`。曾经发现并修复的边界问题包括：

- `YYYYMMDD` 数值日期被误解析成 1970 年纳秒时间。
- Region 筛选后某类表为空，趋势计算缺失汇总列导致 callback error。
- 同列混排带时间与纯日期时，`pd.to_datetime` 按首值推断格式导致整行被丢弃（改 mixed 解析）。
- leads/deals 日期带时分秒，导致区间最后一天丢失、按天分组错位（改日历日归一化）。
- Excel 把 `Record ID` 存成科学计数法导致去重后线索数从 1085 变 30（改为按行计数，`record_key` 已移除）。
- 整体漏斗用空前缀拼键名，取不到 `all_*` 指标导致六层全 0（改 `FUNNEL_KEYS` 显式声明）。
- 环比拿 30 天聚合值比单日值（改等长前移区间）。
- 付费 MQL 用等值匹配、整体 MQL 用集合匹配，导致漏斗 MQL < SQL 倒置（统一为集合口径）。

**测试 fixture 必须用真实数据形态**：带时分秒的日期、重复且丢精度的 `Record ID`、账户名形式的广告地区。用午夜日期 + 干净主键的 fixture 会让上述所有问题全部漏检。

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
- 仓库已初始化并绑定 GitHub：分支 `main`，remote `git@github.com:chengyingshe/dashboard.git`，可以用 git 历史，不要伪造 commit hash。
- `数据底表V1/` 的 CSV 是真实客户线索与成交数据，已随仓库入库；仓库转 public 会泄露，新增文件时注意不要引入敏感导出。
