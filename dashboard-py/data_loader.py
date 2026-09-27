from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class Diagnostic:
    level: str
    message: str
    path: str | None = None


@dataclass
class DataBundle:
    tables: dict[str, pd.DataFrame]
    diagnostics: list[Diagnostic]


TABLE_REQUIRED_COLUMNS = {
    "traffic": {"date", "region", "session default channel group", "sessions"},
    "leads": {"record id", "create date", "lifecycle stage", "original traffic source", "region"},
    "deals": {"record id", "close date", "deal stage", "amount", "original traffic source", "region"},
}

FALLBACK_ENCODING = "latin-1"


def _normalized_columns(columns: list[Any]) -> dict[str, str]:
    return {str(column).strip().lower(): column for column in columns if str(column).strip()}


def _read_csv(path: Path) -> tuple[pd.DataFrame, str]:
    """读取 CSV，返回 (DataFrame, 实际使用的编码)。

    最后一种编码 latin-1 几乎总能解码成功，调用方需要据此提示源文件可能存在乱码。
    """
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030", FALLBACK_ENCODING):
        try:
            return pd.read_csv(path, encoding=encoding), encoding
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
    raise ValueError(str(last_error))


def _classify_table(columns: list[Any]) -> str | None:
    normalized = set(_normalized_columns(columns))
    for table_name, required in TABLE_REQUIRED_COLUMNS.items():
        if required <= normalized:
            return table_name
    if {"day", "currency code", "cost"} <= normalized:
        if "region" in normalized:
            return "ad_cost"
        if "account name" in normalized:
            return "ad_cost"
    return None


def _first_column(columns: dict[str, str], name: str) -> str:
    return columns[name]


def _source_class(value: Any) -> str:
    """来源分类：只看前缀。

    口径表要求 Session default channel group / Original Traffic Source 以 "Organic" 或 "Paid"
    **开头** 才归入对应分类（如 Organic Search、Paid Social），因此不能用包含判断。
    """
    text = "" if pd.isna(value) else str(value).strip().lower()
    if text.startswith("organic"):
        return "organic"
    if text.startswith("paid"):
        return "paid"
    return "other"


def _flexible_to_datetime(text: pd.Series) -> pd.Series:
    """逐值解析日期。

    pd.to_datetime 会从第一个值推断单一格式，一旦同列混了「2026-09-01 08:30」和「2026-09-02」，
    后者会被静默置为 NaT 并整行丢弃，因此必须按 mixed 模式解析。
    """
    try:
        return pd.to_datetime(text, errors="coerce", format="mixed")
    except (ValueError, TypeError):
        return pd.to_datetime(text.map(lambda value: pd.to_datetime(value, errors="coerce")), errors="coerce")


