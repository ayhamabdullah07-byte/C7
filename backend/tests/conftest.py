import os
import time
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://c1-meal-scanner.preview.emergentagent.com").rstrip("/")

@pytest.fixture(scope="session")
def base_url():
    return BASE

@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s

@pytest.fixture(scope="session")
def user_ctx(api_client, base_url):
    # register a fresh user
    email = f"TEST_{int(time.time())}@c1.app"
    pw = "Test1234!"
    r = api_client.post(f"{base_url}/api/auth/register", json={"email": email, "password": pw, "name": "TEST User"})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    uid = r.json()["user_id"]
    return {"email": email, "password": pw, "token": tok, "user_id": uid, "auth": {"Authorization": f"Bearer {tok}"}}


# ---------------------------------------------------------------------------
# Phase 1 additions — DB fixture + helpers
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db():
    """Isolated Mongo DB per test."""
    mongo_url = os.environ["MONGO_URL"]
    name = f"c1_test_{uuid.uuid4().hex[:8]}"
    client = AsyncIOMotorClient(mongo_url)
    try:
        yield client[name]
    finally:
        await client.drop_database(name)
        client.close()


@pytest.fixture
def user_id() -> str:
    return f"u-{uuid.uuid4().hex[:8]}"


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Helper for legacy tests: grant a plan via seeded subscription (no mock endpoints)
# ---------------------------------------------------------------------------
def grant_plan_via_subscription(user_id: str, tier: str) -> dict:
    """Insert a verified-looking subscription record directly.

    Only for tests. Replaces the removed /api/auth/plan mock.
    """
    import os
    from pymongo import MongoClient
    now = datetime.now(timezone.utc)
    mongo = MongoClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]

    # Remove existing subs so tests are deterministic
    db.subscriptions.delete_many({"user_id": user_id})

    if tier == "free":
        # No subscription = free. Also clear cache projection so /auth/me updates.
        db.users.update_one(
            {"id": user_id},
            {"$set": {"plan": "free", "premium": False, "plan_recomputed_at": now}},
        )
        mongo.close()
        return {"tier": "free"}

    product_map = {
        "premium": ("com.yourbrand.c1.premium.monthly", "P1M"),
        "plus": ("com.yourbrand.c1.plus.monthly", "P1M"),
    }
    product_id, period = product_map[tier]
    doc = {
        "id": f"s-{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "platform": "apple",
        "product_id": product_id,
        "tier": tier,
        "period": period,
        "original_transaction_id": uuid.uuid4().hex,
        "latest_transaction_id": uuid.uuid4().hex,
        "status": "active",
        "auto_renew": True,
        "purchase_date": now,
        "expires_at": now.replace(microsecond=0) + timedelta(days=365),
        "grace_period_expires_at": None,
        "original_purchase_date": now,
        "in_trial": False,
        "revoked": False,
        "environment": "sandbox",
        "created_at": now,
        "updated_at": now,
    }
    db.subscriptions.insert_one(doc)
    # Bust the cached projection so tests see the change immediately.
    db.users.update_one(
        {"id": user_id},
        {"$set": {"plan": tier, "premium": True, "plan_recomputed_at": now}},
    )
    mongo.close()
    return doc


# Backfill the timedelta import
from datetime import timedelta  # noqa: E402
