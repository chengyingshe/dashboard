from __future__ import annotations

from dash import dcc, html


def _card(title: str, value_id: str, delta_id: str) -> html.Div:
    return html.Div(
        [html.Div(title, className="kpi-title"), html.Div(id=value_id, className="kpi-value"), html.Div(id=delta_id, className="kpi-delta")],
        className="kpi-card",
    )


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


def _cards(specs):
    return [_card(title, f"kpi-{name.replace('_', '-')}", f"delta-{name.replace('_', '-')}") for title, name in specs]


def build_layout(regions, min_date=None, max_date=None, start_date=None):
    return html.Div(
        [
            html.Header(
                [
                    html.Div([html.Div("▮▮▮", className="brand-mark"), html.Div([html.H1("Digital Marketing KPI Dashboard"), html.P("Daily performance overview")])], className="brand"),
                    html.Div([html.Div("Data refresh", className="refresh-label"), html.Div(id="data-status", className="refresh-value")], className="data-status"),
                ],
                className="topbar",
            ),
            html.Main(
                [
                    html.Div(
                        [
                            html.Div([html.Label("Date Range"), dcc.DatePickerRange(id="date-range", min_date_allowed=min_date, max_date_allowed=max_date, start_date=start_date or min_date, end_date=max_date, display_format="MMM D, YYYY")], className="filter-control"),
                            html.Div([html.Label("Region"), dcc.Dropdown(id="region-filter", options=[{"label": region, "value": region} for region in regions], value=[], multi=True, placeholder="All Regions")], className="filter-control region-control"),
                        ],
                        className="filters",
                    ),
                    html.Section([html.Div("1", className="section-number"), html.H2("What happened?"), html.Div("Overall results", className="section-kicker"), html.Div(_cards(OVERALL_CARDS), className="kpi-grid")], className="dashboard-section"),
                    html.Section([html.Div("2", className="section-number"), html.H2("Where is the funnel leaking?"), html.Div("Funnel diagnosis", className="section-kicker"), html.Div([dcc.Graph(id="overall-funnel", config={"displayModeBar": False}), dcc.Graph(id="paid-funnel", config={"displayModeBar": False}), dcc.Graph(id="conversion-trend", config={"displayModeBar": False})], className="three-column")], className="dashboard-section"),
                    html.Section([html.Div("3", className="section-number"), html.H2("Which source contributes the most?"), html.Div("Channel contribution", className="section-kicker"), html.Div([dcc.Graph(id="traffic-share", config={"displayModeBar": False}), dcc.Graph(id="lead-share", config={"displayModeBar": False}), dcc.Graph(id="mql-share", config={"displayModeBar": False})], className="three-column")], className="dashboard-section"),
                    html.Section([html.Div("4", className="section-number"), html.H2("Is the paid media worth it?"), html.Div("Paid media efficiency", className="section-kicker"), html.Div([html.Div(_cards(PAID_CARDS), className="kpi-grid"), dcc.Graph(id="efficiency-trend", config={"displayModeBar": False})], className="efficiency-block")], className="dashboard-section"),
                    html.Section([html.Div("5", className="section-number"), html.H2("Performance diagnosis"), html.Div("Region and day diagnosis", className="section-kicker"), dcc.Graph(id="region-heatmap", config={"displayModeBar": False})], className="dashboard-section"),
                ],
                className="content",
            ),
        ],
        className="app-shell",
    )
