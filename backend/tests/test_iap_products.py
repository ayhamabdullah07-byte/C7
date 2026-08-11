"""Unit tests for the IAP product mapping (com.ayhamabdullah.c1).

Verifies:
  - Apple product IDs resolve to correct (tier, period)
  - Google product tuples resolve correctly
  - Unknown IDs return None
  - Bundle constants match user-approved identifier
  - SCAN_LIMITS shape matches the Free/Premium/Plus contract
"""
from iap import common
from iap.common import (
    APPLE_PRODUCTS,
    GOOGLE_PRODUCTS,
    PLUS_FAIR_USE_LIMIT,
    SCAN_LIMITS,
    plan_limits,
    resolve_apple_product,
    resolve_google_product,
)


def test_apple_products_shape():
    expected_ids = {
        "com.ayhamabdullah.c1.premium.monthly",
        "com.ayhamabdullah.c1.plus.monthly",
        "com.ayhamabdullah.c1.plus.annual",
    }
    assert set(APPLE_PRODUCTS.keys()) == expected_ids


def test_apple_products_resolve():
    assert resolve_apple_product("com.ayhamabdullah.c1.premium.monthly") == ("premium", "P1M")
    assert resolve_apple_product("com.ayhamabdullah.c1.plus.monthly") == ("plus", "P1M")
    assert resolve_apple_product("com.ayhamabdullah.c1.plus.annual") == ("plus", "P1Y")


def test_apple_unknown_product_returns_none():
    assert resolve_apple_product("com.ayhamabdullah.c1.premium.quarterly") is None
    assert resolve_apple_product("random.garbage") is None


def test_google_products_shape():
    expected_keys = {
        ("c1_premium", "monthly"),
        ("c1_plus", "monthly"),
        ("c1_plus", "annual"),
    }
    assert set(GOOGLE_PRODUCTS.keys()) == expected_keys


def test_google_products_resolve():
    assert resolve_google_product("c1_premium", "monthly") == ("premium", "P1M")
    assert resolve_google_product("c1_plus", "monthly") == ("plus", "P1M")
    assert resolve_google_product("c1_plus", "annual") == ("plus", "P1Y")


def test_google_unknown_product_returns_none():
    assert resolve_google_product("nonexistent", "monthly") is None
    assert resolve_google_product("c1_plus", "quarterly") is None


# ---------------------------------------------------------------------------
# Scan limits contract
# ---------------------------------------------------------------------------
def test_scan_limits_free():
    row = plan_limits("free")
    assert row["base"] == 3
    assert row["rewarded"] == 2
    assert row["total_cap"] is None


def test_scan_limits_premium():
    row = plan_limits("premium")
    assert row["base"] == 20
    assert row["rewarded"] == 3
    assert row["total_cap"] is None


def test_scan_limits_plus():
    row = plan_limits("plus")
    assert row["base"] == 99
    assert row["rewarded"] == 0
    assert row["total_cap"] == 99


def test_plus_fair_use_constant():
    assert PLUS_FAIR_USE_LIMIT == 99


def test_unknown_plan_defaults_to_free():
    row = plan_limits("legacy_something")
    assert row == SCAN_LIMITS["free"]


def test_periods_are_valid():
    for _tier, period in APPLE_PRODUCTS.values():
        assert period in ("P1M", "P1Y")
    for _tier, period in GOOGLE_PRODUCTS.values():
        assert period in ("P1M", "P1Y")
