import pandas as pd

from data_loader import DataBundle
from metrics import compute_daily_trends, compute_funnel, compute_kpis, compute_region_heatmap, compute_source_share, safe_ratio


def sample_bundle():
    return DataBundle(
        tables={
            "traffic": pd.DataFrame(
                [
                    ["2026-09-01", "Brazil", "Organic Search", "organic", 10],
                    ["2026-09-01", "Brazil", "Paid Search", "paid", 20],
                    ["2026-09-02", "Brazil", "Organic Video", "organic", 12],
                ],
                columns=["date", "region", "source", "source_class", "sessions"],
            ).assign(date=lambda frame: pd.to_datetime(frame["date"])),
            "leads": pd.DataFrame(
                [
                    ["2026-09-01", "Brazil", "1", "Lead", "Paid Search", "paid"],
                    ["2026-09-01", "Brazil", "2", "Marketing Qualified Lead", "Paid Search", "paid"],
                    ["2026-09-02", "Brazil", "3", "Sales Qualified Lead", "Organic Search", "organic"],
                ],
                columns=["date", "region", "record_id", "lifecycle_stage", "source", "source_class"],
            ).assign(date=lambda frame: pd.to_datetime(frame["date"])),
            "deals": pd.DataFrame(
                [
                    ["2026-09-01", "Brazil", "d1", "Closed Won", 600, "Paid Search", "paid"],
                    ["2026-09-02", "Brazil", "d2", "Closed Won", 400, "Organic Search", "organic"],
                ],
                columns=["date", "region", "record_id", "deal_stage", "amount", "source", "source_class"],
            ).assign(date=lambda frame: pd.to_datetime(frame["date"])),
            "ad_cost": pd.DataFrame(
                [["2026-09-01", "Brazil", 60], ["2026-09-02", "Brazil", 40]],
                columns=["date", "region", "cost"],
            ).assign(date=lambda frame: pd.to_datetime(frame["date"])),
        },
        diagnostics=[],
    )


def test_compute_kpis_uses_business_definitions():
    result = compute_kpis(sample_bundle(), ("2026-09-01", "2026-09-02"), ["Brazil"])

    assert result["organic_traffic"] == 22
    assert result["all_traffic"] == 42
    assert result["all_leads"] == 3
    assert result["all_mqls"] == 2
    assert result["all_sqls"] == 1
    assert result["all_customers"] == 0
    assert result["all_revenue"] == 1000
    assert result["ad_spend"] == 100
    assert result["paid_traffic"] == 20
    # Paid Leads 与 All Leads 用同一套生命周期集合，不再是「只算 Lead」
    assert result["paid_leads"] == 2
    assert result["paid_mqls"] == 1
    assert result["paid_sqls"] == 0
    assert result["paid_customers"] == 0
    assert result["paid_revenue"] == 600
    assert result["cost_per_lead"] == 50
    assert result["cost_per_mql"] == 100
    assert result["roas"] == 6


def test_lead_counts_exclude_subscriber_and_blank_stages():
    """口径表的 All Leads 只认 Lead / MQL / SQL / Customer 四个取值，Subscriber 与空值不算。"""
    bundle = sample_bundle()
    bundle.tables["leads"] = pd.DataFrame(
        [
            ["2026-09-01", "Brazil", "1", "Lead", "Paid Search", "paid"],
            ["2026-09-01", "Brazil", "2", "Subscriber", "Paid Search", "paid"],
            ["2026-09-01", "Brazil", "3", "", "Organic Search", "organic"],
            ["2026-09-01", "Brazil", "4", "Customer", "Organic Search", "organic"],
        ],
        columns=["date", "region", "record_id", "lifecycle_stage", "source", "source_class"],
    ).assign(date=lambda frame: pd.to_datetime(frame["date"]))

    result = compute_kpis(bundle, ("2026-09-01", "2026-09-02"), ["Brazil"])

    assert result["all_leads"] == 2
    assert result["all_mqls"] == 1
    assert result["all_sqls"] == 1
    assert result["all_customers"] == 1
    assert result["paid_customers"] == 0


