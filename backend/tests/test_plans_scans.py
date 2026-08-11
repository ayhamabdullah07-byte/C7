"""Tests for scan limits, plan gating, and quota persistence.

Turn A limits (com.ayhamabdullah.c1):
  Free:    3 base + 2 rewarded  (5 max/day, ads unlock rewarded)
  Premium: 20 base + 3 rewarded (23 max/day)
  Plus:    99 total, no ads, fair-use cap
"""
import base64
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

# tiny valid JPEG (1x1)
_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AL+A/9k="
)


@pytest.fixture(scope="module")
def user():
    ts = int(time.time() * 1000)
    email = f"TEST_plan_{ts}@c1.app"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "Plan Tester"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    user_id = r.json()["user_id"]
    requests.patch(
        f"{API}/auth/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"age": 30, "gender": "male", "height_cm": 180, "weight_kg": 80, "activity": "moderate", "goal": "maintain"},
    )
    yield {"email": email, "token": token, "id": user_id}
    requests.delete(f"{API}/auth/account", headers={"Authorization": f"Bearer {token}"})


def H(u):
    return {"Authorization": f"Bearer {u['token']}"}


def _mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


def _clear_all(user_id: str):
    db = _mongo()
    db.scan_logs.delete_many({"user_id": user_id})
    db.rewarded_credits.delete_many({"user_id": user_id})


def _seed_scans(user_id: str, base: int = 0, rewarded: int = 0):
    db = _mongo()
    now = datetime.now(tz=timezone.utc)
    db.scan_logs.delete_many({"user_id": user_id})
    docs = []
    for i in range(base):
        docs.append({
            "id": f"seed-base-{uuid.uuid4().hex[:8]}",
            "user_id": user_id,
            "created_at": now - timedelta(minutes=i + 1),
            "items_count": 1,
            "kind": "base",
        })
    for i in range(rewarded):
        docs.append({
            "id": f"seed-rw-{uuid.uuid4().hex[:8]}",
            "user_id": user_id,
            "created_at": now - timedelta(minutes=base + i + 1),
            "items_count": 1,
            "kind": "rewarded",
        })
    if docs:
        db.scan_logs.insert_many(docs)


def _seed_credit(user_id: str, tx_id: str | None = None):
    """Insert one unconsumed rewarded credit."""
    db = _mongo()
    tx_id = tx_id or uuid.uuid4().hex
    db.rewarded_credits.insert_one({
        "id": f"c-{uuid.uuid4().hex[:8]}",
        "user_id": user_id,
        "transaction_id": tx_id,
        "granted_at": datetime.now(tz=timezone.utc),
        "consumed_at": None,
        "ad_unit": "test",
    })
    return tx_id


# ---------------------------------------------------------------------------
# Free tier
# ---------------------------------------------------------------------------
def test_01_me_defaults_to_free_plan(user):
    r = requests.get(f"{API}/auth/me", headers=H(user))
    assert r.status_code == 200
    d = r.json()
    assert d["plan"] == "free"
    assert d["premium"] is False


def test_02_scan_quota_free_defaults(user):
    _clear_all(user["id"])
    r = requests.get(f"{API}/scan-quota", headers=H(user))
    assert r.status_code == 200
    d = r.json()
    assert d["plan"] == "free"
    assert d["base_limit"] == 3
    assert d["base_used"] == 0
    assert d["base_remaining"] == 3
    assert d["rewarded_limit"] == 2
    assert d["rewarded_used"] == 0
    assert d["rewarded_remaining"] == 2
    assert d["rewarded_credits_available"] == 0
    assert d["blocked"] is False
    assert d["can_watch_ad"] is False   # still have base scans left
    assert d["fair_use_limit"] == 5      # 3 + 2


def test_03_failed_scan_does_not_count(user):
    _clear_all(user["id"])
    r = requests.post(f"{API}/ai/scan-meal", headers=H(user), json={"image_b64": "not_valid_base64!!"})
    assert r.status_code == 400
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["total_used"] == 0


def test_04_free_base_exhausted_returns_base_limit_reached(user):
    """After 3 base scans, next scan must be 429 with error=base_limit_reached and can_watch_ad=True."""
    _seed_scans(user["id"], base=3, rewarded=0)
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["base_used"] == 3
    assert q["base_remaining"] == 0
    assert q["can_watch_ad"] is True
    assert q["blocked"] is False   # not blocked — can still watch ad
    r = requests.post(f"{API}/ai/scan-meal", headers=H(user), json={"image_b64": _JPEG_B64})
    assert r.status_code == 429, r.text
    d = r.json().get("detail", {})
    assert d.get("error") == "base_limit_reached"
    assert d.get("plan") == "free"
    assert d.get("can_watch_ad") is True


def test_05_free_credit_grants_one_rewarded_scan(user):
    """With base=3 (exhausted) and 1 unconsumed credit, next scan should succeed as rewarded."""
    _seed_scans(user["id"], base=3, rewarded=0)
    _seed_credit(user["id"])
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["rewarded_credits_available"] == 1
    r = requests.post(f"{API}/ai/scan-meal", headers=H(user), json={"image_b64": _JPEG_B64})
    assert r.status_code == 200, r.text
    q2 = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q2["rewarded_used"] == 1
    assert q2["rewarded_credits_available"] == 0


