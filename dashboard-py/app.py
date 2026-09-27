from __future__ import annotations

import argparse
from datetime import timedelta

from dash import Dash, Input, Output

from charts import make_conversion_trend_figure, make_funnel_figure, make_heatmap_figure, make_source_donut_figure, make_spend_revenue_figure
from config import resolve_data_dir
from data_loader import load_folder
from layout import build_layout
from metrics import compute_daily_trends, compute_funnel, compute_kpis, compute_region_heatmap, compute_source_share


def _format_value(name, value):
    if value is None:
        return "N/A"
    if name in {"all_revenue", "ad_spend", "cost_per_lead", "cost_per_mql"}:
        return f"${value:,.0f}"
    if name == "roas":
        return f"{value:.1f}x"
    return f"{value:,.0f}"


def create_app(data_dir=None):
    bundle = load_folder(data_dir or resolve_data_dir(None))
    all_dates = []
    for frame in bundle.tables.values():
        if not frame.empty:
            all_dates.extend(frame["date"].dropna().tolist())
    min_date = min(all_dates).date() if all_dates else None
    max_date = max(all_dates).date() if all_dates else None
    start_date = max_date - timedelta(days=29) if max_date else None
    regions = sorted({region for frame in bundle.tables.values() for region in frame.get("region", []).dropna().unique()})

    app = Dash(__name__, title="Digital Marketing KPI Dashboard")
    app.layout = build_layout(regions, min_date, max_date, start_date)

    output_ids = [
        Output(f"kpi-{name.replace('_', '-')}", "children") for name in ["organic_traffic", "all_traffic", "all_leads", "all_mqls", "all_sqls", "all_revenue", "ad_spend", "cost_per_lead", "cost_per_mql", "roas"]
    ] + [Output(f"delta-{name.replace('_', '-')}", "children") for name in ["organic_traffic", "all_traffic", "all_leads", "all_mqls", "all_sqls", "all_revenue", "ad_spend", "cost_per_lead", "cost_per_mql", "roas"]] + [Output("data-status", "children"), Output("overall-funnel", "figure"), Output("paid-funnel", "figure"), Output("conversion-trend", "figure"), Output("traffic-share", "figure"), Output("lead-share", "figure"), Output("mql-share", "figure"), Output("efficiency-trend", "figure"), Output("region-heatmap", "figure")]

    @app.callback(output_ids, Input("date-range", "start_date"), Input("date-range", "end_date"), Input("region-filter", "value"))
    def update_dashboard(start, end, selected_regions):
        if not start or not end:
            start, end = start_date, max_date
        date_range = (start, end)
        regions_value = selected_regions or []
        kpis = compute_kpis(bundle, date_range, regions_value)
        trend = compute_daily_trends(bundle, date_range, regions_value)
        previous_start = (trend["date"].min() - timedelta(days=1)).date() if not trend.empty else start
        previous = compute_kpis(bundle, (previous_start, previous_start), regions_value)
        names = ["organic_traffic", "all_traffic", "all_leads", "all_mqls", "all_sqls", "all_revenue", "ad_spend", "cost_per_lead", "cost_per_mql", "roas"]
        values = [_format_value(name, kpis.get(name)) for name in names]
        deltas = []
        for name in names:
            current, prior = kpis.get(name), previous.get(name)
            change = None if current is None or prior in (None, 0) else (current - prior) / prior
            deltas.append("N/A" if change is None else f"{'▲' if change >= 0 else '▼'} {abs(change):.1%} vs prior day")
        diagnostics = f"{len(bundle.tables)} table types · {sum(1 for d in bundle.diagnostics if d.level == 'error')} errors · {max_date or 'no dates'}"
        return values + deltas + [diagnostics, make_funnel_figure(compute_funnel(bundle, date_range, regions_value), "Overall Funnel"), make_funnel_figure(compute_funnel(bundle, date_range, regions_value, paid=True), "Paid Funnel"), make_conversion_trend_figure(trend), make_source_donut_figure(compute_source_share(bundle, date_range, regions_value, "traffic"), "Traffic Source Share", _format_value("all_traffic", kpis["all_traffic"])), make_source_donut_figure(compute_source_share(bundle, date_range, regions_value, "leads"), "Leads Source Share", _format_value("all_leads", kpis["all_leads"])), make_source_donut_figure(compute_source_share(bundle, date_range, regions_value, "mqls"), "MQLs Source Share", _format_value("all_mqls", kpis["all_mqls"])), make_spend_revenue_figure(trend), make_heatmap_figure(compute_region_heatmap(bundle, date_range, regions_value), "MQL Conversion by Region")]

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    create_app(args.data_dir).run(debug=True, host=args.host, port=args.port)
