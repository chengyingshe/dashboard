from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "数据底表V1"
DEFAULT_DAYS = 30
TARGETS = {"organic_traffic": 478649, "leads": 15500, "mqls": 5879, "revenue": 1_520_000, "close_win_conversion": 0.07}

# 广告花费表的 region 存的是投放账户名，与流量/线索/成交的国家名不是同一套枚举。
# 这里配置「账户 -> 覆盖国家」映射，使地区筛选时花费能与业务指标对齐。
# 未配置的账户只在不限地区时计入；如 LATAM 账户实际也投放 Brazil / Mexico，在对应列表里补上即可。
AD_ACCOUNT_REGION_MAP = {
    "Hytera Brazil": ["Brazil"],
    "Hytera Mexico": ["Mexico"],
    "Canada": ["Canada"],
    "Hytera LATAM North": [
        "Colombia", "Venezuela", "Panama", "Costa Rica", "Guatemala", "Dominican Republic",
        "El Salvador", "Honduras", "Nicaragua", "Puerto Rico", "Jamaica", "Trinidad and Tobago",
    ],
    "Hytera LATAM South": [
        "Argentina", "Chile", "Peru", "Ecuador", "Uruguay", "Paraguay", "Bolivia",
    ],
}


def resolve_data_dir(cli_value: str | None) -> Path:
    return Path(cli_value or os.getenv("DASHBOARD_DATA_DIR") or DEFAULT_DATA_DIR).expanduser().resolve()
