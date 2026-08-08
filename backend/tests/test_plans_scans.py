"""Tests for scan limits, plan gating, and quota persistence (iteration 5)."""
import base64
import os
import time
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
    # onboard so calc doesn't fail
    requests.patch(
        f"{API}/auth/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"age": 30, "gender": "male", "height_cm": 180, "weight_kg": 80, "activity": "moderate", "goal": "maintain"},
    )
    yield {"email": email, "token": token, "id": user_id}
    # cleanup
    requests.delete(f"{API}/auth/account", headers={"Authorization": f"Bearer {token}"})


def H(u):
    return {"Authorization": f"Bearer {u['token']}"}


def _mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


def _seed_scans(user_id: str, n: int):
    db = _mongo()
    now = datetime.now(tz=timezone.utc)
    db.scan_logs.delete_many({"user_id": user_id})
    if n > 0:
        db.scan_logs.insert_many([
            {"id": f"seed-{i}", "user_id": user_id, "created_at": now - timedelta(minutes=i + 1), "items_count": 1}
            for i in range(n)
        ])


def test_01_me_defaults_to_free_plan(user):
    r = requests.get(f"{API}/auth/me", headers=H(user))
    assert r.status_code == 200
    d = r.json()
    assert d["plan"] == "free"
    assert d["premium"] is False


def test_02_scan_quota_free_defaults(user):
    _seed_scans(user["id"], 0)
    r = requests.get(f"{API}/scan-quota", headers=H(user))
    assert r.status_code == 200
    d = r.json()
    assert d["plan"] == "free"
    assert d["limit"] == 4
    assert d["used"] == 0
    assert d["remaining"] == 4
    assert d["blocked"] is False


def test_03_failed_scan_does_not_count(user):
    _seed_scans(user["id"], 0)
    r = requests.post(f"{API}/ai/scan-meal", headers=H(user), json={"image_b64": "not_valid_base64!!"})
    # invalid image → 400 (b64decode length must be multiple of 4)
    assert r.status_code == 400
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["used"] == 0


def test_04_free_scan_429_when_seeded_at_limit(user):
    _seed_scans(user["id"], 4)
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["used"] == 4 and q["remaining"] == 0 and q["blocked"] is True and q["limit"] == 4
    r = requests.post(f"{API}/ai/scan-meal", headers=H(user), json={"image_b64": _JPEG_B64})
    assert r.status_code == 429, r.text
    body = r.json()
    d = body.get("detail", {})
    assert d.get("error") == "scan_limit_reached"
    assert d.get("plan") == "free"
    assert d.get("limit") == 4
    assert d.get("reset_at")
    assert "message" in d


def test_05_recommend_gated_for_free(user):
    r = requests.post(f"{API}/ai/recommend", headers=H(user), json={"focus": "any", "only": "all"})
    assert r.status_code == 402
    assert r.json()["detail"]["error"] == "plus_required"


def test_06_upgrade_to_premium_shows_limit_20(user):
    r = requests.post(f"{API}/auth/plan", headers=H(user), json={"plan": "premium"})
    assert r.status_code == 200
    me = r.json()
    assert me["plan"] == "premium" and me["premium"] is True
    _seed_scans(user["id"], 0)
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["limit"] == 20 and q["plan"] == "premium" and q["used"] == 0 and q["remaining"] == 20


def test_07_premium_at_limit_blocks(user):
    _seed_scans(user["id"], 20)
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["blocked"] is True and q["remaining"] == 0
    r = requests.post(f"{API}/ai/scan-meal", headers=H(user), json={"image_b64": _JPEG_B64})
    assert r.status_code == 429
    assert r.json()["detail"]["plan"] == "premium"
    assert r.json()["detail"]["limit"] == 20


def test_08_recommend_still_gated_for_premium(user):
    r = requests.post(f"{API}/ai/recommend", headers=H(user), json={"focus": "any", "only": "all"})
    assert r.status_code == 402
    assert r.json()["detail"]["error"] == "plus_required"
    r2 = requests.post(
        f"{API}/ai/recommend/refine",
        headers=H(user),
        json={
            "session_id": "s1",
            "item": {"id": "x", "kind": "meal", "name": "n", "calories": 100, "protein_g": 10, "carbs_g": 10, "fat_g": 5},
            "request": "make it vegetarian",
        },
    )
    assert r2.status_code == 402


def test_09_upgrade_to_plus(user):
    r = requests.post(f"{API}/auth/plan", headers=H(user), json={"plan": "plus"})
    assert r.status_code == 200
    me = r.json()
    assert me["plan"] == "plus" and me["premium"] is True  # legacy bool includes plus
    _seed_scans(user["id"], 0)
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["plan"] == "plus"
    assert q["limit"] is None
    assert q["fair_use_limit"] == 60
    assert q["blocked"] is False


def test_10_plus_scan_succeeds_and_counts(user):
    _seed_scans(user["id"], 0)
    r = requests.post(f"{API}/ai/scan-meal", headers=H(user), json={"image_b64": _JPEG_B64})
    assert r.status_code == 200, r.text
    assert "items" in r.json()
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["used"] == 1


def test_11_persistence_across_new_jwt(user):
    # Set to premium and seed 3 scans
    requests.post(f"{API}/auth/plan", headers=H(user), json={"plan": "premium"})
    _seed_scans(user["id"], 3)
    # Login again → new JWT for same user
    r = requests.post(f"{API}/auth/login", json={"email": user["email"], "password": "Test1234!"})
    assert r.status_code == 200
    new_token = r.json()["token"]
    q = requests.get(f"{API}/scan-quota", headers={"Authorization": f"Bearer {new_token}"}).json()
    assert q["used"] == 3
    assert q["plan"] == "premium"
    assert q["remaining"] == 17


def test_12_downgrade_to_free_updates_legacy_bool(user):
    r = requests.post(f"{API}/auth/plan", headers=H(user), json={"plan": "free"})
    assert r.status_code == 200
    me = r.json()
    assert me["plan"] == "free" and me["premium"] is False
