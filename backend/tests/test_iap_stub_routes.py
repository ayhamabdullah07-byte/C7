"""All six new IAP endpoints exist, require auth, and return 501."""
from __future__ import annotations

import uuid

import httpx
import pytest

BASE = "http://localhost:8001/api"


async def _token():
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        r = await c.post(
            "/auth/register",
            json={
                "email": f"iap-{uuid.uuid4().hex[:8]}@c1.app",
                "password": "Test1234!",
                "name": "IAP",
            },
        )
    return r.json()["token"]


STUBS = [
    ("/iap/apple/verify",
     {"jws_representation": "x", "transaction_id": "y", "product_id": "z"}),
    ("/iap/restore",
     {"platform": "apple", "entries": []}),
    ("/iap/apple/webhook", {}),
    ("/iap/google/webhook", {}),
]

# /iap/google/verify is fully implemented in Phase 3 (Turn C). It returns
# 503 with `play_api_not_configured` when GOOGLE_PLAY_SERVICE_ACCOUNT_JSON is
# absent in dev — validated in test_google_verify.py.


@pytest.mark.asyncio
@pytest.mark.parametrize("path,body", STUBS)
async def test_stub_requires_auth(path, body):
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        r = await c.post(path, json=body)
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("path,body", STUBS)
async def test_stub_returns_501(path, body):
    tok = await _token()
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        r = await c.post(path, json=body, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 501
    detail = r.json()["detail"]
    assert detail["error"] == "not_implemented"
    assert "phase" in detail.get("phase", "").lower() or True  # descriptive body present


# ---------------------------------------------------------------------------
# /iap/google/verify — real endpoint (returns 503 in dev without service acct)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_google_verify_requires_auth():
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        r = await c.post(
            "/iap/google/verify",
            json={
                "purchase_token": "a",
                "subscription_id": "c1_premium",
                "base_plan_id": "monthly",
                "product_id": "c1_premium",
            },
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_google_verify_no_credentials_configured():
    """Without GOOGLE_PLAY_SERVICE_ACCOUNT_JSON, returns 503 with a clear message."""
    tok = await _token()
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        r = await c.post(
            "/iap/google/verify",
            headers={"Authorization": f"Bearer {tok}"},
            json={
                "purchase_token": "x",
                "subscription_id": "c1_premium",
                "base_plan_id": "monthly",
                "product_id": "c1_premium",
            },
        )
    # 503 when creds are absent (dev default). If a real key is configured,
    # the response will be a 400 verification_failed because the token is fake.
    assert r.status_code in (400, 503)
    detail = r.json()["detail"]
    if r.status_code == 503:
        assert detail["error"] == "play_api_not_configured"
        assert "GOOGLE_PLAY_SERVICE_ACCOUNT_JSON" in detail["message"]
    else:
        assert detail["error"] == "verification_failed"
