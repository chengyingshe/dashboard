from __future__ import annotations

from dash import dcc, html

from config import DEFAULT_TARGETS, TARGET_BY_METRIC, TARGET_SPECS
from data_loader import UPLOAD_SLOTS


def target_input_id(target_id: str) -> str:
    return f"target-{target_id.replace('_', '-')}"


def target_progress_id(target_id: str) -> str:
    return f"target-progress-{target_id.replace('_', '-')}"


def _card(title: str, value_id: str, delta_id: str, progress_id: str | None = None) -> html.Div:
    children = [
        html.Div(title, className="kpi-title"),
        html.Div(id=value_id, className="kpi-value"),
        html.Div(id=delta_id, className="kpi-delta"),
    ]
    if progress_id:
        children.append(html.Div(id=progress_id, className="kpi-target"))
    return html.Div(children, className="kpi-card")


# KPI 卡片的 id 由指标名派生：organic_traffic -> kpi-organic-traffic / delta-organic-traffic
OVERALL_CARDS = [
    ("Organic Traffic", "organic_traffic"),
    ("All Traffic", "all_traffic"),
    ("All Leads", "all_leads"),
    ("All MQLs", "all_mqls"),
    ("All SQLs", "all_sqls"),
    ("All Customers", "all_customers"),
    ("All Revenue", "all_revenue"),
]

PAID_CARDS = [
    ("Ad Spend", "ad_spend"),
    ("Paid Traffic", "paid_traffic"),
    ("Paid Leads", "paid_leads"),
    ("Paid MQLs", "paid_mqls"),
    ("Paid SQLs", "paid_sqls"),
    ("Paid Customers", "paid_customers"),
    ("Paid Revenue", "paid_revenue"),
    ("Cost per Lead", "cost_per_lead"),
    ("Cost per MQL", "cost_per_mql"),
    ("ROAS", "roas"),
]

# 上传页四个格子：id 与 data_loader 的表类型一致，文案面向使用者
UPLOAD_SLOT_SPECS = [
    {"id": "traffic", "label": "Traffic", "hint": "Sessions by day, region and channel"},
    {"id": "leads", "label": "Leads", "hint": "Lifecycle stage per record"},
    {"id": "deals", "label": "Deals", "hint": "Amount and close date"},
    {"id": "ad_cost", "label": "Ads Cost", "hint": "Daily spend per ad account (several files allowed)"},
]


def _cards(specs):
    cards = []
    for title, name in specs:
        # 只有配了目标的指标才多挂一行达成率
        target_id = TARGET_BY_METRIC.get(name)
        cards.append(
            _card(
                title,
                f"kpi-{name.replace('_', '-')}",
                f"delta-{name.replace('_', '-')}",
                target_progress_id(target_id) if target_id else None,
            )
        )
    return cards


def _target_input(spec: dict, values: dict) -> html.Div:
    target_id = spec["id"]
    return html.Div(
        [
            html.Label(spec["label"]),
            dcc.Input(
                id=target_input_id(target_id),
                type="number",
                min=0,
                step=spec["step"],
                value=values.get(target_id),
                placeholder="Not set",
                # 不能用 debounce：type="number" 时 Chromium 只在失焦时补发 change，
                # 按回车不会提交，使用者会以为输入没生效。compute_kpis 只要十几毫秒，
                # 直接边打边算，回车/失焦/粘贴都能触发。
                debounce=False,
                className="target-input",
            ),
        ],
        className="target-control",
    )


def _targets_strip(targets: dict | None = None) -> html.Div:
    """目标输入条：改动即刷新下面卡片上的达成率。"""
    values = dict(DEFAULT_TARGETS)
    values.update({key: value for key, value in (targets or {}).items() if key in DEFAULT_TARGETS})
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Targets", className="targets-title"),
                    html.Span("Type a target for the selected period; achievement shows on the cards below.", className="targets-hint"),
                ],
                className="targets-head",
            ),
            html.Div([_target_input(spec, values) for spec in TARGET_SPECS], className="target-grid"),
        ],
        className="targets-strip",
    )


def _upload_slot(spec: dict) -> html.Div:
    slot = spec["id"]
    return html.Div(
        [
            html.Div(spec["label"], className="slot-title"),
            html.Div(spec["hint"], className="slot-hint"),
            dcc.Upload(
                id=f"upload-{slot}",
                children=html.Div(["Drag & drop or ", html.Span("browse", className="slot-browse")], className="slot-drop"),
                className="slot-dropzone",
                multiple=True,
                accept=".csv",
            ),
            html.Div("No file selected", id=f"slot-status-{slot}", className="slot-status"),
        ],
        className="upload-slot",
    )


