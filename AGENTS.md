# AGENTS.md

## 项目概览

这是一个基于 Plotly Dash 的数字营销 KPI dashboard。页面使用英文界面，视觉参考 `Digital Marketing KPI Dashboard` 类运营看板，重点展示日粒度营销漏斗、来源贡献和付费媒体效率。

**数据入口是上传页**：打开应用先看到 Traffic / Leads / Deals / Ads Cost 四个上传格子，四个 CSV 都解析成功后才渲染 dashboard（Docker 部署同样如此，容器里不再挂载数据目录）。显式传 `--data-dir` 或 `DASHBOARD_DATA_DIR` 时才跳过上传页、直接读服务端目录，这只是本地调试的旁路。

项目目录：`/Users/shechengying/workspace/dashboard/dashboard-py`

样例数据目录：`/Users/shechengying/workspace/dashboard/数据底表V1`

## 运行环境

当前开发机是 Windows，虚拟环境在 `dashboard-py/.venv`：

```bash
cd dashboard-py
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe app.py --port 8051        # 上传页模式（默认）
.venv/Scripts/python.exe app.py --data-dir ../数据底表V1 --port 8051   # 跳过上传页，方便本地调试
```

浏览器地址：`http://127.0.0.1:8051`（8050 被 Docker 容器占用，本地调试别用）

仓库历史里记录的 macOS 路径（`/Users/shechengying/workspace/dashboard/.venv/bin/python`）在当前环境不存在，按上面的路径执行。

容器部署：`docker compose build dashboard && docker compose up -d dashboard`（配合 cloudflared 隧道对外提供上传页）。

## 文件职责

- `app.py`：Dash 应用入口、上传回调、数据集内存缓存（`DATA_CACHE` + `data-key`）、筛选回调、命令行参数。
- `config.py`：目标参考值、`DEFAULT_DAYS`、区域组定义（`REGION_GROUPS` / `region_group()`）和账户→国家映射。
- `data_loader.py`：递归遍历 CSV / 解析上传内容、按列名识别业务表、日期/数值清洗、来源分类和诊断信息。
- `metrics.py`：KPI、漏斗、日趋势、来源占比、地区热力图和安全比率计算。
- `charts.py`：Plotly Figure 工厂、颜色主题和空状态图表。
- `layout.py`：页面外壳（header + 上传页 + dashboard 容器）、上传格子、筛选器、KPI 卡片和图表容器。
- `assets/styles.css`：深蓝 header、浅色 dashboard、上传页网格、KPI 网格和响应式布局。
- `tests/test_data_loader.py`：文件识别、递归扫描、日期解析、广告成本归一化、上传解析测试。
- `tests/test_metrics.py`：核心 KPI、比率、漏斗、趋势与空表筛选测试。
- `tests/test_config.py`：国家名/广告账户名 → 区域组的映射测试。
- `tests/browser_smoke.mjs`：浏览器侧冒烟（CDP 驱动真实 Chrome），验证目标输入框 → 卡片达成率 → localStorage 的完整链路，含回车/失焦提交与刷新回填。不属于 pytest，用 `node tests/browser_smoke.mjs` 手动跑。
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

上传页（`load_uploads`）与目录扫描（`load_folder`）共用同一套列名识别、清洗和诊断逻辑，不要为上传另写一套解析。上传的四个格子（`data_loader.UPLOAD_SLOTS`：traffic / leads / deals / ad_cost）只是给使用者分组用的：

- 表类型仍由列名决定。文件放错格子时把表按真实类型加载，并给出一条 warning（「Uploaded in the Traffic slot but the columns are a Deals table」）。
- 列名对不上任何已知表型时报 error 且不加载，绝不能退回按文件名猜。
- 一个格子可以放多份同类文件（Ads Cost 就常有 `Ads Cost.csv` + `加拿大Ads Cost.csv` 两张），按类型合并。
- 四个格子全部有数据才允许渲染 dashboard；缺一个就留在上传页并显示缺哪个。

标准化后的主要字段：