def test_paid_customers_and_paid_revenue_follow_the_spec():
    bundle = sample_bundle()
    bundle.tables["leads"] = pd.DataFrame(
        [
            ["2026-09-01", "Brazil", "1", "Customer", "Paid Search", "paid"],
            ["2026-09-01", "Brazil", "2", "Customer", "Organic Search", "organic"],
            ["2026-09-01", "Brazil", "3", "Sales Qualified Lead", "Paid Search", "paid"],
        ],
        columns=["date", "region", "record_id", "lifecycle_stage", "source", "source_class"],
    ).assign(date=lambda frame: pd.to_datetime(frame["date"]))

    result = compute_kpis(bundle, ("2026-09-01", "2026-09-02"), ["Brazil"])

    assert result["paid_customers"] == 1
    assert result["paid_revenue"] == 600
    assert result["roas"] == 6


def test_ratio_returns_none_for_zero_denominator():
    assert safe_ratio(10, 0) is None


def test_daily_trends_keep_complete_columns_when_filtered_table_is_empty():
    bundle = sample_bundle()
    bundle.tables["deals"] = bundle.tables["deals"][bundle.tables["deals"]["region"].eq("Canada")]

    trend = compute_daily_trends(bundle, ("2026-09-01", "2026-09-02"), ["Canada"])

    assert {"all_customers", "all_revenue", "paid_revenue", "customer_conversion"} <= set(trend.columns)
    assert trend["all_customers"].sum() == 0


def _bundle_with_timestamps():
    """贴近真实导出的形态：Create Date / Close Date 带时分秒，Record ID 重复。"""
    return DataBundle(
        tables={
            "traffic": pd.DataFrame(
                [["2026-09-01", "Brazil", "Organic Search", "organic", 10], ["2026-09-02", "Brazil", "Paid Search", "paid", 20]],
                columns=["date", "region", "source", "source_class", "sessions"],
            ).assign(date=lambda frame: pd.to_datetime(frame["date"])),
            "leads": pd.DataFrame(
                [
                    ["2026-09-01 08:30", "Brazil", "1", "Lead", "Paid Search", "paid"],
                    ["2026-09-02 09:15", "Brazil", "1", "Lead", "Paid Search", "paid"],
                    ["2026-09-02 23:50", "Brazil", "1", "Sales Qualified Lead", "Paid Search", "paid"],
                ],
                columns=["date", "region", "record_id", "lifecycle_stage", "source", "source_class"],
            ).assign(date=lambda frame: pd.to_datetime(frame["date"])),
            "deals": pd.DataFrame(
                [["2026-09-02 18:00", "Brazil", "d1", "Closed Won", 500, "Paid Search", "paid"]],
                columns=["date", "region", "record_id", "deal_stage", "amount", "source", "source_class"],
            ).assign(date=lambda frame: pd.to_datetime(frame["date"])),
            "ad_cost": pd.DataFrame(
                [["2026-09-01", "Hytera Brazil", 60, "USD"], ["2026-09-02", "Hytera Brazil", 40, "USD"]],
                columns=["date", "region", "cost", "currency"],
            ).assign(date=lambda frame: pd.to_datetime(frame["date"])),
        },
        diagnostics=[],
    )


def test_counts_rows_without_dedupe_when_record_id_repeats():
    """Record ID 被 Excel 存成科学计数法后失去精度，口径表的 COUNT 按行计数。"""
    kpis = compute_kpis(_bundle_with_timestamps(), ("2026-09-01", "2026-09-02"), ["Brazil"])

    assert _bundle_with_timestamps().tables["leads"]["record_id"].nunique() == 1
    assert kpis["all_leads"] == 3
    assert kpis["paid_leads"] == 3


