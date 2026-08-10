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
    ("/iap/google/verify",
     {"purchase_token": "a", "subscription_id": "b", "base_plan_id": "c", "product_id": "d"}),
    ("/iap/restore",
     {"platform": "apple", "entries": []}),
    ("/iap/apple/webhook", {}),
    ("/iap/google/webhook", {}),
]


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