- Traffic：`date`、`region`、`source`、`source_class`、`sessions`
- Leads：`date`、`region`、`record_id`、`lifecycle_stage`、`source`、`source_class`
- Deals：`date`、`region`、`record_id`、`deal_stage`、`amount`、`source`、`source_class`
- Ad cost：`date`、`region`、`cost`、`currency`

来源分类不区分大小写，且**只看前缀**：以 `Organic` 开头的来源为 `organic`，以 `Paid` 开头的为 `paid`，其他为 `other`。不要用包含判断——口径要求是 `Organic xxx` / `Paid xxx`。

日期必须支持普通日期、带时间日期和 Traffic 中常见的 `YYYYMMDD`/`YYYYMMDD.0` 格式，且必须**归一到日历日**（`.dt.normalize()`）。HubSpot 导出的 `Create Date` / `Close Date` 带时分秒，不归一化会让区间最后一天整日丢失、按天分组错位。日期解析必须走 mixed 模式：`pd.to_datetime` 会按第一个值推断单一格式，同列混排 `2026-09-01 08:30` 与 `2026-09-02` 时后者会被静默置为 NaT 并整行丢弃。

Traffic 的 `Grand total` 汇总行不参与明细计算。

地区为空的行**不能整行丢弃**，归入 `Unassigned`（`config.UNKNOWN_REGION`）后参与总量：口径表里的 All Traffic / All Leads 等指标没有地区条件，丢弃会让总量凭空少一块（真实数据里 Traffic 少 1 条 Unassigned 明细、Leads 少 61 行）。

**Region 筛选器只给区域组，不给国家明细**：底表的 `region` 列是国家名（广告花费是投放账户名），筛选时统一经 `config.region_group()` 归一成 `Brazil` / `Mexico` / `LATAM North` / `LATAM South` / `Canada`，`metrics._selected()` 按 `region_group` 列匹配。不在任何区域组里的国家（美国、西班牙、亚太等）落到 `Other`、空地区落到 `Unassigned`，两者都不进下拉，只在不限地区时计入总量——不要为了让它们在下拉里可见而放宽映射。区域组与国家清单维护在 `config.REGION_GROUPS`，LATAM North / LATAM South 的覆盖范围与广告账户 `Hytera LATAM North` / `Hytera LATAM South` 一致。热力图也按同一套区域组分行，行标签与筛选器保持一致。

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
| Ad Spend（`Ads Cost`） | Ad cost（两张表合并） | Cost 求和，展示为 USD |
| Paid Traffic | Traffic | `source_class == paid` 的 Sessions 求和 |
| Paid Leads | Leads | 付费来源且 `∈ LEAD_STAGES` 的行数 |
| Paid MQLs | Leads | 付费来源且 `∈ MQL_STAGES` 的行数 |
| Paid SQLs | Leads | 付费来源且 `∈ SQL_STAGES` 的行数 |
| Paid Customers | **Leads** | 付费来源且 `== Customer` 的行数（不是 Deal 表） |
| Paid Revenue | Deals | 付费来源的 Amount 求和 |
| Cost per Lead | — | `Ad Spend / Paid Leads` |
| Cost per MQL | — | `Ad Spend / Paid MQLs` |
| ROAS | — | `Paid Revenue / Ad Spend` |

口径表 Sheet1 的 KPI 名有两处笔误，代码与页面用正确拼写：`All Cutomers` → `All Customers`、`All Revenues` → `All Revenue`；`Ads Cost` 在页面上沿用既有的 `Ad Spend` 标题。

Deal 表在口径里**只提供 Revenue**（All Revenue / Paid Revenue = `SUM(Amount)`），不再提供成交笔数：Sheet1 已无 Deals 类指标，漏斗第 5 层与 Sheet2 的 `sql-deal`、`paid sql-paid deal` 都对应 Customers。

漏斗顺序：`Traffic -> Leads -> MQLs -> SQLs -> Customers -> Revenue`。第 5 层整体与付费都用 **Customers**（Sheet1 的 All Customers / Paid Customers 同源，`metrics.FUNNEL_KEYS`），不要再拿 Deal 表的成交笔数当漏斗层。最后一层 Revenue 是金额，与计数不同量纲，不计算环节转化率。分母为空或为 0 时返回 `None`，页面显示 `N/A`，不能显示无穷值或伪造的 0。