def build_upload_gate() -> html.Div:
    """初始上传页：四个表格都就绪后才渲染 dashboard。"""
    return html.Div(
        [
            html.Div("Load the four source tables", className="gate-title"),
            html.P(
                "Upload the CSV exports for Traffic, Leads, Deals and Ads Cost. "
                "Files are read in this browser session only and are never written to disk.",
                className="gate-subtitle",
            ),
            html.Div([_upload_slot(spec) for spec in UPLOAD_SLOT_SPECS], className="upload-grid"),
            html.Div("The dashboard appears automatically once all four tables are loaded.", className="gate-foot"),
        ],
        className="upload-gate",
    )


def build_dashboard(regions, min_date=None, max_date=None, start_date=None, show_reset=False, targets=None) -> html.Main:
    filters = [
        html.Div(
            [
                html.Label("Date Range"),
                dcc.DatePickerRange(id="date-range", min_date_allowed=min_date, max_date_allowed=max_date, start_date=start_date or min_date, end_date=max_date, display_format="MMM D, YYYY"),
            ],
            className="filter-control",
        ),
        html.Div(
            [html.Label("Region"), dcc.Dropdown(id="region-filter", options=[{"label": region, "value": region} for region in regions], value=[], multi=True, placeholder="All Regions")],
            className="filter-control region-control",
        ),
    ]
    if show_reset:
        filters.append(
            html.Div([html.Label("Data"), html.Button("Change files", id="reset-data", className="reset-button", n_clicks=0)], className="filter-control reset-control")
        )
    return html.Main(
        [
            html.Div(filters, className="filters"),
            html.Section([html.Div("1", className="section-number"), html.H2("What happened?"), html.Div("Overall results", className="section-kicker"), _targets_strip(targets), html.Div(_cards(OVERALL_CARDS), className="kpi-grid")], className="dashboard-section"),
            html.Section([html.Div("2", className="section-number"), html.H2("Where is the funnel leaking?"), html.Div("Funnel diagnosis", className="section-kicker"), html.Div([dcc.Graph(id="overall-funnel", config={"displayModeBar": False}), dcc.Graph(id="paid-funnel", config={"displayModeBar": False}), dcc.Graph(id="conversion-trend", config={"displayModeBar": False})], className="three-column")], className="dashboard-section"),
            html.Section([html.Div("3", className="section-number"), html.H2("Which source contributes the most?"), html.Div("Channel contribution", className="section-kicker"), html.Div([dcc.Graph(id="traffic-share", config={"displayModeBar": False}), dcc.Graph(id="lead-share", config={"displayModeBar": False}), dcc.Graph(id="mql-share", config={"displayModeBar": False})], className="three-column")], className="dashboard-section"),
            html.Section([html.Div("4", className="section-number"), html.H2("Is the paid media worth it?"), html.Div("Paid media efficiency", className="section-kicker"), html.Div([html.Div(_cards(PAID_CARDS), className="kpi-grid"), dcc.Graph(id="efficiency-trend", config={"displayModeBar": False})], className="efficiency-block")], className="dashboard-section"),
            html.Section([html.Div("5", className="section-number"), html.H2("Performance diagnosis"), html.Div("Region and day diagnosis", className="section-kicker"), dcc.Graph(id="region-heatmap", config={"displayModeBar": False})], className="dashboard-section"),
        ],
        className="content",
    )


def build_layout(regions, min_date=None, max_date=None, start_date=None, preloaded=False, reset=False, data_key=None, targets=None):
    """页面外壳：header + 上传页 + dashboard 容器。

    `preloaded=True`（服务端已指定数据目录）时直接渲染 dashboard 并跳过上传页；
    前端上传模式下 dashboard 由上传回调按需填充。
    `targets` 只是渲染时的初始值，真正的持久化由 `target-store`（localStorage）负责。
    """
    return html.Div(
        [
            dcc.Store(id="data-key", data=data_key),
            # storage_type="local"：浏览器记住使用者填过的目标值；data 必须留空，
            # 否则页面每次加载都会把默认值写回 localStorage，覆盖已保存的值
            dcc.Store(id="target-store", storage_type="local"),
            html.Header(
                [
                    html.Div([html.Div("▮▮▮", className="brand-mark"), html.Div([html.H1("Digital Marketing KPI Dashboard"), html.P("Daily performance overview")])], className="brand"),
                    html.Div([html.Div("Data refresh", className="refresh-label"), html.Div(id="data-status", className="refresh-value")], className="data-status"),
                ],
                className="topbar",
            ),
            html.Div(
                [
                    html.Div(id="upload-gate", children=None if preloaded else build_upload_gate(), style={"display": "none"} if preloaded else {}),
                    html.Div(id="dashboard-root", children=build_dashboard(regions, min_date, max_date, start_date, show_reset=reset, targets=targets) if preloaded else None),
                ],
                className="body-shell",
            ),
        ],
        className="app-shell",
    )
