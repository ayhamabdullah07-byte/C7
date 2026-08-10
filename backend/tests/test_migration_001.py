"""Migration 001 tests."""
from __future__ import annotations

import uuid

import pytest

from migrations import __init__  # noqa: F401
# Import the migration module by numeric name
import importlib
mig = importlib.import_module("migrations.001_reset_dev_plans")


@pytest.mark.asyncio
async def test_migration_resets_all_plans_to_free(db):
    # Seed 3 users
    await db.users.insert_many(
        [
            {"id": f"u{i}", "email": f"u{i}@x", "name": f"U{i}", "plan": p, "premium": (p != "free")}
            for i, p in enumerate(["free", "premium", "plus"])
        ]
    )
    result = await mig.run(dry_run=False, db=db)
    assert result["status"] == "applied"
    assert result["reset_count"] == 2  # premium + plus users
    assert result["total_touched"] == 3  # all three touched (plan_recomputed_at, etc.)

    async for u in db.users.find({}, {"_id": 0}):
        assert u["plan"] == "free"
        assert u["premium"] is False
        assert u["is_email_verified"] is False


@pytest.mark.asyncio
async def test_migration_dry_run_writes_nothing(db):
    await db.users.insert_one({"id": "u1", "email": "u1@x", "name": "U1", "plan": "plus", "premium": True})
    result = await mig.run(dry_run=True, db=db)
    assert result["status"] == "dry_run"
    assert result["would_reset"] == 1
    u = await db.users.find_one({"id": "u1"}, {"_id": 0})
    assert u["plan"] == "plus"  # untouched


@pytest.mark.asyncio
async def test_migration_is_idempotent(db):
    await db.users.insert_one({"id": "u1", "email": "u1@x", "name": "U1", "plan": "plus", "premium": True})
    first = await mig.run(dry_run=False, db=db)
    assert first["status"] == "applied"
    second = await mig.run(dry_run=False, db=db)
    assert second["status"] == "already_applied"


@pytest.mark.asyncio
async def test_migration_creates_indexes(db):
    await mig.run(dry_run=False, db=db)
    sub_ix = [ix["name"] for ix in await db.subscriptions.list_indexes().to_list(20)]
    ev_ix = [ix["name"] for ix in await db.iap_events.list_indexes().to_list(20)]
    assert "apple_original_tx_uniq" in sub_ix
    assert "google_purchase_token_uniq" in sub_ix
    assert "apple_notif_uuid_uniq" in ev_ix
    assert "google_msg_id_uniq" in ev_ix