环比按**等长前移区间**计算：当前区间 N 天，则对比其前 N 天（`app._previous_period`）。不要用"区间聚合值 vs 前一日单日值"，那会得出几千个百分点的无意义数字。分母缺失或为 0 时显示 `N/A`。

广告花费的地区口径与其他表不同：ad cost 的 `region` 是**投放账户名**（如 `Hytera Brazil`），不是国家名。`config.region_group()` 先经 `AD_ACCOUNT_REGION_MAP` 把账户映射成覆盖国家，再归到区域组，因此 `Hytera Brazil` / `Hytera LATAM North` 这类账户名能和 Brazil / LATAM North 的国家明细一起被选中；没配映射的账户落 `Other`，只在不限地区时计入。账户名本身不进入 Region 下拉选项。

### 目标与达成率

目标清单只有一份来源：`config.TARGET_SPECS`。每项声明 `id`（localStorage 里的键名）、`label`（输入框文案）、`metric`（`compute_kpis` 的键名）、`default`/`step`/`format`。加目标就改这一处，`layout.py` 的输入框与挂载点、`app.py` 的回调、页面上的卡片都会跟着派生。

| 目标 | 对应 KPI | 默认值 | 来源 |
|---|---|---|---|
| Target Organic Traffic | `organic_traffic` | 478,649 | Sheet2 |
| Target Leads | `all_leads` | 15,500 | Sheet2 |
| Target MQLs | `all_mqls` | 5,879 | Sheet2 |
| Target SQLs | `all_sqls` | 留空 | Sheet2 有 `sqls % of Target` 但没有目标值，留空即不显示达成率 |
| Target Revenue | `all_revenue` | 1,520,000 | Sheet2 写的是 `1.52M USD` |

- 达成率 = 实际值 / 目标值（`metrics.compute_target_progress`），同时给出缺口：未达标显示 `73% of target · 4,117 to go`，达标显示 `157% of target · 283 ahead`。
- 目标没填、填 0、填非法值时 `attainment` / `gap` 返回 `None`，卡片显示 `No target set`，**不能伪造 0%**；`metrics.as_number()` 是唯一的输入解析入口（把 0 和负数也视作没填，避免拿 0 当分母算出无穷）。
- 目标值是**每次会话可改的参考值**，Sheet2 里那几行的年份标注互相冲突（2026~2029），不要在任何地方把它写成某年的正式承诺。
- 五个目标的卡片都在第 1 区块（`OVERALL_CARDS` 里），所以输入框放在第 1 区块顶部、KPI 网格之上。

## 页面和交互约定

