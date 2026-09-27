import csv

import pandas as pd

from data_loader import load_folder, load_uploads


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


def test_blank_region_rows_are_kept_as_unassigned(tmp_path):
    """汇总表里的总量没有地区条件，空地区行不能整行丢弃。"""
    write_csv(
        tmp_path / "traffic.csv",
        ["Date", "Region", "Session default channel group", "Sessions"],
        [["20260101", "", "Unassigned", "7"], ["20260101", "Brazil", "Organic Search", "10"]],
    )

    bundle = load_folder(tmp_path)
    traffic = bundle.tables["traffic"]

    assert len(traffic) == 2
    assert set(traffic["region"]) == {"Unassigned", "Brazil"}
    assert traffic["sessions"].sum() == 17


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


def csv_bytes(headers, rows=None) -> bytes:
    lines = [",".join(headers)] + [",".join(str(cell) for cell in row) for row in (rows or [])]
    return ("\n".join(lines) + "\n").encode("utf-8")


TRAFFIC_HEADERS = ["Date", "Region", "Session default channel group", "Sessions"]
LEAD_HEADERS = ["Record ID", "Create Date", "Lifecycle Stage", "Original Traffic Source", "Region"]
DEAL_HEADERS = ["Record ID", "Close Date", "Deal Stage", "Amount", "Original Traffic Source", "Region"]


def upload_files(**slots) -> list[tuple[str, str, bytes]]:
    """按上传页的形态构造 (slot, filename, content) 三元组。"""
    files = []
    for slot, uploads in slots.items():
        for name, content in uploads:
            files.append((slot, name, content))
    return files


def test_load_uploads_merges_several_files_of_the_same_slot():
    """Ads Cost 可能拆成多张表（含中文文件名的加拿大表），合并成一张。"""
    files = upload_files(
        traffic=[("traffic.csv", csv_bytes(TRAFFIC_HEADERS, [["2026-09-01", "Brazil", "Organic Search", "10"]]))],
        leads=[("leads.csv", csv_bytes(LEAD_HEADERS, [["1", "2026-09-01 08:30", "Lead", "Paid Search", "Brazil"]]))],
        deals=[("deals.csv", csv_bytes(DEAL_HEADERS, [["d1", "2026-09-02 17:45", "Closed Won", "100", "Paid Search", "Brazil"]]))],
        ad_cost=[
            ("Ads Cost.csv", csv_bytes(["Account name", "Day", "Currency code", "Cost"], [["Hytera Brazil", "2026-09-01", "USD", "12.5"]])),
            ("加拿大Ads Cost.csv", csv_bytes(["Account name", "Day", "Currency code", "Cost"], [["Canada", "2026-09-01", "USD", "7.5"]])),
        ],
    )

    bundle = load_uploads(files)

    assert set(bundle.tables) == {"traffic", "leads", "deals", "ad_cost"}
    assert len(bundle.tables["ad_cost"]) == 2
    assert bundle.tables["ad_cost"]["cost"].sum() == 20
    assert bundle.tables["traffic"]["date"].iloc[0] == pd.Timestamp("2026-09-01")
    # 带时分秒的 Create Date 仍要归一到日历日
    assert bundle.tables["leads"]["date"].iloc[0] == pd.Timestamp("2026-09-01")


def test_load_uploads_warns_when_a_file_lands_in_the_wrong_slot():
    """表类型按列名识别，放错格子只给警告，不能按文件名或格子猜。"""
    files = upload_files(
        traffic=[("deals.csv", csv_bytes(DEAL_HEADERS, [["d1", "2026-09-02", "Closed Won", "100", "Paid Search", "Brazil"]]))],
    )

    bundle = load_uploads(files)

    assert "traffic" not in bundle.tables
    assert len(bundle.tables["deals"]) == 1
    warning = [d for d in bundle.diagnostics if d.level == "warning"][0]
    assert "Traffic slot" in warning.message and "Deals" in warning.message


def test_load_uploads_rejects_unrecognized_columns(capsys):
    files = upload_files(traffic=[("notes.csv", csv_bytes(["foo", "bar"], [["1", "2"]]))])

    bundle = load_uploads(files)

    assert bundle.tables == {}
    assert [d.level for d in bundle.diagnostics] == ["error"]
    assert bundle.diagnostics[0].path == "notes.csv"


def test_load_uploads_skips_empty_contents_and_flags_blank_region_rows():
    files = upload_files(
        traffic=[("traffic.csv", csv_bytes(TRAFFIC_HEADERS, [["20260101", "", "Unassigned", "7"]]))],
        leads=[],
    )

    bundle = load_uploads(files)

    assert set(bundle.tables["traffic"]["region"]) == {"Unassigned"}
