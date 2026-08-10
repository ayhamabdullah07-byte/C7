"""Verify the unique / partial indexes on `subscriptions` enforce dedupe correctly."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from pymongo.errors import DuplicateKeyError

from tests.conftest import now_utc


async def _ensure(db):
    # Small helper: create the same indexes the startup hook creates.
    await db.subscriptions.create_index(
        [("platform", 1), ("original_transaction_id", 1)],
        unique=True,
        partialFilterExpression={
            "platform": "apple",
            "original_transaction_id": {"$type": "string"},
        },
        name="apple_original_tx_uniq",
    )
    await db.subscriptions.create_index(
        [("platform", 1), ("purchase_token", 1)],
        unique=True,
        partialFilterExpression={
            "platform": "google",
            "purchase_token": {"$type": "string"},
        },
        name="google_purchase_token_uniq",
    )


def _apple_doc(user_id: str, original_tx: str, **kw):
    now = now_utc()
    d = {
        "id": uuid.uuid4().hex,
        "user_id": user_id,
        "platform": "apple",
        "product_id": "com.yourbrand.c1.plus.monthly",
        "tier": "plus",
        "period": "P1M",
        "original_transaction_id": original_tx,
        "status": "active",
        "purchase_date": now,
        "expires_at": now + timedelta(days=30),
        "original_purchase_date": now,
        "revoked": False,
        "environment": "sandbox",
        "created_at": now,
        "updated_at": now,
    }
    d.update(kw)
    return d


def _google_doc(user_id: str, token: str, **kw):
    d = _apple_doc(user_id, uuid.uuid4().hex)
    d["platform"] = "google"
    d["original_transaction_id"] = None
    d["purchase_token"] = token
    d.update(kw)
    return d


@pytest.mark.asyncio
async def test_apple_original_tx_unique(db):
    await _ensure(db)
    tx = "orig-tx-123"
    await db.subscriptions.insert_one(_apple_doc("u1", tx))
    with pytest.raises(DuplicateKeyError):
        await db.subscriptions.insert_one(_apple_doc("u2", tx))


@pytest.mark.asyncio
async def test_google_purchase_token_unique(db):
    await _ensure(db)
    tok = "tok-123"
    await db.subscriptions.insert_one(_google_doc("u1", tok))
    with pytest.raises(DuplicateKeyError):
        await db.subscriptions.insert_one(_google_doc("u2", tok))


@pytest.mark.asyncio
async def test_same_string_different_platforms_ok(db):
    """A collision on the raw value across platforms is allowed (partial index scoped by platform)."""
    await _ensure(db)
    same = "shared-string"
    # apple sub with original_tx == "shared-string"
    await db.subscriptions.insert_one(_apple_doc("u1", same))
    # google sub with purchase_token == "shared-string" — different field, different platform
    await db.subscriptions.insert_one(_google_doc("u2", same))
    assert await db.subscriptions.count_documents({}) == 2