- 页面语言为英文。
- 默认日期范围为最大可用日期往前 29 天，即最近 30 天。
- 全局筛选器只有 `Date Range` 和 `Region`，没有全局 Channel 筛选器。
- Region 是多选下拉，选项固定为 `Brazil` / `Mexico` / `LATAM North` / `LATAM South` / `Canada`（`config.REGION_GROUP_ORDER`），不选即为 All Regions。
- Dashboard 区块包括：KPI cards、overall/paid funnel、conversion trend、source share、paid media efficiency 和 regional heatmap。
- 所有 KPI 和图表必须由同一个 Date Range/Region 回调联动更新。
- 无数据时使用空状态 Figure；筛选器不能因为无数据而消失。
- 数据加载状态显示识别出的表类型、错误数和最大数据日期。
- 打开应用先看到上传页，四个格子都解析成功后才渲染 dashboard（`app.handle_uploads` 一次性输出 `data-key` + `upload-gate.style` + `dashboard-root.children` + 四个状态行）。
- 上传的 CSV 只在进程内存里（`app.DATA_CACHE`，`data-key` 指向自己那一份，最多保留 8 份），不落盘、不进仓库。
- dashboard 里的 `Change files` 按钮清空四个格子并回到上传页；重置后必须把 `data-key` 置空，不能留下不完整数据集的句柄。
- KPI 卡片下方可挂一条目标达成率（`config.TARGET_SPECS`，输入框在 dashboard 顶部）：使用者填的值存浏览器 localStorage（`target-store`），达成率由 `update_targets` 回调按当前 Date Range/Region 重算；上传页阶段 `target-store` 没有 `data-key`，相关回调必须返回 `no_update` 而不是写不存在的组件。
- 目标输入框有两个必踩的坑：**不能用 `debounce=True`**（`type="number"` 时 Chromium 只在失焦时补发 `change`，按回车不提交，使用者会以为输入没生效；`compute_kpis` 只要十几毫秒，直接边打边算）；**`dcc.Input` 的 `className` 挂在最外层 div 上**，真正的输入框是里面的 `.dash-input-element`，写样式要选 `.target-input .dash-input-element`。
- 达成率以**输入框的值**为准，不读 `target-store`：首次访问时 localStorage 还是空的，而输入框已经显示布局里的默认目标值，读 store 会得到「输入框有数字、卡片却写 No target set」。持久化由 `save_targets` / `restore_targets` 两个回调单独负责。
- 三个目标回调用 `dcc.Store` 的 `data` 与 `modified_timestamp` 两个**不同属性**做存取，避开 input→store→input 的循环依赖；`restore_targets` 只在「有 `data-key` 且有存量」时回填，其余情况返回 `no_update` 保留布局默认值。
- dashboard 组件是上传后才创建的，所以 `create_app` 必须开 `suppress_callback_exceptions=True`（默认 `--data-dir` 模式下反而直接渲染）。

## 开发和验证

每次修改数据加载或指标计算后运行：

```bash
cd dashboard-py
.venv/Scripts/python.exe -m pytest -q          # Windows
.venv/Scripts/python.exe -m compileall -q .
```

（`AGENTS.md` 里记录的 macOS 路径 `/Users/shechengying/workspace/dashboard/.venv/bin/python` 在新环境不存在，按上面的 Windows 路径执行。）

当前已验证：测试套件 `38 passed`。曾经发现并修复的边界问题包括：

- `YYYYMMDD` 数值日期被误解析成 1970 年纳秒时间。
- Region 筛选后某类表为空，趋势计算缺失汇总列导致 callback error。
- 同列混排带时间与纯日期时，`pd.to_datetime` 按首值推断格式导致整行被丢弃（改 mixed 解析）。
- leads/deals 日期带时分秒，导致区间最后一天丢失、按天分组错位（改日历日归一化）。
- Excel 把 `Record ID` 存成科学计数法导致去重后线索数从 1085 变 30（改为按行计数，`record_key` 已移除）。
- 整体漏斗用空前缀拼键名，取不到 `all_*` 指标导致六层全 0（改 `FUNNEL_KEYS` 显式声明）。
- 环比拿 30 天聚合值比单日值（改等长前移区间）。
- 付费 MQL 用等值匹配、整体 MQL 用集合匹配，导致漏斗 MQL < SQL 倒置（统一为集合口径）。
- 地区为空的行被整行丢弃，导致 All Traffic 少 1 条 Unassigned 明细、Leads 少 61 行（改为归入 `Unassigned`）。
- 广告花费漏读 `加拿大Ads Cost.csv`，Ad Spend、CPL/CPMQL、ROAS 全部偏低（改为两张花费表合并）。
- Region 下拉按国家明细展示（近 180 个选项），与广告账户口径对不上；改为区域组后在 `metrics._selected()` 统一归组筛选。
- `dcc.Upload(multiple=True)` 的 `contents` / `filename` 都是**列表**（单文件也是长度为 1 的列表），按字符串处理会 `AttributeError: 'list' object has no attribute 'split'`；上传回调必须逐文件成对遍历。
- 对外容器默认带 `--debug 1` 跑着 Werkzeug 交互式调试器（公开上传入口下的 RCE 风险），Dockerfile / compose 已显式加 `--debug 0 --reload 0`。
- 目标输入框用 `debounce=True` 时，`type="number"` 按回车不提交（Chromium 只在失焦补发 `change`），输入框里明明有数字、卡片却一直不变；改为 `debounce=False` 后回车/失焦/粘贴都能触发。
- 达成率一度从 `target-store` 取值，导致首次访问（localStorage 为空）时输入框显示默认目标、卡片却写 `No target set`；改为以输入框的值为准。
- `dcc.Input` 的 `className` 挂在最外层 div 上（`dash-input-container dash-input target-input`），真正的输入框是内部的 `.dash-input-element`；只写 `.target-input { padding: ... }` 样式不会落到输入框上。

