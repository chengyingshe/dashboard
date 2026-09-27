# Digital Marketing Dashboard 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）来跟踪进度。

**目标：** 构建一个本地 Plotly Dash 日粒度营销 KPI dashboard，从用户配置的文件夹自动发现并按列名识别 CSV 表格，支持 Date Range 和 Region 筛选。

**架构：** 使用 Pandas 负责文件遍历、表识别、清洗和标准化，使用独立的 metrics 模块计算业务指标，使用 Dash 回调把筛选状态传给 Plotly 图表生成函数。数据处理、指标计算和展示层彼此隔离，后续可替换为缓存或数据库而不改变页面接口。

**技术栈：** Python 3、Dash、Plotly、Pandas、pytest。

---

## 文件清单

- 创建：`config.py`，数据目录、目标参考值和展示常量。
- 创建：`data_loader.py`，递归扫描 CSV、按列名识别表、清洗并返回标准化数据集和诊断信息。
- 创建：`metrics.py`，实现 KPI、漏斗、环比、来源占比和地区热力表计算。
- 创建：`charts.py`，生成 Plotly 图表和空状态。
- 创建：`layout.py`，创建 Dash 页面布局、筛选器、状态区和 KPI 容器。
- 创建：`app.py`，注册 Dash 应用、加载数据、注册回调和启动入口。
- 创建：`assets/styles.css`，实现参考图风格的桌面 dashboard 样式。
- 创建：`tests/test_data_loader.py`，覆盖文件识别和数据质量行为。
- 创建：`tests/test_metrics.py`，覆盖核心指标和边界情况。
- 修改：`requirements.txt`，补充 `dash`、`pandas` 和 `pytest`。

## 任务 1：建立依赖和配置边界

**文件：**
- 修改：`requirements.txt`
- 创建：`config.py`
- 测试：无独立测试；由后续导入测试覆盖。

- [ ] **步骤 1：补充运行依赖**

在 `requirements.txt` 中保留 `plotly`，加入版本无关的最小依赖：

```text
plotly
dash
pandas
pytest
```

- [ ] **步骤 2：定义配置对象**

在 `config.py` 中定义：

```python
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "数据底表V1"
DEFAULT_DAYS = 30
TARGETS = {
    "organic_traffic": 478649,
    "leads": 15500,
    "mqls": 5879,
    "revenue": 1_520_000,
    "close_win_conversion": 0.07,
}
```

同时提供 `resolve_data_dir(cli_value: str | None) -> Path`，优先使用 CLI 路径，其次使用 `DASHBOARD_DATA_DIR` 环境变量，最后使用 `DEFAULT_DATA_DIR`。

- [ ] **步骤 3：验证配置导入**

运行：`python3 -c "from config import DEFAULT_DATA_DIR, TARGETS; print(DEFAULT_DATA_DIR, TARGETS)"`

预期：成功打印数据目录和 5 个目标配置。

## 任务 2：实现 CSV 自动发现、识别和标准化

**文件：**
- 创建：`data_loader.py`
- 测试：`tests/test_data_loader.py`

- [ ] **步骤 1：先写失败测试覆盖表识别**

测试必须验证文件名无关的识别规则：

```python
def test_identifies_tables_by_columns(tmp_path):
    write_csv(tmp_path / "random-a.csv", ["Date", "Region", "Session default channel group", "Sessions"])
    write_csv(tmp_path / "random-b.csv", ["Record ID", "Create Date", "Lifecycle Stage", "Original Traffic Source", "Region"])
    write_csv(tmp_path / "random-c.csv", ["Record ID", "Close Date", "Deal Stage", "Amount", "Original Traffic Source", "Region"])
    write_csv(tmp_path / "random-d.csv", ["Day", "Currency code", "Cost", "Region"])

    bundle = load_folder(tmp_path)

    assert set(bundle.tables) == {"traffic", "leads", "deals", "ad_cost"}
```

同时覆盖递归目录扫描和来源分类：

```python
def test_scans_nested_csv_and_classifies_source_case_insensitively(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    write_csv(nested / "traffic.csv", ["Date", "Region", "Session default channel group", "Sessions"], [
        ["2026-09-01", "Brazil", "Organic Search", "10"],
        ["2026-09-01", "Brazil", "paid social", "5"],
    ])

    bundle = load_folder(tmp_path)

    assert set(bundle.tables["traffic"]["source_class"]) == {"organic", "paid"}
```

