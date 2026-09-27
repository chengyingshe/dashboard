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


def _normalized_columns(columns: list[Any]) -> dict[str, str]:
    return {str(column).strip().lower(): column for column in columns if str(column).strip()}


def _read_csv(path: Path) -> pd.DataFrame:
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return pd.read_csv(path, encoding=encoding)
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
    text = "" if pd.isna(value) else str(value).lower()
    if "organic" in text:
        return "organic"
    if "paid" in text:
        return "paid"
    return "other"


def _parse_dates(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.strip()
    compact = text.str.fullmatch(r"\d{8}(?:\.0)?")
    text = text.str.replace(r"\.0$", "", regex=True)
    parsed = pd.to_datetime(text.where(~compact), errors="coerce")
    parsed.loc[compact] = pd.to_datetime(text.loc[compact], format="%Y%m%d", errors="coerce")
    return parsed


def _standardize(frame: pd.DataFrame, table_name: str, path: Path) -> pd.DataFrame:
    columns = _normalized_columns(list(frame.columns))
    frame = frame.copy()
    frame["source_file"] = str(path)

    if table_name == "traffic":
        date_column = _first_column(columns, "date")
        frame["date"] = _parse_dates(frame[date_column])
        frame["region"] = frame[_first_column(columns, "region")].fillna("").astype(str).str.strip()
        frame["source"] = frame[_first_column(columns, "session default channel group")].fillna("").astype(str)
        frame["sessions"] = pd.to_numeric(frame[_first_column(columns, "sessions")], errors="coerce")
        frame = frame[frame["date"].notna() & frame["region"].ne("")]
        frame = frame[frame["source"].str.lower().ne("grand total")]
        frame["source_class"] = frame["source"].map(_source_class)
        return frame[["date", "region", "source", "source_class", "sessions", "source_file"]]

    if table_name == "leads":
        frame["date"] = _parse_dates(frame[_first_column(columns, "create date")])
        frame["region"] = frame[_first_column(columns, "region")].fillna("").astype(str).str.strip()
        frame["record_id"] = frame[_first_column(columns, "record id")].astype(str).str.strip()
        frame["lifecycle_stage"] = frame[_first_column(columns, "lifecycle stage")].fillna("").astype(str).str.strip()
        frame["source"] = frame[_first_column(columns, "original traffic source")].fillna("").astype(str)
        frame = frame[frame["date"].notna() & frame["record_id"].ne("")]
        frame["source_class"] = frame["source"].map(_source_class)
        return frame[["date", "region", "record_id", "lifecycle_stage", "source", "source_class", "source_file"]]

    if table_name == "deals":
        frame["date"] = _parse_dates(frame[_first_column(columns, "close date")])
        frame["region"] = frame[_first_column(columns, "region")].fillna("").astype(str).str.strip()
        frame["record_id"] = frame[_first_column(columns, "record id")].astype(str).str.strip()
        frame["deal_stage"] = frame[_first_column(columns, "deal stage")].fillna("").astype(str).str.strip()
        frame["amount"] = pd.to_numeric(frame[_first_column(columns, "amount")], errors="coerce")
        frame["source"] = frame[_first_column(columns, "original traffic source")].fillna("").astype(str)
        frame = frame[frame["date"].notna() & frame["record_id"].ne("")]
        frame["source_class"] = frame["source"].map(_source_class)
        return frame[["date", "region", "record_id", "deal_stage", "amount", "source", "source_class", "source_file"]]

    frame["date"] = _parse_dates(frame[_first_column(columns, "day")])
    if "region" in columns:
        frame["region"] = frame[_first_column(columns, "region")].fillna("").astype(str).str.strip()
    else:
        frame["region"] = frame[_first_column(columns, "account name")].fillna("").astype(str).str.strip()
    frame["cost"] = pd.to_numeric(frame[_first_column(columns, "cost")], errors="coerce")
    frame = frame[frame["date"].notna() & frame["region"].ne("")]
    return frame[["date", "region", "cost", "source_file"]]


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
            frame = _read_csv(path)
            table_name = _classify_table(list(frame.columns))
            if table_name is None:
                diagnostics.append(Diagnostic("warning", "CSV table type was not recognized", str(path)))
                continue
            tables.setdefault(table_name, []).append(_standardize(frame, table_name, path))
        except Exception as exc:
            diagnostics.append(Diagnostic("error", f"Could not load CSV: {exc}", str(path)))

    merged = {name: pd.concat(frames, ignore_index=True) for name, frames in tables.items()}
    return DataBundle(merged, diagnostics)
