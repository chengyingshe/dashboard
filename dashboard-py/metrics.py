from __future__ import annotations

from typing import Iterable

import pandas as pd

from config import AD_ACCOUNT_REGION_MAP
from data_loader import DataBundle


# 生命周期分档：口径表按「Lifecycle Stage 取值集合」计数，Subscriber 与空值不属于任何一档
LEAD_STAGES = {"Lead", "Marketing Qualified Lead", "Sales Qualified Lead", "Customer"}
MQL_STAGES = {"Marketing Qualified Lead", "Sales Qualified Lead", "Customer"}
SQL_STAGES = {"Sales Qualified Lead", "Customer"}
CUSTOMER_STAGE = "Customer"

# 漏斗第 5 层统一用 Customers（Sheet1 的 All Customers / Paid Deals 同源）
FUNNEL_KEYS = {
    "all": ["all_traffic", "all_leads", "all_mqls", "all_sqls", "all_customers", "all_revenue"],
    "paid": ["paid_traffic", "paid_leads", "paid_mqls", "paid_sqls", "paid_deals", "paid_revenue"],
}
FUNNEL_LABELS = ["Traffic", "Leads", "MQLs", "SQLs", "Customers", "Revenue"]

# 来源占比图支持的口径
SOURCE_SHARE_METRICS = {"traffic": "traffic", "leads": "leads", "mqls": "leads", "customers": "leads"}


def safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator in (0, None) or pd.isna(denominator):
        return None
    return numerator / denominator


def _stage_mask(frame: pd.DataFrame, stages: Iterable[str] | str) -> pd.Series:
    """生命周期筛选：传集合做 isin，传字符串做等值。"""
    if isinstance(stages, str):
        return frame["lifecycle_stage"].eq(stages)
    return frame["lifecycle_stage"].isin(set(stages))


def _count_rows(frame: pd.DataFrame | None, mask=None) -> int:
    """按行计数。

    口径表里所有 COUNT 都是「行数」，不做跨行去重：Leads 的 Record ID 被 Excel 存成科学计数法
    后已丢精度，无法作为去重键；Deals 同理按行计入。
    """
    if frame is None or frame.empty:
        return 0
    if mask is None:
        return int(len(frame))
    return int(len(frame[mask]))


def _sum_column(frame: pd.DataFrame | None, column: str, mask=None) -> float:
    if frame is None or frame.empty:
        return 0.0
    if mask is None:
        return float(frame[column].sum())
    return float(frame.loc[mask, column].sum())