- [ ] **步骤 2：运行测试确认失败**

运行：`pytest tests/test_data_loader.py -q`

预期：FAIL，提示 `load_folder` 尚未定义。

- [ ] **步骤 3：实现最小数据加载接口**

实现以下稳定接口：

```python
@dataclass
class DataBundle:
    tables: dict[str, pd.DataFrame]
    diagnostics: list[Diagnostic]

def load_folder(folder: Path) -> DataBundle:
    ...
```

实现内容：递归 `rglob("*.csv")`；读取 UTF-8-SIG、UTF-8 和本地常见编码回退；根据必要列集合识别表；为每行添加 `source_file`；标准化日期列、数值列、地区列和 `source_class`；过滤 Traffic 的 `Grand total` 行；将无地区 ad cost 的 `Account name` 映射为 `region`。

识别不到的 CSV 不参与指标计算，但加入 diagnostics；同类表按规范化列合并，必要列冲突则加入 error diagnostic。

- [ ] **步骤 4：补充数据质量测试**

覆盖：缺文件夹、无 CSV、缺必要列、不可解析日期、不可解析金额、Traffic 汇总行、账户级广告成本和重复同类文件合并。

- [ ] **步骤 5：运行数据加载测试**

运行：`pytest tests/test_data_loader.py -q`

预期：全部 PASS。

## 任务 3：实现 KPI 和聚合计算

**文件：**
- 创建：`metrics.py`
- 测试：`tests/test_metrics.py`

- [ ] **步骤 1：编写固定样例和失败测试**

测试构造 2 天、2 个地区的标准化 DataFrame，验证：

```python
def test_compute_kpis_uses_business_definitions(sample_bundle):
    result = compute_kpis(sample_bundle, date_range=("2026-09-01", "2026-09-02"), regions=["Brazil"])

    assert result["organic_traffic"] == 10
    assert result["all_leads"] == 3
    assert result["all_mqls"] == 2
    assert result["all_sqls"] == 1
    assert result["all_revenue"] == 1000
    assert result["ad_spend"] == 100
    assert result["paid_leads"] == 1
    assert result["paid_revenue"] == 600
    assert result["roas"] == 6
```

另测分母为 0：

```python
def test_ratio_returns_none_for_zero_denominator():
    assert safe_ratio(10, 0) is None
```

- [ ] **步骤 2：运行测试确认失败**

运行：`pytest tests/test_metrics.py -q`

预期：FAIL，提示计算接口尚未实现。

- [ ] **步骤 3：实现标准化计算接口**

实现这些函数：

```python
def safe_ratio(numerator: float, denominator: float) -> float | None: ...
def filter_bundle(bundle, date_range, regions): ...
def compute_kpis(bundle, date_range, regions) -> dict: ...
def compute_funnel(bundle, date_range, regions, paid=False) -> pd.DataFrame: ...
def compute_daily_trends(bundle, date_range, regions) -> pd.DataFrame: ...
def compute_source_share(bundle, date_range, regions, metric) -> pd.DataFrame: ...
def compute_region_heatmap(bundle, date_range, regions, metric) -> pd.DataFrame: ...
```

使用明确的 lifecycle 集合、`Closed Won` 判断和大小写不敏感的 `source_class`。所有比率在分母缺失或为零时返回 `None`，而不是 `0` 或无穷值。环比使用前一日聚合值。

- [ ] **步骤 4：补充边界测试**

测试包括：日期范围过滤、多地区过滤、付费漏斗、漏斗相邻转化率、缺少前一日数据、前一日为零、空筛选结果、账户级广告成本合并和来源占比合计。

- [ ] **步骤 5：运行指标测试**

运行：`pytest tests/test_metrics.py -q`

预期：全部 PASS。

## 任务 4：实现 Plotly 图表工厂

**文件：**
- 创建：`charts.py`

- [ ] **步骤 1：定义空状态和主题常量**

建立统一的蓝色、青绿色、黄色、橙色、红色和紫色阶段色板，以及 `empty_figure(title, message)`。空图保持固定高度并显示原因。

- [ ] **步骤 2：实现图表函数**

实现：