**目标与达成率这类只存在于浏览器里的行为，用 `tests/browser_smoke.mjs` 验**（pytest 覆盖不到 dcc.Input 的提交时机、React 受控输入和 localStorage）：

```bash
cd dashboard-py && ./.venv/Scripts/python.exe app.py --data-dir ../数据底表V1 --port 8051 &
rm -rf /tmp/cdp-profile
"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu --no-sandbox \
  --remote-debugging-port=9222 --user-data-dir=/tmp/cdp-profile --no-first-run about:blank &
node tests/browser_smoke.mjs          # 输出 PASS/FAIL，8 项
```

写这类脚本有两个必须遵守的点：`type="number"` 的输入框不支持 `setSelectionRange`，全选要走 Ctrl+A 键盘事件；用 `element.value = x` + 合成事件 React 不认，必须用 CDP 的 `Input.insertText`。另外**跑之前先确认没有残留的 Chrome 连着 9222**，否则会连上旧会话、localStorage 里带着上一轮的值，断言会莫名其妙地失败。

**测试 fixture 必须用真实数据形态**：带时分秒的日期、重复且丢精度的 `Record ID`、账户名形式的广告地区。用午夜日期 + 干净主键的 fixture 会让上述所有问题全部漏检。

启动后至少验证：

1. 首页和 Dash layout 接口可访问，未上传时页面是上传页（含 `upload-traffic` 等四个格子、没有 `region-filter`）。
2. 上传四个 CSV 后 `data-key` 有值、`upload-gate` 被隐藏、dashboard 渲染出来。
3. 用新 `data-key` 触发筛选回调，KPI / 漏斗 / 趋势 / 热力图都能更新（Region 组切换同样）。
4. 只传三个表时停在上传页并提示缺哪个；把 Deals 丢进 Traffic 格子时给出「放错格子」警告。
5. 空表/无数据日期不会产生 callback error、Infinity 或异常崩溃；`data-key` 失效（缓存被淘汰）时回调只返回 `no_update`，不报错。

用 Dash 的 HTTP 接口做端到端冒烟：`output` 传 `app.callback_map` 里的完整 key（`..id.prop...id.prop..`），`outputs` 要列全部输出，响应里每个输出的值是按属性包起来的（如 `resp["data-key"]["data"]`）。

## 修改边界

- 保持数据加载、指标计算、图表生成和页面布局分层，不要把业务口径直接写进 Dash callback。
- 新增指标时先在 `metrics.py` 添加明确函数和测试，再接入 `app.py`。
- 上传的数据集只放内存，不写临时文件、不落盘；页面文案保持英文。
- `--data-dir` / `DASHBOARD_DATA_DIR` 只是本地调试旁路，默认路径必须是上传页；改部署（Dockerfile / docker-compose.yml）时别再默认挂载数据目录。
- 新增底表类型时先扩展列名识别、标准化字段和数据加载测试。
- 不根据用户提供的参考图片数字写死业务结果；图片只作为视觉参考。
- 不做跨表去重，除非后续提供可靠的统一联系人/成交关联键。
- 目标配置当前只是参考值，因目标年份与数据年份不完全一致，不要把它描述为当前年度承诺。
- 仓库已初始化并绑定 GitHub：分支 `main`，remote `git@github.com:chengyingshe/dashboard.git`，可以用 git 历史，不要伪造 commit hash。
- `数据底表V1/` 的 CSV 是真实客户线索与成交数据，已随仓库入库；仓库转 public 会泄露，新增文件时注意不要引入敏感导出。
