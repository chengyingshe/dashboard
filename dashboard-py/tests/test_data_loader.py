import csv

import pandas as pd

from data_loader import load_folder


def write_csv(path, headers, rows=None):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows or [])


def test_identifies_tables_by_columns(tmp_path):
    write_csv(tmp_path / "random-a.csv", ["Date", "Region", "Session default channel group", "Sessions"])
    write_csv(tmp_path / "random-b.csv", ["Record ID", "Create Date", "Lifecycle Stage", "Original Traffic Source", "Region"])
    write_csv(tmp_path / "random-c.csv", ["Record ID", "Close Date", "Deal Stage", "Amount", "Original Traffic Source", "Region"])
    write_csv(tmp_path / "random-d.csv", ["Day", "Currency code", "Cost", "Region"])

    bundle = load_folder(tmp_path)

    assert set(bundle.tables) == {"traffic", "leads", "deals", "ad_cost"}


def test_scans_nested_csv_and_classifies_source_case_insensitively(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    write_csv(
        nested / "traffic.csv",
        ["Date", "Region", "Session default channel group", "Sessions"],
        [
            ["2026-09-01", "Brazil", "Organic Search", "10"],
            ["2026-09-01", "Brazil", "paid social", "5"],
        ],
    )

    bundle = load_folder(tmp_path)

    assert set(bundle.tables["traffic"]["source_class"]) == {"organic", "paid"}


def test_normalizes_account_level_ad_cost_and_ignores_traffic_total(tmp_path):
    write_csv(
        tmp_path / "traffic.csv",
        ["Date", "Region", "Session default channel group", "Sessions"],
        [["", "", "", "2194968"], ["20260901", "Canada", "Organic Search", "10"]],
    )
    write_csv(
        tmp_path / "cost.csv",
        ["Account name", "Day", "Currency code", "Cost"],
        [["Canada", "2026/09/01", "USD", "12.5"]],
    )

    bundle = load_folder(tmp_path)

    assert len(bundle.tables["traffic"]) == 1
    assert bundle.tables["ad_cost"].iloc[0]["region"] == "Canada"
    assert bundle.tables["ad_cost"].iloc[0]["cost"] == 12.5


def test_parses_compact_numeric_dates_as_calendar_dates(tmp_path):
    write_csv(
        tmp_path / "traffic.csv",
        ["Date", "Region", "Session default channel group", "Sessions"],
        [["20260101", "Brazil", "Organic Search", "10"]],
    )

    bundle = load_folder(tmp_path)

    assert bundle.tables["traffic"].iloc[0]["date"] == pd.Timestamp("2026-01-01")


def test_dates_are_truncated_to_calendar_days(tmp_path):
    """HubSpot 导出的 Create Date / Close Date 带时分秒，必须归一到日历日。"""
    write_csv(
        tmp_path / "leads.csv",
        ["Record ID", "Create Date", "Lifecycle Stage", "Original Traffic Source", "Region", "Email"],
        [["1", "2026-09-01 08:30", "Lead", "Paid Search", "Brazil", "a@x.com"]],
    )
    write_csv(
        tmp_path / "deals.csv",
        ["Record ID", "Close Date", "Deal Stage", "Amount", "Original Traffic Source", "Region"],
        [["d1", "2026-09-02 17:45", "Closed Won", "100", "Paid Search", "Brazil"]],
    )

    bundle = load_folder(tmp_path)

    assert bundle.tables["leads"]["date"].iloc[0] == pd.Timestamp("2026-09-01")
    assert bundle.tables["deals"]["date"].iloc[0] == pd.Timestamp("2026-09-02")


def test_source_class_matches_organic_and_paid_prefixes_only(tmp_path):
    """口径表要求来源以 Organic / Paid 开头才归类，中间出现关键词的来源不算。"""
    write_csv(
        tmp_path / "traffic.csv",
        ["Date", "Region", "Session default channel group", "Sessions"],
        [
            ["2026-09-01", "Brazil", "Organic Shopping", "1"],
            ["2026-09-01", "Brazil", "Paid Other", "2"],
            ["2026-09-01", "Brazil", "Display", "3"],
            ["2026-09-01", "Brazil", "Other Campaigns", "4"],
            ["2026-09-01", "Brazil", "Unassigned", "5"],
        ],
    )

    frame = load_folder(tmp_path).tables["traffic"]
    classes = dict(zip(frame["source"], frame["source_class"]))

    assert classes["Organic Shopping"] == "organic"
    assert classes["Paid Other"] == "paid"
    assert classes["Display"] == "other"
    assert classes["Other Campaigns"] == "other"
    assert classes["Unassigned"] == "other"
