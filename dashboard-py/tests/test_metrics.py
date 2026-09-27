import pandas as pd

from data_loader import DataBundle
from metrics import compute_daily_trends, compute_kpis, safe_ratio


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
    assert result["all_leads"] == 3
    assert result["all_mqls"] == 2
    assert result["all_sqls"] == 1
    assert result["all_revenue"] == 1000
    assert result["ad_spend"] == 100
    assert result["paid_leads"] == 1
    assert result["paid_revenue"] == 600
    assert result["roas"] == 6


def test_ratio_returns_none_for_zero_denominator():
    assert safe_ratio(10, 0) is None


def test_daily_trends_keep_complete_columns_when_filtered_table_is_empty():
    bundle = sample_bundle()
    bundle.tables["deals"] = bundle.tables["deals"][bundle.tables["deals"]["region"].eq("Canada")]

    trend = compute_daily_trends(bundle, ("2026-09-01", "2026-09-02"), ["Canada"])

    assert {"all_deals", "all_revenue", "paid_revenue", "deal_conversion"} <= set(trend.columns)
    assert trend["all_deals"].sum() == 0
