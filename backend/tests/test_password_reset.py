"""Tests for the new password reset flow (/api/auth/forgot-password + /api/auth/reset-password).

The plaintext 6-digit code is only ever delivered by email in production, so these tests
write directly to Mongo via pymongo to (a) inspect the `password_resets` row created by
/forgot-password and (b) mint a known-plaintext code before calling /reset-password.
"""
import hashlib
import os
import time
from datetime import datetime, timezone, timedelta

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://frontend-verify-9.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


def _sha(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def user():
    email = f"TEST_pwreset_{int(time.time())}@c1.app"
    pw = "OldPass123!"
    r = requests.post(f"{BASE}/api/auth/register",
                      json={"email": email, "password": pw, "name": "PW Reset User"})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    yield {"email": email, "old": pw, "token": tok}
    try:
        requests.delete(f"{BASE}/api/auth/account", headers={"Authorization": f"Bearer {tok}"})
    except Exception:
        pass


def _mint_known_code(db, email: str, code: str = "123456", minutes: int = 15) -> str:
    """Invalidate any existing rows and insert a fresh row with a known-plaintext code."""
    db.password_resets.update_many(
        {"email": email, "used": False},
        {"$set": {"used": True, "invalidated_at": datetime.now(tz=timezone.utc)}},
    )
    db.password_resets.insert_one({
        "email": email,
        "code_hash": _sha(code),
        "attempts": 0,
        "created_at": datetime.now(tz=timezone.utc),
        "expires_at": datetime.now(tz=timezone.utc) + timedelta(minutes=minutes),
        "used": False,
    })
    return code


# ---------- 1. forgot-password (no enumeration + row created) ----------
def test_forgot_password_unregistered_generic_ok(db):
    bogus = f"TEST_unreg_{int(time.time()*1000)}@c1.app"
    r = requests.post(f"{BASE}/api/auth/forgot-password", json={"email": bogus})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert "message" in body
    assert db.password_resets.find_one({"email": bogus.lower()}) is None, \
        "Should not create reset row for unregistered email"


def test_forgot_password_registered_creates_row(user, db):
    email = user["email"].lower()
    r = requests.post(f"{BASE}/api/auth/forgot-password", json={"email": user["email"]})
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True
    time.sleep(0.4)
    row = db.password_resets.find_one({"email": email, "used": False})
    assert row is not None, "password_resets doc not created for registered user"
    assert isinstance(row.get("code_hash"), str) and len(row["code_hash"]) == 64
    assert row.get("attempts", 0) == 0
    assert row.get("used") is False
    exp = row["expires_at"]
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    delta = exp - datetime.now(tz=timezone.utc)
    assert timedelta(minutes=10) < delta < timedelta(minutes=20), f"Unexpected TTL: {delta}"


# ---------- 2. reset-password: wrong code increments attempts ----------
def test_reset_password_wrong_code_increments_attempts(user, db):
    email = user["email"].lower()
    _mint_known_code(db, email, code="424242")
    r = requests.post(f"{BASE}/api/auth/reset-password", json={
        "email": email, "code": "000000", "new_password": "NewPass123!"
    })
    assert r.status_code == 400, r.text
    row = db.password_resets.find_one({"email": email, "used": False})
    assert row is not None
    assert row.get("attempts", 0) == 1, f"attempts not incremented, got {row.get('attempts')}"


# ---------- 3. success + replay protection + login change ----------
def test_reset_password_success_then_replay_fails(user, db):
    email = user["email"].lower()
    code = _mint_known_code(db, email, code="654321")
    new_pw = "BrandNew123!"
    r = requests.post(f"{BASE}/api/auth/reset-password", json={
        "email": email, "code": code, "new_password": new_pw
    })
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True

    # Old password rejected
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": user["old"]})
    assert r.status_code == 401, "Old password should be rejected after reset"

    # New password works
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": new_pw})
    assert r.status_code == 200, r.text
    user["token"] = r.json()["token"]
    user["old"] = new_pw  # keep fixture cleanup working

    # Replay must fail (row now used)
    r = requests.post(f"{BASE}/api/auth/reset-password", json={
        "email": email, "code": code, "new_password": "Another123!"
    })
    assert r.status_code == 400, f"Replay of used code should fail, got {r.status_code}: {r.text}"


# ---------- 4. new forgot invalidates prior unused code ----------
def test_new_forgot_invalidates_prior_unused(user, db):
    email = user["email"].lower()
    _mint_known_code(db, email, code="111111")
    r = requests.post(f"{BASE}/api/auth/forgot-password", json={"email": email})
    assert r.status_code == 200
    time.sleep(0.4)
    unused = list(db.password_resets.find({"email": email, "used": False}))
    assert len(unused) == 1, f"expected exactly 1 unused row, got {len(unused)}"
    assert unused[0]["code_hash"] != _sha("111111"), "Prior code should have been invalidated"
    # Using the invalidated code must fail
    r = requests.post(f"{BASE}/api/auth/reset-password", json={
        "email": email, "code": "111111", "new_password": "Nope1234!"
    })
    assert r.status_code == 400
