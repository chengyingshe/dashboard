from __future__ import annotations


# 默认区间长度（天）：前端默认展示最大数据日期往前 29 天
DEFAULT_DAYS = 30

# 目标值（`数据口径.xlsx` Sheet2 顶部）。前端提供输入框可随时改，浏览器会记住使用者填的值。
# 口径表里这几行的年份标注互相冲突（2026~2029），只作为参考值，不要当成某年的正式承诺。
# `metric` 指向 metrics.compute_kpis 的键名；`default=None` 表示留空，不显示达成率。
TARGET_SPECS = [
    {"id": "organic_traffic", "label": "Target Organic Traffic", "metric": "organic_traffic", "default": 478649, "step": 1000, "format": "number"},
    {"id": "leads", "label": "Target Leads", "metric": "all_leads", "default": 15500, "step": 100, "format": "number"},
    {"id": "mqls", "label": "Target MQLs", "metric": "all_mqls", "default": 5879, "step": 100, "format": "number"},
    {"id": "sqls", "label": "Target SQLs", "metric": "all_sqls", "default": None, "step": 100, "format": "number"},
    {"id": "revenue", "label": "Target Revenue", "metric": "all_revenue", "default": 1_520_000, "step": 10000, "format": "money"},
]

TARGET_IDS = [spec["id"] for spec in TARGET_SPECS]

# 达成率显示在哪张 KPI 卡片上：metric 名 -> target id
TARGET_BY_METRIC = {spec["metric"]: spec["id"] for spec in TARGET_SPECS}

DEFAULT_TARGETS = {spec["id"]: spec["default"] for spec in TARGET_SPECS}

# 地区缺失时的兜底显示名：空地区行不整行丢弃，归到它名下继续参与总量
UNKNOWN_REGION = "Unassigned"

# Region 下拉只展示业务区域组，不展示国家明细。
# LATAM North / LATAM South 的覆盖范围与广告账户 Hytera LATAM North / Hytera LATAM South 一致。
REGION_GROUP_ORDER = ["Brazil", "Mexico", "LATAM North", "LATAM South", "Canada"]

REGION_GROUPS: dict[str, list[str]] = {
    "Brazil": ["Brazil"],
    "Mexico": ["Mexico"],
    "LATAM North": [
        # 中美洲
        "Guatemala", "Belize", "El Salvador", "Honduras", "Nicaragua", "Costa Rica", "Panama",
        # 加勒比
        "Dominican Republic", "Cuba", "Jamaica", "Haiti", "Puerto Rico", "Bahamas", "Barbados",
        "Trinidad and Tobago", "Trinidad & Tobago", "Aruba", "Curacao", "Curaçao", "Cayman Islands",
        "Antigua and Barbuda", "Antigua & Barbuda", "Dominica", "Grenada", "Saint Lucia", "St. Lucia",
        "Saint Vincent & Grenadines", "St. Vincent & Grenadines", "Saint Kitts & Nevis", "Montserrat",
        "Anguilla", "Turks and Caicos Islands", "Turks & Caicos Islands", "British Virgin Islands",
        "BVI16", "U.S. Virgin Islands", "Saint Martin", "St. Martin", "Sint Maarten", "Saint Maarten",
        "Saint Barthélemy", "St. Barthélemy", "Caribbean Netherlands", "Guadeloupe", "Martinique",
        # 南美北部
        "Colombia", "Venezuela", "Guyana", "Suriname", "French Guiana",
    ],
    "LATAM South": ["Argentina", "Chile", "Peru", "Ecuador", "Uruguay", "Paraguay", "Bolivia"],
    "Canada": ["Canada"],
}

# 不在任何区域组内的国家（美国、西班牙、亚太等）：只在不限地区时计入，不进下拉
OTHER_REGION_GROUP = "Other"

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


def _country_to_group() -> dict[str, str]:
    """国家名（含区域组自身）-> 区域组，大小写不敏感。"""
    mapping = {group.casefold(): group for group in REGION_GROUP_ORDER}
    for group, countries in REGION_GROUPS.items():
        for country in countries:
            mapping.setdefault(str(country).strip().casefold(), group)
    return mapping


COUNTRY_TO_GROUP = _country_to_group()


def region_group(value) -> str:
    """把国家名或广告账户名映射成 Region 下拉里的区域组。

    广告花费表的 region 是投放账户名（如 `Hytera LATAM North`），先经「账户 -> 覆盖国家」
    再归到区域组；没有配置映射的取值一律落到 `Other`，不会凭空算进某个区域。
    """
    if value is None or (isinstance(value, float) and value != value):
        return UNKNOWN_REGION
    text = str(value).strip()
    if text.casefold() in {"", "nan", "none"}:
        return UNKNOWN_REGION
    group = COUNTRY_TO_GROUP.get(text.casefold())
    if group:
        return group
    countries = AD_ACCOUNT_REGION_MAP.get(text)
    if countries:
        groups = [COUNTRY_TO_GROUP.get(str(country).strip().casefold()) for country in countries]
        groups = [item for item in groups if item in REGION_GROUP_ORDER]
        if groups:
            return min(groups, key=REGION_GROUP_ORDER.index)
    return OTHER_REGION_GROUP