```python
def make_funnel_figure(funnel_df, title): ...
def make_conversion_trend_figure(trend_df): ...
def make_source_donut_figure(source_df, title, center_label): ...
def make_spend_revenue_figure(trend_df): ...
def make_heatmap_figure(heatmap_df, title): ...
```

所有函数返回 `plotly.graph_objects.Figure`，统一使用白色背景、紧凑边距、hover 模板和固定高度。小来源在传入图表函数前由指标层合并为 `Other`。

- [ ] **步骤 3：验证图表对象**

运行：`python3 -c "from charts import empty_figure; assert empty_figure('x', 'y').layout.height > 0"`

预期：成功退出。

## 任务 5：实现 Dash 页面布局与回调

**文件：**
- 创建：`layout.py`
- 创建：`app.py`

- [ ] **步骤 1：建立可测试布局**

在 `layout.py` 中创建 header、筛选器、数据状态区、KPI card、五个 dashboard section 和图表容器。所有组件使用稳定 ID：`date-range`、`region-filter`、`data-status`、`kpi-*`、`overall-funnel`、`paid-funnel`、`conversion-trend`、`traffic-share`、`lead-share`、`mql-share`、`efficiency-trend`、`region-heatmap`。

- [ ] **步骤 2：添加桌面样式**

在 `assets/styles.css` 中实现深蓝 header、浅蓝灰 section 背景、最多 8px 圆角、紧凑 KPI 卡片、响应式两列/三列图表网格，并保证 1280px 桌面宽度不产生横向滚动。

- [ ] **步骤 3：创建应用入口**

在 `app.py` 中创建 `Dash(__name__, external_stylesheets=[])`，解析 `--data-dir`，加载 `DataBundle`，调用 `build_layout`，并注册回调。

- [ ] **步骤 4：实现单一联动回调**

回调输入为日期范围和 Region；输出 KPI 卡片、状态区和所有图表。回调内部只调用 `metrics.py` 的聚合函数和 `charts.py` 的图表工厂，不在回调里写业务口径判断。

日期默认取可用最大日期向前 29 天；如果没有可用数据，日期控件禁用并展示诊断信息。无数据筛选时返回空状态图。

- [ ] **步骤 5：启动应用验证基础页面**

运行：`python3 app.py --data-dir ../数据底表V1`

预期：终端显示 Dash 服务地址，浏览器访问后看到 header、筛选器、KPI 区和图表容器。

## 任务 6：完成回归测试和浏览器验证

**文件：**
- 修改：必要时修复 `data_loader.py`、`metrics.py`、`charts.py`、`layout.py`、`app.py`、`assets/styles.css`

- [ ] **步骤 1：运行全量单元测试**

运行：`pytest -q`

预期：全部 PASS，无 import error 或 warning 导致的失败。

- [ ] **步骤 2：使用真实底表启动**

运行：`python3 app.py --data-dir ../数据底表V1`

预期：所有可识别 CSV 加载成功；页面状态区显示文件数、表类型和刷新时间。

- [ ] **步骤 3：验证筛选联动**

在浏览器中验证：

1. 默认最近 30 天可显示数据或明确空状态。
2. 选择单个 Region 后 KPI、漏斗、趋势和热力表同步变化。
3. 修改 Date Range 后所有组件更新。
4. 选择无数据日期时显示 `N/A` 或 empty state，不显示无穷值。

- [ ] **步骤 4：验证桌面布局**

使用 1280px 以上窗口检查 header、筛选器、KPI 卡和主要图表无重叠、无横向溢出、长地区名不破坏布局。

- [ ] **步骤 5：记录工作区限制**

当前工作区不是 Git 仓库，因此不能执行计划要求的 commit 步骤；完成后报告测试结果、启动命令和实际变更文件，不伪造 commit hash。

## 计划自检

- 规格中的文件夹递归扫描、列名识别、数据清洗、指标口径、Date Range、Region、英文 UI、主要图表、错误处理和测试均有对应任务。
- 已搜索计划中的 `TODO`、`待定` 和无具体内容的“适当处理”类占位描述；没有保留此类步骤。
- 所有后续任务使用的接口名称与前置任务一致：`DataBundle`、`load_folder`、`compute_kpis`、`compute_funnel`、`compute_daily_trends`、`compute_source_share`、`compute_region_heatmap`。
