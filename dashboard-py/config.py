from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "数据底表V1"
DEFAULT_DAYS = 30
TARGETS = {"organic_traffic": 478649, "leads": 15500, "mqls": 5879, "revenue": 1_520_000, "close_win_conversion": 0.07}


def resolve_data_dir(cli_value: str | None) -> Path:
    return Path(cli_value or os.getenv("DASHBOARD_DATA_DIR") or DEFAULT_DATA_DIR).expanduser().resolve()
