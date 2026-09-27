from __future__ import annotations

from typing import Iterable

import pandas as pd

from data_loader import DataBundle


MQL_STAGES = {"Marketing Qualified Lead", "Sales Qualified Lead", "Customer"}
SQL_STAGES = {"Sales Qualified Lead", "Customer"}


def safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator in (0, None) or pd.isna(denominator):
        return None
    return numerator / denominator


def _selected(frame: pd.DataFrame | None, date_range, regions: Iterable[str]) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    result = frame[frame["date"].between(start, end)].copy()
    regions = list(regions or [])
    if regions and "All Regions" not in regions:
        result = result[result["region"].isin(regions)]
    return result


def filter_bundle(bundle: DataBundle, date_range, regions) -> dict[str, pd.DataFrame]:
    return {name: _selected(frame, date_range, regions) for name, frame in bundle.tables.items()}


def _count_records(frame, mask=None) -> int:
    if frame.empty:
        return 0
    if mask is not None:
        frame = frame[mask]
    return int(frame["record_id"].nunique())


def compute_kpis(bundle: DataBundle, date_range, regions) -> dict:
    tables = filter_bundle(bundle, date_range, regions)
    traffic = tables.get("traffic", pd.DataFrame())
    leads = tables.get("leads", pd.DataFrame())
    deals = tables.get("deals", pd.DataFrame())
    ad_cost = tables.get("ad_cost", pd.DataFrame())

    mqls = _count_records(leads, leads["lifecycle_stage"].isin(MQL_STAGES) if not leads.empty else None)
    sqls = _count_records(leads, leads["lifecycle_stage"].isin(SQL_STAGES) if not leads.empty else None)
    closed = deals["deal_stage"].str.casefold().eq("closed won") if not deals.empty else None
    paid_leads = _count_records(
        leads,
        (leads["source_class"].eq("paid") & leads["lifecycle_stage"].eq("Lead")) if not leads.empty else None,
    )
    paid_mqls = _count_records(
        leads,
        (leads["source_class"].eq("paid") & leads["lifecycle_stage"].eq("Marketing Qualified Lead"))
        if not leads.empty
        else None,
    )
    paid_sqls = _count_records(
        leads,
        (leads["source_class"].eq("paid") & leads["lifecycle_stage"].eq("Sales Qualified Lead"))
        if not leads.empty
        else None,
    )
    paid_deals = int(deals.loc[closed & deals["source_class"].eq("paid"), "record_id"].nunique()) if not deals.empty else 0
    paid_revenue = float(deals.loc[closed & deals["source_class"].eq("paid"), "amount"].sum()) if not deals.empty else 0.0
    ad_spend = float(ad_cost["cost"].sum()) if not ad_cost.empty else 0.0
    revenue = float(deals.loc[closed, "amount"].sum()) if not deals.empty else 0.0

    return {
        "organic_traffic": int(traffic.loc[traffic["source_class"].eq("organic"), "sessions"].sum()) if not traffic.empty else 0,
        "all_traffic": int(traffic["sessions"].sum()) if not traffic.empty else 0,
        "all_leads": _count_records(leads),
        "all_mqls": mqls,
        "all_sqls": sqls,
        "all_deals": int(deals.loc[closed, "record_id"].nunique()) if not deals.empty else 0,
        "all_revenue": revenue,
        "ad_spend": ad_spend,
        "paid_traffic": int(traffic.loc[traffic["source_class"].eq("paid"), "sessions"].sum()) if not traffic.empty else 0,
        "paid_leads": paid_leads,
        "paid_mqls": paid_mqls,
        "paid_sqls": paid_sqls,
        "paid_deals": paid_deals,
        "paid_revenue": paid_revenue,
        "cost_per_lead": safe_ratio(ad_spend, paid_leads),
        "cost_per_mql": safe_ratio(ad_spend, paid_mqls),
        "roas": safe_ratio(paid_revenue, ad_spend),
    }


def compute_funnel(bundle: DataBundle, date_range, regions, paid=False) -> pd.DataFrame:
    kpi = compute_kpis(bundle, date_range, regions)
    prefix = "paid_" if paid else ""
    keys = [f"{prefix}traffic", f"{prefix}leads", f"{prefix}mqls", f"{prefix}sqls", f"{prefix}deals", f"{prefix}revenue"]
    labels = ["Traffic", "Leads", "MQLs", "SQLs", "Deals", "Revenue"]
    values = [kpi.get(key, 0) for key in keys]
    rates = [None] + [safe_ratio(values[index], values[index - 1]) for index in range(1, len(values))]
    return pd.DataFrame({"stage": labels, "value": values, "conversion": rates})