def _days(frame: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(frame["date"]).dt.normalize()


def _selected(frame: pd.DataFrame | None, date_range, regions: Iterable[str]) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    start = pd.to_datetime(date_range[0]).normalize()
    end = pd.to_datetime(date_range[1]).normalize() + pd.Timedelta(days=1)
    result = frame[(frame["date"] >= start) & (frame["date"] < end)].copy()
    regions = list(regions or [])
    if regions and "All Regions" not in regions:
        result = result[result["region"].isin(regions)]
    return result


def _selected_ad_cost(frame: pd.DataFrame | None, date_range, regions: Iterable[str]) -> pd.DataFrame:
    """广告花费按账户筛选：先按日期过滤，再经「账户 -> 国家」映射参与地区筛选。"""
    result = _selected(frame, date_range, [])
    if result.empty:
        return result
    regions = list(regions or [])
    if not regions or "All Regions" in regions:
        return result
    selected = set(regions)

    def matched(account):
        countries = AD_ACCOUNT_REGION_MAP.get(account)
        # 配置了映射走账户覆盖国家；没有配置时把该列当作普通地区名直接匹配
        return bool(selected & set(countries)) if countries else account in selected

    return result[result["region"].map(matched)]


def filter_bundle(bundle: DataBundle, date_range, regions) -> dict[str, pd.DataFrame]:
    tables = {}
    for name, frame in bundle.tables.items():
        if name == "ad_cost":
            tables[name] = _selected_ad_cost(frame, date_range, regions)
        else:
            tables[name] = _selected(frame, date_range, regions)
    return tables


def compute_kpis(bundle: DataBundle, date_range, regions) -> dict:
    tables = filter_bundle(bundle, date_range, regions)
    traffic = tables.get("traffic", pd.DataFrame())
    leads = tables.get("leads", pd.DataFrame())
    deals = tables.get("deals", pd.DataFrame())
    ad_cost = tables.get("ad_cost", pd.DataFrame())

    paid = leads["source_class"].eq("paid") if not leads.empty else None
    paid_deals_mask = deals["source_class"].eq("paid") if not deals.empty else None

    def lead_count(stages):
        if leads.empty:
            return 0
        return _count_rows(leads, _stage_mask(leads, stages))

    def paid_lead_count(stages):
        if leads.empty:
            return 0
        return _count_rows(leads, paid & _stage_mask(leads, stages))

    paid_leads = paid_lead_count(LEAD_STAGES)
    paid_mqls = paid_lead_count(MQL_STAGES)
    paid_sqls = paid_lead_count(SQL_STAGES)
    paid_deals = paid_lead_count(CUSTOMER_STAGE)
    paid_revenue = _sum_column(deals, "amount", paid_deals_mask)
    ad_spend = _sum_column(ad_cost, "cost")

    return {
        "organic_traffic": int(_sum_column(traffic, "sessions", traffic["source_class"].eq("organic") if not traffic.empty else None)),
        "all_traffic": int(_sum_column(traffic, "sessions")),
        "all_leads": lead_count(LEAD_STAGES),
        "all_mqls": lead_count(MQL_STAGES),
        "all_sqls": lead_count(SQL_STAGES),
        "all_customers": lead_count(CUSTOMER_STAGE),
        "all_revenue": _sum_column(deals, "amount"),
        "ad_spend": ad_spend,
        "paid_traffic": int(_sum_column(traffic, "sessions", traffic["source_class"].eq("paid") if not traffic.empty else None)),
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
    keys = FUNNEL_KEYS["paid" if paid else "all"]
    values = [kpi.get(key, 0) for key in keys]
    rates = [None]
    for index in range(1, len(values)):
        # 最后一层 Revenue 是金额，与成交数不同量纲，算比率没有意义
        rates.append(None if index == len(values) - 1 else safe_ratio(values[index], values[index - 1]))
    return pd.DataFrame({"stage": FUNNEL_LABELS, "value": values, "conversion": rates})


def compute_daily_trends(bundle: DataBundle, date_range, regions) -> pd.DataFrame:
    tables = filter_bundle(bundle, date_range, regions)
    dates = pd.date_range(pd.to_datetime(date_range[0]).normalize(), pd.to_datetime(date_range[1]).normalize(), freq="D")
    result = pd.DataFrame({"date": dates})

    traffic = tables.get("traffic", pd.DataFrame())
    if not traffic.empty:
        frame = traffic.assign(_day=_days(traffic))
        traffic_daily = frame.groupby("_day").agg(
            all_traffic=("sessions", "sum"),
            organic_traffic=("sessions", lambda values: values[frame.loc[values.index, "source_class"].eq("organic")].sum()),
            paid_traffic=("sessions", lambda values: values[frame.loc[values.index, "source_class"].eq("paid")].sum()),
        )
        result = result.merge(traffic_daily.rename_axis("date"), on="date", how="left")

    leads = tables.get("leads", pd.DataFrame())
    if not leads.empty:
        frame = leads.assign(_day=_days(leads))
        paid = frame["source_class"].eq("paid")

        def daily(mask):
            return frame[mask].groupby("_day").size()

        leads_daily = pd.DataFrame({"all_leads": daily(_stage_mask(frame, LEAD_STAGES))})
        leads_daily["all_mqls"] = daily(_stage_mask(frame, MQL_STAGES))
        leads_daily["all_sqls"] = daily(_stage_mask(frame, SQL_STAGES))
        leads_daily["all_customers"] = daily(_stage_mask(frame, CUSTOMER_STAGE))
        leads_daily["paid_leads"] = daily(paid & _stage_mask(frame, LEAD_STAGES))
        leads_daily["paid_mqls"] = daily(paid & _stage_mask(frame, MQL_STAGES))
        leads_daily["paid_sqls"] = daily(paid & _stage_mask(frame, SQL_STAGES))
        leads_daily["paid_deals"] = daily(paid & _stage_mask(frame, CUSTOMER_STAGE))
        result = result.merge(leads_daily.rename_axis("date"), on="date", how="left")

    deals = tables.get("deals", pd.DataFrame())
    if not deals.empty:
        frame = deals.assign(_day=_days(deals))
        paid = frame["source_class"].eq("paid")
        deal_daily = frame.groupby("_day").agg(all_revenue=("amount", "sum")).rename_axis("date")
        paid_daily = frame[paid].groupby("_day").agg(paid_revenue=("amount", "sum")).rename_axis("date")
        result = result.merge(deal_daily, on="date", how="left").merge(paid_daily, on="date", how="left")

    ad_cost = tables.get("ad_cost", pd.DataFrame())
    if not ad_cost.empty:
        spend = ad_cost.assign(_day=_days(ad_cost)).groupby("_day")["cost"].sum().rename("ad_spend").rename_axis("date")
        result = result.merge(spend, on="date", how="left")

    required_numeric = [
        "all_traffic", "organic_traffic", "paid_traffic", "all_leads", "all_mqls", "all_sqls", "all_customers",
        "paid_leads", "paid_mqls", "paid_sqls", "paid_deals", "all_revenue", "paid_revenue", "ad_spend",
    ]
    for column in required_numeric:
        if column not in result:
            result[column] = 0
    for column in result.columns[1:]:
        result[column] = result[column].fillna(0)
    result["lead_conversion"] = result.apply(lambda row: safe_ratio(row["all_leads"], row["all_traffic"]), axis=1)
    result["mql_conversion"] = result.apply(lambda row: safe_ratio(row["all_mqls"], row["all_leads"]), axis=1)
    result["sql_conversion"] = result.apply(lambda row: safe_ratio(row["all_sqls"], row["all_mqls"]), axis=1)
    result["customer_conversion"] = result.apply(lambda row: safe_ratio(row["all_customers"], row["all_sqls"]), axis=1)
    return result


def compute_source_share(bundle: DataBundle, date_range, regions, metric: str) -> pd.DataFrame:
    table_name = SOURCE_SHARE_METRICS[metric]
    frame = filter_bundle(bundle, date_range, regions).get(table_name, pd.DataFrame())
    if frame.empty:
        return pd.DataFrame(columns=["source", "value"])
    if table_name == "traffic":
        return frame.groupby("source")["sessions"].sum().reset_index(name="value")
    if metric == "mqls":
        frame = frame[_stage_mask(frame, MQL_STAGES)]
    elif metric == "customers":
        frame = frame[_stage_mask(frame, CUSTOMER_STAGE)]
    else:
        frame = frame[_stage_mask(frame, LEAD_STAGES)]
    return frame.groupby("source").size().reset_index(name="value")


def compute_region_heatmap(bundle: DataBundle, date_range, regions) -> pd.DataFrame:
    leads = filter_bundle(bundle, date_range, regions).get("leads", pd.DataFrame())
    if leads.empty:
        return pd.DataFrame(columns=["region", "date", "value"])
    frame = leads.assign(date=_days(leads))
    rows = []
    for (region, date), group in frame.groupby(["region", "date"]):
        mql = len(group[_stage_mask(group, MQL_STAGES)])
        rows.append({"region": region, "date": date, "value": safe_ratio(mql, len(group))})
    return pd.DataFrame(rows)
