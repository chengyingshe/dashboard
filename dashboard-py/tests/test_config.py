from config import OTHER_REGION_GROUP, REGION_GROUP_ORDER, UNKNOWN_REGION, region_group


def test_country_names_map_to_business_region_groups():
    assert region_group("Brazil") == "Brazil"
    assert region_group("Mexico") == "Mexico"
    assert region_group("Canada") == "Canada"
    assert region_group("Colombia") == "LATAM North"
    assert region_group("Guatemala") == "LATAM North"
    assert region_group("Chile") == "LATAM South"
    assert region_group("Peru") == "LATAM South"


def test_ad_account_names_map_to_the_group_they_cover():
    """广告花费的 region 是投放账户名，要按账户覆盖国家归组，不能按字面值匹配。"""
    assert region_group("Hytera Brazil") == "Brazil"
    assert region_group("Hytera Mexico") == "Mexico"
    assert region_group("Canada") == "Canada"
    assert region_group("Hytera LATAM North") == "LATAM North"
    assert region_group("Hytera LATAM South") == "LATAM South"


def test_unmapped_values_never_land_in_a_business_group():
    """美国/亚太等不在区域组内的国家只能落到 Other，不能凭空算进某个区域。"""
    assert region_group("United States") == OTHER_REGION_GROUP
    assert region_group("Spain") == OTHER_REGION_GROUP
    assert region_group("Some Unmapped Account") == OTHER_REGION_GROUP


def test_blank_or_missing_region_stays_unassigned():
    assert region_group("") == UNKNOWN_REGION
    assert region_group(None) == UNKNOWN_REGION
    assert region_group(float("nan")) == UNKNOWN_REGION


def test_lookup_is_case_insensitive_and_group_names_resolve_to_themselves():
    assert region_group("brazil") == "Brazil"
    for group in REGION_GROUP_ORDER:
        assert region_group(group) == group
