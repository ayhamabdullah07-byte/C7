"""Unit tests for iap.effective_plan.effective_plan()."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from iap.effective_plan import effective_plan, entitlement_snapshot

from tests.conftest import now_utc


def _sub(user_id: str, **overrides) -> dict:
    now = now_utc()
    base = {
        "id": f"s-{uuid.uuid4().hex[:8]}",
        "user_id": user_id,
        "platform": "apple",
        "product_id": "com.yourbrand.c1.premium.monthly",
        "tier": "premium",
        "period": "P1M",
        "original_transaction_id": uuid.uuid4().hex,
        "status": "active",
        "auto_renew": True,
        "purchase_date": now,
        "expires_at": now + timedelta(days=30),
        "grace_period_expires_at": None,
        "original_purchase_date": now,
        "in_trial": False,
        "revoked": False,
        "environment": "sandbox",
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_no_subs_returns_free(db, user_id):
    assert await effective_plan(db, user_id) == "free"


@pytest.mark.asyncio
async def test_active_premium(db, user_id):
    await db.subscriptions.insert_one(_sub(user_id))
    assert await effective_plan(db, user_id) == "premium"


@pytest.mark.asyncio
async def test_active_plus(db, user_id):
    await db.subscriptions.insert_one(_sub(user_id, tier="plus", product_id="com.yourbrand.c1.plus.monthly"))
    assert await effective_plan(db, user_id) == "plus"


@pytest.mark.asyncio
async def test_plus_wins_over_premium(db, user_id):
    await db.subscriptions.insert_one(_sub(user_id, tier="premium"))
    await db.subscriptions.insert_one(
        _sub(user_id, tier="plus", product_id="com.yourbrand.c1.plus.monthly")
    )
    assert await effective_plan(db, user_id) == "plus"


@pytest.mark.asyncio
async def test_expired_returns_free(db, user_id):
    await db.subscriptions.insert_one(
        _sub(user_id, expires_at=now_utc() - timedelta(days=1), status="expired")
    )
    assert await effective_plan(db, user_id) == "free"


@pytest.mark.asyncio
async def test_expired_with_grace_still_active(db, user_id):
    await db.subscriptions.insert_one(
        _sub(
            user_id,
            expires_at=now_utc() - timedelta(hours=1),
            grace_period_expires_at=now_utc() + timedelta(days=3),
            status="in_grace",
        )
    )
    assert await effective_plan(db, user_id) == "premium"


@pytest.mark.asyncio
async def test_grace_but_revoked_returns_free(db, user_id):
    await db.subscriptions.insert_one(
        _sub(
            user_id,
            expires_at=now_utc() - timedelta(hours=1),
            grace_period_expires_at=now_utc() + timedelta(days=3),
            status="in_grace",
            revoked=True,
        )
    )
    assert await effective_plan(db, user_id) == "free"


@pytest.mark.asyncio
async def test_paused_status_returns_free(db, user_id):
    await db.subscriptions.insert_one(
        _sub(user_id, status="paused")
    )
    assert await effective_plan(db, user_id) == "free"


@pytest.mark.asyncio
async def test_entitlement_snapshot_reports_grace(db, user_id):
    await db.subscriptions.insert_one(
        _sub(
            user_id,
            tier="plus",
            product_id="com.yourbrand.c1.plus.monthly",
            expires_at=now_utc() - timedelta(hours=1),
            grace_period_expires_at=now_utc() + timedelta(days=2),
            status="in_grace",
        )
    )
    snap = await entitlement_snapshot(db, user_id)
    assert snap.plan == "plus"
    assert snap.in_grace is True
    assert snap.manage_url == "https://apps.apple.com/account/subscriptions"