def _parse_dates(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.strip()
    compact = text.str.fullmatch(r"\d{8}(?:\.0)?")
    text = text.str.replace(r"\.0$", "", regex=True)
    parsed = _flexible_to_datetime(text.where(~compact))
    if compact.any():
        parsed.loc[compact] = pd.to_datetime(text.loc[compact], format="%Y%m%d", errors="coerce")
    return parsed


def _day(values: pd.Series) -> pd.Series:
    """统一截断到日历日。

    HubSpot 导出的 Create Date / Close Date 带时分秒，会让区间最后一天和按天分组都错位。
    """
    return _parse_dates(values).dt.normalize()


def _standardize(frame: pd.DataFrame, table_name: str, path: Path) -> pd.DataFrame:
    columns = _normalized_columns(list(frame.columns))
    frame = frame.copy()
    frame["source_file"] = str(path)

    if table_name == "traffic":
        frame["date"] = _day(frame[_first_column(columns, "date")])
        frame["region"] = frame[_first_column(columns, "region")].fillna("").astype(str).str.strip()
        frame["source"] = frame[_first_column(columns, "session default channel group")].fillna("").astype(str)
        frame["sessions"] = pd.to_numeric(frame[_first_column(columns, "sessions")], errors="coerce")
        frame = frame[frame["date"].notna() & frame["region"].ne("")]
        frame = frame[frame["source"].str.lower().ne("grand total")]
        frame["source_class"] = frame["source"].map(_source_class)
        return frame[["date", "region", "source", "source_class", "sessions", "source_file"]]

    if table_name == "leads":
        frame["date"] = _day(frame[_first_column(columns, "create date")])
        frame["region"] = frame[_first_column(columns, "region")].fillna("").astype(str).str.strip()
        frame["record_id"] = frame[_first_column(columns, "record id")].astype(str).str.strip()
        frame["lifecycle_stage"] = frame[_first_column(columns, "lifecycle stage")].fillna("").astype(str).str.strip()
        frame["source"] = frame[_first_column(columns, "original traffic source")].fillna("").astype(str)
        frame = frame[frame["date"].notna() & frame["record_id"].ne("")]
        frame["source_class"] = frame["source"].map(_source_class)
        return frame[["date", "region", "record_id", "lifecycle_stage", "source", "source_class", "source_file"]]

    if table_name == "deals":
        frame["date"] = _day(frame[_first_column(columns, "close date")])
        frame["region"] = frame[_first_column(columns, "region")].fillna("").astype(str).str.strip()
        frame["record_id"] = frame[_first_column(columns, "record id")].astype(str).str.strip()
        frame["deal_stage"] = frame[_first_column(columns, "deal stage")].fillna("").astype(str).str.strip()
        frame["amount"] = pd.to_numeric(frame[_first_column(columns, "amount")], errors="coerce")
        frame["source"] = frame[_first_column(columns, "original traffic source")].fillna("").astype(str)
        frame = frame[frame["date"].notna() & frame["record_id"].ne("")]
        frame["source_class"] = frame["source"].map(_source_class)
        return frame[["date", "region", "record_id", "deal_stage", "amount", "source", "source_class", "source_file"]]

    frame["date"] = _day(frame[_first_column(columns, "day")])
    if "region" in columns:
        frame["region"] = frame[_first_column(columns, "region")].fillna("").astype(str).str.strip()
    else:
        frame["region"] = frame[_first_column(columns, "account name")].fillna("").astype(str).str.strip()
    frame["cost"] = pd.to_numeric(frame[_first_column(columns, "cost")], errors="coerce")
    frame["currency"] = frame[_first_column(columns, "currency code")].fillna("").astype(str).str.strip().str.upper()
    frame = frame[frame["date"].notna() & frame["region"].ne("")]
    return frame[["date", "region", "cost", "currency", "source_file"]]


def load_folder(folder: Path | str) -> DataBundle:
    folder = Path(folder)
    diagnostics: list[Diagnostic] = []
    tables: dict[str, list[pd.DataFrame]] = {}
    if not folder.exists() or not folder.is_dir():
        return DataBundle({}, [Diagnostic("error", "Data folder does not exist", str(folder))])

    paths = sorted(folder.rglob("*.csv"))
    if not paths:
        return DataBundle({}, [Diagnostic("error", "No CSV files found", str(folder))])

    for path in paths:
        try:
            frame, encoding = _read_csv(path)
            if encoding == FALLBACK_ENCODING:
                diagnostics.append(
                    Diagnostic("warning", f"CSV was decoded with the {FALLBACK_ENCODING} fallback; non-ASCII text may be garbled", str(path))
                )
            table_name = _classify_table(list(frame.columns))
            if table_name is None:
                diagnostics.append(Diagnostic("warning", "CSV table type was not recognized", str(path)))
                continue
            tables.setdefault(table_name, []).append(_standardize(frame, table_name, path))
        except Exception as exc:
            diagnostics.append(Diagnostic("error", f"Could not load CSV: {exc}", str(path)))

    merged = {name: pd.concat(frames, ignore_index=True) for name, frames in tables.items()}
    ad_cost = merged.get("ad_cost")
    if ad_cost is not None and not ad_cost.empty:
        others = sorted({code for code in ad_cost["currency"].dropna().unique() if code and code != "USD"})
        if others:
            diagnostics.append(
                Diagnostic("warning", f"Ad cost contains non-USD currencies summed as USD: {', '.join(others)}", None)
            )
    return DataBundle(merged, diagnostics)