def compute_daily_trends(bundle: DataBundle, date_range, regions) -> pd.DataFrame:
    tables = filter_bundle(bundle, date_range, regions)
    dates = pd.date_range(date_range[0], date_range[1], freq="D")
    result = pd.DataFrame({"date": dates})
    traffic = tables.get("traffic", pd.DataFrame())
    if not traffic.empty:
        traffic_daily = traffic.groupby("date").agg(
            all_traffic=("sessions", "sum"),
            organic_traffic=("sessions", lambda values: values[traffic.loc[values.index, "source_class"].eq("organic")].sum()),
            paid_traffic=("sessions", lambda values: values[traffic.loc[values.index, "source_class"].eq("paid")].sum()),
        )
        result = result.merge(traffic_daily, on="date", how="left")
    leads = tables.get("leads", pd.DataFrame())
    if not leads.empty:
        leads_daily = leads.groupby("date").agg(all_leads=("record_id", "nunique"))
        leads_daily["all_mqls"] = leads[leads["lifecycle_stage"].isin(MQL_STAGES)].groupby("date")["record_id"].nunique()
        leads_daily["all_sqls"] = leads[leads["lifecycle_stage"].isin(SQL_STAGES)].groupby("date")["record_id"].nunique()
        leads_daily["paid_leads"] = leads[leads["source_class"].eq("paid")].groupby("date")["record_id"].nunique()
        result = result.merge(leads_daily, on="date", how="left")
    deals = tables.get("deals", pd.DataFrame())
    if not deals.empty:
        closed = deals["deal_stage"].str.casefold().eq("closed won")
        deal_daily = deals[closed].groupby("date").agg(all_deals=("record_id", "nunique"), all_revenue=("amount", "sum"))
        paid = deals[closed & deals["source_class"].eq("paid")].groupby("date").agg(paid_deals=("record_id", "nunique"), paid_revenue=("amount", "sum"))
        result = result.merge(deal_daily, on="date", how="left").merge(paid, on="date", how="left")
    ad_cost = tables.get("ad_cost", pd.DataFrame())
    if not ad_cost.empty:
        result = result.merge(ad_cost.groupby("date")["cost"].sum().rename("ad_spend"), on="date", how="left")
    required_numeric = [
        "all_traffic", "organic_traffic", "paid_traffic", "all_leads", "all_mqls", "all_sqls",
        "paid_leads", "all_deals", "all_revenue", "paid_deals", "paid_revenue", "ad_spend",
    ]
    for column in required_numeric:
        if column not in result:
            result[column] = 0
    for column in result.columns[1:]:
        result[column] = result[column].fillna(0)
    result["lead_conversion"] = result.apply(lambda row: safe_ratio(row["all_leads"], row["all_traffic"]), axis=1)
    result["mql_conversion"] = result.apply(lambda row: safe_ratio(row["all_mqls"], row["all_leads"]), axis=1)
    result["sql_conversion"] = result.apply(lambda row: safe_ratio(row["all_sqls"], row["all_mqls"]), axis=1)
    result["deal_conversion"] = result.apply(lambda row: safe_ratio(row["all_deals"], row["all_sqls"]), axis=1)
    return result


def compute_source_share(bundle: DataBundle, date_range, regions, metric: str) -> pd.DataFrame:
    tables = filter_bundle(bundle, date_range, regions)
    table_name, value_column = {"traffic": ("traffic", "sessions"), "leads": ("leads", "record_id"), "mqls": ("leads", "record_id")} [metric]
    frame = tables.get(table_name, pd.DataFrame())
    if frame.empty:
        return pd.DataFrame(columns=["source", "value"])
    if metric == "mqls":
        frame = frame[frame["lifecycle_stage"].isin(MQL_STAGES)]
    return frame.groupby("source")[value_column].nunique() .reset_index(name="value") if value_column == "record_id" else frame.groupby("source")[value_column].sum().reset_index(name="value")


def compute_region_heatmap(bundle: DataBundle, date_range, regions, metric="mql_conversion") -> pd.DataFrame:
    trend = compute_daily_trends(bundle, date_range, [])
    leads = filter_bundle(bundle, date_range, regions).get("leads", pd.DataFrame())
    if leads.empty:
        return pd.DataFrame(columns=["region", "date", "value"])
    rows = []
    for (region, date), group in leads.groupby(["region", "date"]):
        mql = group[group["lifecycle_stage"].isin(MQL_STAGES)]["record_id"].nunique()
        leads_count = group["record_id"].nunique()
        rows.append({"region": region, "date": date, "value": safe_ratio(mql, leads_count)})
    return pd.DataFrame(rows)
