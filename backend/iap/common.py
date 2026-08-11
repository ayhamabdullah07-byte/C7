"""Shared types, product mapping, and idempotency helpers for the IAP subsystem.

Product identifiers use the real bundle ID `com.ayhamabdullah.c1`. Actual App Store
Connect / Play Console product IDs must be created by the operator before purchases
can complete (see /app/memory/PRD.md for the Play Console checklist).

Base prices shown in EUR — the store returns real localized prices at runtime:
  Premium Monthly   €1.99  / month
  Plus    Monthly   €4.99  / month
  Plus    Annual    €54.99 / year
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------
Plan = Literal["free", "premium", "plus"]
Platform = Literal["apple", "google"]
Period = Literal["P1M", "P1Y"]

RANK: dict[str, int] = {"free": 0, "premium": 1, "plus": 2}


def rank_of(plan: str) -> int:
    return RANK.get(plan, 0)


# ---------------------------------------------------------------------------
# Product mapping — real bundle IDs (com.ayhamabdullah.c1)
# ---------------------------------------------------------------------------
_APPLE_BUNDLE = os.environ.get("APPLE_BUNDLE_ID", "com.ayhamabdullah.c1")
_GOOGLE_PACKAGE = os.environ.get("GOOGLE_PACKAGE_NAME", "com.ayhamabdullah.c1")


APPLE_PRODUCTS: dict[str, tuple[Plan, Period]] = {
    f"{_APPLE_BUNDLE}.premium.monthly": ("premium", "P1M"),
    f"{_APPLE_BUNDLE}.plus.monthly":    ("plus",    "P1M"),
    f"{_APPLE_BUNDLE}.plus.annual":     ("plus",    "P1Y"),
}

# Google keys are (subscription_id, base_plan_id) tuples.
GOOGLE_PRODUCTS: dict[tuple[str, str], tuple[Plan, Period]] = {
    ("c1_premium", "monthly"): ("premium", "P1M"),
    ("c1_plus",    "monthly"): ("plus",    "P1M"),
    ("c1_plus",    "annual"):  ("plus",    "P1Y"),
}


def resolve_apple_product(product_id: str) -> Optional[tuple[Plan, Period]]:
    return APPLE_PRODUCTS.get(product_id)


def resolve_google_product(subscription_id: str, base_plan_id: str) -> Optional[tuple[Plan, Period]]:
    return GOOGLE_PRODUCTS.get((subscription_id, base_plan_id))


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------
def dedupe_hash(raw: bytes | str) -> str:
    """SHA-256 of the raw payload; used as a *secondary* dedupe defense in iap_events.

    Primary dedupe uses store canonical IDs (notification_uuid / pubsub_message_id).
    """
    data = raw.encode() if isinstance(raw, str) else raw
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
SubscriptionStatus = Literal[
    "active", "expired", "in_grace", "on_hold", "paused", "revoked", "canceled"
]


class Subscription(BaseModel):
    """Subscription lifecycle document. One per (user, transaction chain)."""

    id: str
    user_id: str
    platform: Platform
    product_id: str
    tier: Plan
    period: Period

    # Apple
    original_transaction_id: Optional[str] = None
    latest_transaction_id: Optional[str] = None

    # Google
    purchase_token: Optional[str] = None
    linked_purchase_token: Optional[str] = None
    base_plan_id: Optional[str] = None

    # Universal state
    status: SubscriptionStatus = "active"
    auto_renew: bool = True
    purchase_date: datetime
    expires_at: datetime  # canonical store value, never mutated by us
    grace_period_expires_at: Optional[datetime] = None  # store-provided
    original_purchase_date: datetime
    in_trial: bool = False
    trial_end_at: Optional[datetime] = None
    cancellation_date: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    refund_date: Optional[datetime] = None
    revoked: bool = False

    # Audit
    environment: Literal["sandbox", "production"] = "production"
    last_notification_id: Optional[str] = None
    last_webhook_at: Optional[datetime] = None
    raw_state_snapshot: Optional[dict] = None

    created_at: datetime
    updated_at: datetime


class IapEvent(BaseModel):
    """Immutable audit-log entry for every IAP action."""

    id: str
    user_id: Optional[str] = None
    platform: Platform
    event_type: Literal["verify", "notification", "restore", "reconcile"]
    notification_type: Optional[str] = None
    notification_uuid: Optional[str] = None  # Apple
    pubsub_message_id: Optional[str] = None  # Google
    raw_payload_hash: str
    raw_payload: Optional[str] = None
    subscription_id: Optional[str] = None
    processed: bool = False
    processing_error: Optional[str] = None
    processing_note: Optional[str] = None
    received_at: datetime
    processed_at: Optional[datetime] = None


class EntitlementOut(BaseModel):
    plan: Plan
    tier_source: Optional[str] = None       # product_id of the currently-effective sub
    platform: Optional[Platform] = None
    expires_at: Optional[datetime] = None
    grace_period_expires_at: Optional[datetime] = None
    in_grace: bool = False
    auto_renew: bool = False
    will_renew_at: Optional[datetime] = None
    manage_url: Optional[str] = None
    trial: Optional[dict] = None
    canceled_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Scan-limit tiers — per-plan Base + Rewarded splits (24h rolling window)
# ---------------------------------------------------------------------------
#
#   Free:    3 base + up to 2 rewarded = 5 max/day
#   Premium: 20 base + up to 3 rewarded = 23 max/day
#   Plus:    99 total (no ads, no rewarded flow); fair-use cap
#
# `base` = free daily allowance without watching any ad
# `rewarded` = max additional scans a user may unlock by watching Rewarded Ads
# `total_cap` = hard fair-use cap (Plus only; None means base+rewarded gate)
#
SCAN_LIMITS: dict[str, dict[str, Optional[int]]] = {
    "free":    {"base": 3,  "rewarded": 2, "total_cap": None},
    "premium": {"base": 20, "rewarded": 3, "total_cap": None},
    "plus":    {"base": 99, "rewarded": 0, "total_cap": 99},
}

# Backward-compat top-level fair-use cap for Plus (also referenced by legacy code).
PLUS_FAIR_USE_LIMIT: int = 99


def plan_limits(plan: str) -> dict[str, Optional[int]]:
    """Return the SCAN_LIMITS row for a plan, defaulting to free's config for unknown plans."""
    return SCAN_LIMITS.get(plan, SCAN_LIMITS["free"])