def test_06_free_all_exhausted_blocks(user):
    """base=3 + rewarded=2 → fully blocked, can_watch_ad=False."""
    _clear_all(user["id"])
    _seed_scans(user["id"], base=3, rewarded=2)
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["blocked"] is True
    assert q["can_watch_ad"] is False
    assert q["rewarded_remaining"] == 0
    r = requests.post(f"{API}/ai/scan-meal", headers=H(user), json={"image_b64": _JPEG_B64})
    assert r.status_code == 429
    d = r.json()["detail"]
    assert d["error"] == "scan_limit_reached"
    assert d["fair_use_limit"] == 5


def test_07_recommend_gated_for_free(user):
    r = requests.post(f"{API}/ai/recommend", headers=H(user), json={"focus": "any", "only": "all"})
    assert r.status_code == 402
    assert r.json()["detail"]["error"] == "plus_required"


# ---------------------------------------------------------------------------
# Premium tier — 20 base + 3 rewarded
# ---------------------------------------------------------------------------
def test_10_upgrade_to_premium_limits(user):
    from tests.conftest import grant_plan_via_subscription
    grant_plan_via_subscription(user["id"], "premium")
    _clear_all(user["id"])
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["plan"] == "premium"
    assert q["base_limit"] == 20
    assert q["rewarded_limit"] == 3
    assert q["fair_use_limit"] == 23


def test_11_premium_base_exhausted_can_watch_ad(user):
    _seed_scans(user["id"], base=20, rewarded=0)
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["can_watch_ad"] is True
    assert q["blocked"] is False
    r = requests.post(f"{API}/ai/scan-meal", headers=H(user), json={"image_b64": _JPEG_B64})
    assert r.status_code == 429
    assert r.json()["detail"]["error"] == "base_limit_reached"


def test_12_premium_all_exhausted_blocks(user):
    _clear_all(user["id"])
    _seed_scans(user["id"], base=20, rewarded=3)
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["blocked"] is True
    r = requests.post(f"{API}/ai/scan-meal", headers=H(user), json={"image_b64": _JPEG_B64})
    assert r.status_code == 429
    assert r.json()["detail"]["error"] == "scan_limit_reached"


def test_13_recommend_still_gated_for_premium(user):
    r = requests.post(f"{API}/ai/recommend", headers=H(user), json={"focus": "any", "only": "all"})
    assert r.status_code == 402


# ---------------------------------------------------------------------------
# Plus tier — 99 hard cap, no rewarded flow
# ---------------------------------------------------------------------------
def test_20_upgrade_to_plus_limits(user):
    from tests.conftest import grant_plan_via_subscription
    grant_plan_via_subscription(user["id"], "plus")
    _clear_all(user["id"])
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["plan"] == "plus"
    assert q["base_limit"] == 99
    assert q["rewarded_limit"] == 0
    assert q["fair_use_limit"] == 99
    assert q["can_watch_ad"] is False
    assert q["blocked"] is False


def test_21_plus_scan_succeeds_and_counts(user):
    _clear_all(user["id"])
    r = requests.post(f"{API}/ai/scan-meal", headers=H(user), json={"image_b64": _JPEG_B64})
    assert r.status_code == 200, r.text
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["total_used"] == 1
    assert q["base_used"] == 1


def test_22_plus_at_fair_use_cap_blocks(user):
    _clear_all(user["id"])
    _seed_scans(user["id"], base=99, rewarded=0)
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["blocked"] is True
    assert q["can_watch_ad"] is False
    r = requests.post(f"{API}/ai/scan-meal", headers=H(user), json={"image_b64": _JPEG_B64})
    assert r.status_code == 429
    assert r.json()["detail"]["fair_use_limit"] == 99


def test_23_plus_does_not_consume_credits(user):
    """Even if a Plus user had a lingering credit, scans should be counted as 'base' not rewarded."""
    _clear_all(user["id"])
    _seed_credit(user["id"])
    r = requests.post(f"{API}/ai/scan-meal", headers=H(user), json={"image_b64": _JPEG_B64})
    assert r.status_code == 200
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    # credit still available (Plus doesn't touch rewarded_credits)
    assert q["rewarded_credits_available"] == 1


# ---------------------------------------------------------------------------
# Persistence across JWT re-login
# ---------------------------------------------------------------------------
def test_30_persistence_across_new_jwt(user):
    from tests.conftest import grant_plan_via_subscription
    grant_plan_via_subscription(user["id"], "premium")
    _clear_all(user["id"])
    _seed_scans(user["id"], base=5, rewarded=1)
    r = requests.post(f"{API}/auth/login", json={"email": user["email"], "password": "Test1234!"})
    assert r.status_code == 200
    new_token = r.json()["token"]
    q = requests.get(f"{API}/scan-quota", headers={"Authorization": f"Bearer {new_token}"}).json()
    assert q["base_used"] == 5
    assert q["rewarded_used"] == 1
    assert q["total_used"] == 6
    assert q["plan"] == "premium"


def test_31_downgrade_to_free_updates_legacy_bool(user):
    from tests.conftest import grant_plan_via_subscription
    grant_plan_via_subscription(user["id"], "free")
    r = requests.get(f"{API}/auth/me", headers=H(user))
    me = r.json()
    assert me["plan"] == "free" and me["premium"] is False
