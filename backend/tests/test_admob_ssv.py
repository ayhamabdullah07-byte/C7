"""AdMob Server-Side Verification (SSV) endpoint tests.

Endpoints under test:
  POST /api/ai/rewarded/token   → JWT-auth, issues short-lived custom_data token
  GET  /api/ai/rewarded/redeem  → AdMob-called SSV callback (no user auth)

Signature verification is bypassed unless ADMOB_SSV_ENFORCE=true is set at process start,
so these tests exercise the token, dedupe, per-plan cap, and credit insertion paths.
"""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
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
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = os.environ.get("JWT_ALG", "HS256")


@pytest.fixture(scope="module")
def user():
    ts = int(time.time() * 1000)
    email = f"TEST_ssv_{ts}@c1.app"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "SSV Tester"})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    uid = r.json()["user_id"]
    requests.patch(
        f"{API}/auth/profile",
        headers={"Authorization": f"Bearer {tok}"},
        json={"age": 30, "gender": "male", "height_cm": 180, "weight_kg": 80, "activity": "moderate", "goal": "maintain"},
    )
    yield {"email": email, "token": tok, "id": uid}
    requests.delete(f"{API}/auth/account", headers={"Authorization": f"Bearer {tok}"})


def H(u):
    return {"Authorization": f"Bearer {u['token']}"}


def _mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


def _clear_credits(user_id: str):
    _mongo().rewarded_credits.delete_many({"user_id": user_id})


# ---------------------------------------------------------------------------
# Token issuance
# ---------------------------------------------------------------------------
def test_01_token_requires_auth():
    r = requests.post(f"{API}/ai/rewarded/token")
    assert r.status_code == 401


def test_02_token_ok_shape(user):
    r = requests.post(f"{API}/ai/rewarded/token", headers=H(user))
    assert r.status_code == 200
    d = r.json()
    assert "token" in d
    assert isinstance(d["expires_in"], int) and d["expires_in"] > 0
    claims = jwt.decode(d["token"], JWT_SECRET, algorithms=[JWT_ALG])
    assert claims["typ"] == "c1_rw"
    assert claims["sub"] == user["id"]


# ---------------------------------------------------------------------------
# SSV redeem
# ---------------------------------------------------------------------------
def _valid_token(user_id: str, minutes: int = 10) -> str:
    now = datetime.now(tz=timezone.utc)
    return jwt.encode(
        {"typ": "c1_rw", "sub": user_id, "iat": now, "exp": now + timedelta(minutes=minutes), "jti": uuid.uuid4().hex},
        JWT_SECRET,
        algorithm=JWT_ALG,
    )


def _ssv(**kw):
    """Perform a GET to the SSV endpoint with query params (mimicking AdMob)."""
    return requests.get(f"{API}/ai/rewarded/redeem", params=kw, allow_redirects=False)


def test_10_ssv_missing_params_returns_400(user):
    r = _ssv()
    assert r.status_code == 400


def test_11_ssv_invalid_token_400(user):
    r = _ssv(transaction_id=uuid.uuid4().hex, custom_data="not-a-jwt", signature="s", key_id="k")
    assert r.status_code == 400


def test_12_ssv_expired_token_400(user):
    tok = _valid_token(user["id"], minutes=-1)
    r = _ssv(transaction_id=uuid.uuid4().hex, custom_data=tok)
    assert r.status_code == 400


def test_13_ssv_valid_grants_credit(user):
    _clear_credits(user["id"])
    tok = _valid_token(user["id"])
    tx = uuid.uuid4().hex
    r = _ssv(
        transaction_id=tx, custom_data=tok, signature="sig", key_id="1",
        ad_network="admob", ad_unit="test", reward_amount="1", reward_item="scan",
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    # Confirm quota now shows the credit.
    q = requests.get(f"{API}/scan-quota", headers=H(user)).json()
    assert q["rewarded_credits_available"] >= 1


def test_14_ssv_idempotent_on_transaction_id(user):
    _clear_credits(user["id"])
    tok = _valid_token(user["id"])
    tx = uuid.uuid4().hex
    r1 = _ssv(transaction_id=tx, custom_data=tok)
    r2 = _ssv(transaction_id=tx, custom_data=tok)
    assert r1.status_code == 200
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2.get("duplicate") is True or body2.get("ok") is True
    # Only one credit exists.
    n = _mongo().rewarded_credits.count_documents({"user_id": user["id"], "transaction_id": tx})
    assert n == 1


def test_15_ssv_wrong_token_type_400(user):
    now = datetime.now(tz=timezone.utc)
    tok = jwt.encode({"typ": "wrong", "sub": user["id"], "exp": now + timedelta(minutes=5)}, JWT_SECRET, algorithm=JWT_ALG)
    r = _ssv(transaction_id=uuid.uuid4().hex, custom_data=tok)
    assert r.status_code == 400


def test_16_ssv_unknown_user_400():
    """Token signed for a non-existent user_id → 400."""
    now = datetime.now(tz=timezone.utc)
    tok = jwt.encode({"typ": "c1_rw", "sub": "ghost-user-does-not-exist", "exp": now + timedelta(minutes=5)},
                     JWT_SECRET, algorithm=JWT_ALG)
    r = _ssv(transaction_id=uuid.uuid4().hex, custom_data=tok)
    assert r.status_code == 400


def test_17_ssv_plus_plan_disallows_rewarded(user):
    """A Plus user should not accrue rewarded credits (they don't need them)."""
    from tests.conftest import grant_plan_via_subscription
    grant_plan_via_subscription(user["id"], "plus")
    _clear_credits(user["id"])
    tok = _valid_token(user["id"])
    r = _ssv(transaction_id=uuid.uuid4().hex, custom_data=tok)
    assert r.status_code == 400
    # revert to free for subsequent tests
    grant_plan_via_subscription(user["id"], "free")


def test_18_ssv_free_enforces_rewarded_cap(user):
    """Free plan allows at most 2 rewarded grants / 24h."""
    from tests.conftest import grant_plan_via_subscription
    grant_plan_via_subscription(user["id"], "free")
    _clear_credits(user["id"])
    tok = _valid_token(user["id"])
    ok = 0
    over_cap_hit = False
    for i in range(4):
        r = _ssv(transaction_id=uuid.uuid4().hex, custom_data=tok)
        if r.status_code == 200:
            ok += 1
        elif r.status_code == 429:
            over_cap_hit = True
    assert ok == 2
    assert over_cap_hit is True