def test_date_range_includes_records_with_time_on_the_end_date():
    kpis = compute_kpis(_bundle_with_timestamps(), ("2026-09-01", "2026-09-02"), ["Brazil"])

    assert kpis["all_revenue"] == 500


def test_all_revenue_sums_amount_without_stage_filter():
    """口径表的 All Revenue 直接对 Amount 求和，不再限定 Closed Won。"""
    bundle = sample_bundle()
    bundle.tables["deals"].loc[0, "deal_stage"] = "Negotiation"

    assert compute_kpis(bundle, ("2026-09-01", "2026-09-02"), ["Brazil"])["all_revenue"] == 1000


def test_daily_trends_match_kpis_when_dates_include_time():
    bundle = _bundle_with_timestamps()

    trend = compute_daily_trends(bundle, ("2026-09-01", "2026-09-02"), ["Brazil"])
    kpis = compute_kpis(bundle, ("2026-09-01", "2026-09-02"), ["Brazil"])

    assert trend["all_leads"].sum() == kpis["all_leads"]
    assert trend["all_mqls"].sum() == kpis["all_mqls"]
    assert trend["all_customers"].sum() == kpis["all_customers"]
    assert trend["all_revenue"].sum() == kpis["all_revenue"]
    assert trend["paid_revenue"].sum() == kpis["paid_revenue"]
    assert trend["date"].tolist() == [pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-02")]


def test_overall_funnel_reads_all_prefixed_kpis():
    bundle = _bundle_with_timestamps()

    funnel = compute_funnel(bundle, ("2026-09-01", "2026-09-02"), ["Brazil"])
    kpis = compute_kpis(bundle, ("2026-09-01", "2026-09-02"), ["Brazil"])

    assert funnel["stage"].tolist() == ["Traffic", "Leads", "MQLs", "SQLs", "Customers", "Revenue"]
    assert funnel["value"].tolist() == [
        kpis["all_traffic"],
        kpis["all_leads"],
        kpis["all_mqls"],
        kpis["all_sqls"],
        kpis["all_customers"],
        kpis["all_revenue"],
    ]
    assert funnel["value"].tolist() == [30, 3, 1, 1, 0, 500]


def test_paid_funnel_uses_stage_sets_so_it_never_inverts():
    funnel = compute_funnel(_bundle_with_timestamps(), ("2026-09-01", "2026-09-02"), ["Brazil"], paid=True)
    values = dict(zip(funnel["stage"], funnel["value"]))

    assert values["Customers"] <= values["SQLs"]
    assert values["SQLs"] <= values["MQLs"]
    assert values["MQLs"] == 1
    assert values["Revenue"] == 500


def test_ad_cost_follows_account_to_country_mapping():
    bundle = _bundle_with_timestamps()

    brazil = compute_kpis(bundle, ("2026-09-01", "2026-09-02"), ["Brazil"])
    mexico = compute_kpis(bundle, ("2026-09-01", "2026-09-02"), ["Mexico"])

    assert brazil["ad_spend"] == 100
    assert mexico["ad_spend"] == 0


def test_source_share_counts_rows_within_the_metric_stage_set():
    bundle = sample_bundle()

    leads_share = compute_source_share(bundle, ("2026-09-01", "2026-09-02"), ["Brazil"], "leads")
    mql_share = compute_source_share(bundle, ("2026-09-01", "2026-09-02"), ["Brazil"], "mqls")

    assert dict(zip(leads_share["source"], leads_share["value"])) == {"Paid Search": 2, "Organic Search": 1}
    assert dict(zip(mql_share["source"], mql_share["value"])) == {"Paid Search": 1, "Organic Search": 1}


def test_region_heatmap_groups_by_calendar_day():
    heatmap = compute_region_heatmap(_bundle_with_timestamps(), ("2026-09-01", "2026-09-02"), ["Brazil"])

    assert sorted(heatmap["date"].unique()) == [pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-02")]
    assert set(heatmap["region"]) == {"Brazil"}
