"""Migration 001: reset all mock-plan users to `free`.

Rationale
---------
During development the endpoints /api/auth/plan and /api/auth/premium-toggle
allowed clients to grant themselves any plan without a verified store purchase.
Phase 1 removes those endpoints. This migration retroactively resets every
existing user's cached plan to "free" so that no one keeps paid access on the
basis of a mock switch. Real paying users will regain entitlement through the
Phase 2/3 IAP verification flow.

Also creates required indexes on `subscriptions` and `iap_events` (idempotent).

Guards
------
- --dry-run: reports counts without writing.
- Refuses to run if the `_migrations` marker for this migration already exists.
- Refuses to run in ENVIRONMENT=production when `subscriptions` is non-empty
  (safety valve — prevents accidentally wiping real paid users).

Usage
-----
    python -m migrations.001_reset_dev_plans           # apply
    python -m migrations.001_reset_dev_plans --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load the same .env the server uses when this script runs from /app/backend
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
sys.path.insert(0, str(_ROOT))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

MIGRATION_NAME = "001_reset_dev_plans"


async def _ensure_indexes(db) -> None:
    await db.subscriptions.create_index([("user_id", 1), ("expires_at", -1)])
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
    await db.subscriptions.create_index(
        [("latest_transaction_id", 1)], sparse=True, name="latest_tx_sparse"
    )
    await db.subscriptions.create_index(
        [("expires_at", 1), ("status", 1)], name="expiry_sweep"
    )
    await db.iap_events.create_index(
        [("notification_uuid", 1)], unique=True, sparse=True, name="apple_notif_uuid_uniq"
    )
    await db.iap_events.create_index(
        [("pubsub_message_id", 1)], unique=True, sparse=True, name="google_msg_id_uniq"
    )
    await db.iap_events.create_index([("raw_payload_hash", 1)], name="payload_hash_audit")
    await db.iap_events.create_index(
        [("platform", 1), ("notification_type", 1), ("received_at", -1)],
        name="events_lookup",
    )
    await db.iap_events.create_index(
        [("user_id", 1), ("received_at", -1)], sparse=True, name="events_by_user"
    )


async def run(dry_run: bool = False, db=None) -> dict:
    """Run the migration. Returns a summary dict.

    When `db` is passed (used by tests), the caller owns the connection.
    Otherwise the migration opens its own connection using env vars.
    """
    close_client = False
    client = None
    if db is None:
        mongo_url = os.environ["MONGO_URL"]
        db_name = os.environ["DB_NAME"]
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        close_client = True

    try:
        # Idempotency guard
        existing = await db["_migrations"].find_one({"name": MIGRATION_NAME})
        if existing:
            return {
                "status": "already_applied",
                "applied_at": existing.get("applied_at"),
            }

        # Production safety valve
        env = os.environ.get("ENVIRONMENT", "development")
        if env == "production":
            subs_existing = await db.subscriptions.count_documents({})
            if subs_existing > 0:
                return {
                    "status": "refused",
                    "reason": "production with existing subscriptions",
                    "subs_count": subs_existing,
                }

        # Count affected users
        affected = await db.users.count_documents(
            {"$or": [{"plan": {"$in": ["premium", "plus"]}}, {"premium": True}]}
        )

        if dry_run:
            return {"status": "dry_run", "would_reset": affected}

        # Apply
        now = datetime.now(tz=timezone.utc)
        result = await db.users.update_many(
            {},
            {
                "$set": {
                    "plan": "free",
                    "premium": False,
                    "plan_recomputed_at": now,
                }
            },
        )
        # Only set is_email_verified where the field is missing (don't reset verified users)
        await db.users.update_many(
            {"is_email_verified": {"$exists": False}},
            {"$set": {"is_email_verified": False}},
        )

        await _ensure_indexes(db)

        await db["_migrations"].insert_one(
            {
                "name": MIGRATION_NAME,
                "applied_at": now,
                "reset_count": affected,
                "total_touched": result.modified_count,
            }
        )

        return {
            "status": "applied",
            "reset_count": affected,
            "total_touched": result.modified_count,
            "applied_at": now.isoformat(),
        }
    finally:
        if close_client and client is not None:
            client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(run(dry_run=args.dry_run))
    print(result)
