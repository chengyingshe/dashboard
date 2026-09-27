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
