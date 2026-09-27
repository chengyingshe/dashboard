from __future__ import annotations

import plotly.graph_objects as go
import plotly.express as px


COLORS = {
    "navy": "#0b4f8a",
    "blue": "#2d8fe8",
    "teal": "#36b69c",
    "yellow": "#f4c542",
    "orange": "#f08a4b",
    "red": "#ee5b65",
    "purple": "#6857c9",
    "ink": "#12304a",
    "muted": "#6e8497",
    "grid": "#e7eef5",
}


def _base_figure(title: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        title={"text": title, "font": {"size": 15, "color": COLORS["ink"]}},
        paper_bgcolor="white",
        plot_bgcolor="white",
        height=330,
        margin={"l": 48, "r": 24, "t": 52, "b": 42},
        font={"family": "Inter, Arial, sans-serif", "color": COLORS["ink"]},
        legend={"orientation": "h", "y": 1.08, "x": 0},
    )
    return figure


def empty_figure(title: str, message: str) -> go.Figure:
    figure = _base_figure(title)
    figure.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font={"color": COLORS["muted"], "size": 14})
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    return figure


def make_funnel_figure(funnel_df, title: str) -> go.Figure:
    if funnel_df.empty:
        return empty_figure(title, "No data for the selected filters")
    figure = _base_figure(title)
    figure.add_trace(
        go.Funnel(
            y=funnel_df["stage"],
            x=funnel_df["value"],
            textinfo="label+value",
            marker={"color": [COLORS["blue"], COLORS["teal"], COLORS["yellow"], COLORS["orange"], COLORS["red"], COLORS["purple"]]},
            hovertemplate="%{y}: %{x:,.0f}<extra></extra>",
        )
    )
    return figure


def make_conversion_trend_figure(trend_df) -> go.Figure:
    if trend_df.empty:
        return empty_figure("Conversion Rate Trend", "No data for the selected filters")
    figure = _base_figure("Conversion Rate Trend")
    series = [("Traffic → Leads", "lead_conversion", COLORS["blue"]), ("Leads → MQLs", "mql_conversion", COLORS["teal"]), ("MQLs → SQLs", "sql_conversion", COLORS["orange"]), ("SQLs → Deals", "deal_conversion", COLORS["purple"])]
    for label, column, color in series:
        if column in trend_df:
            figure.add_trace(go.Scatter(x=trend_df["date"], y=trend_df[column], name=label, mode="lines+markers", line={"color": color, "width": 2}, connectgaps=False, hovertemplate="%{x|%b %d}: %{y:.1%}<extra>%{fullData.name}</extra>"))
    figure.update_yaxes(tickformat=".0%", rangemode="tozero", gridcolor=COLORS["grid"])
    figure.update_xaxes(gridcolor=COLORS["grid"])
    return figure


def make_source_donut_figure(source_df, title: str, center_label: str) -> go.Figure:
    if source_df.empty:
        return empty_figure(title, "No source data for the selected filters")
    frame = source_df.sort_values("value", ascending=False).copy()
    if len(frame) > 6:
        frame = frame.iloc[:5].copy()
        frame.loc[len(frame)] = {"source": "Other", "value": source_df.iloc[5:]["value"].sum()}
    figure = go.Figure(go.Pie(labels=frame["source"], values=frame["value"], hole=0.62, textinfo="percent", marker={"colors": [COLORS["blue"], COLORS["teal"], COLORS["yellow"], COLORS["orange"], COLORS["purple"], "#a8b7c5"]}, hovertemplate="%{label}: %{value:,.0f} (%{percent})<extra></extra>"))
    figure.update_layout(title={"text": title, "font": {"size": 15, "color": COLORS["ink"]}}, height=300, margin={"l": 24, "r": 24, "t": 52, "b": 24}, paper_bgcolor="white", showlegend=True, legend={"font": {"size": 10}})
    figure.add_annotation(text=f"<b>{center_label}</b>", x=0.5, y=0.5, showarrow=False, font={"size": 13, "color": COLORS["ink"]})
    return figure


def make_spend_revenue_figure(trend_df) -> go.Figure:
    if trend_df.empty:
        return empty_figure("Paid Media Spend vs Revenue", "No data for the selected filters")
    figure = _base_figure("Paid Media Spend vs Revenue")
    figure.add_bar(x=trend_df["date"], y=trend_df.get("ad_spend", 0), name="Investment", marker_color="#b8d5ee")
    figure.add_trace(go.Scatter(x=trend_df["date"], y=trend_df.get("paid_revenue", 0), name="Revenue", mode="lines+markers", line={"color": COLORS["navy"], "width": 2}, hovertemplate="%{x|%b %d}: $%{y:,.0f}<extra>Revenue</extra>"))
    figure.update_yaxes(gridcolor=COLORS["grid"], tickprefix="$", separatethousands=True)
    figure.update_xaxes(gridcolor=COLORS["grid"])
    return figure


def make_heatmap_figure(heatmap_df, title: str) -> go.Figure:
    if heatmap_df.empty:
        return empty_figure(title, "No regional data for the selected filters")
    matrix = heatmap_df.pivot(index="region", columns="date", values="value")
    figure = px.imshow(matrix, color_continuous_scale=[[0, "#f6c4c8"], [0.5, "#ffe58a"], [1, "#61c59a"]], zmin=0, zmax=1, aspect="auto", labels={"color": "Rate"})
    figure.update_layout(title={"text": title, "font": {"size": 15, "color": COLORS["ink"]}}, height=300, margin={"l": 72, "r": 24, "t": 52, "b": 42}, paper_bgcolor="white", plot_bgcolor="white")
    figure.update_traces(texttemplate="%{z:.0%}", hovertemplate="%{y} · %{x|%b %d}: %{z:.1%}<extra></extra>")
    return figure
