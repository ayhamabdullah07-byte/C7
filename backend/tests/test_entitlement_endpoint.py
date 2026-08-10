"""End-to-end tests for GET /api/entitlement + removed endpoints + IAP stubs.

Runs against the live server at http://localhost:8001/api.
"""
from __future__ import annotations

import uuid

import httpx
import pytest

BASE = "http://localhost:8001/api"


async def _register():
    email = f"e2e-{uuid.uuid4().hex[:8]}@c1.app"
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        r = await c.post(
            "/auth/register",
            json={"email": email, "password": "Test1234!", "name": "E2E"},
        )
    r.raise_for_status()
    return r.json()["token"], email


@pytest.mark.asyncio
async def test_entitlement_new_user_is_free():
    token, _ = await _register()
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        r = await c.get("/entitlement", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "free"
    assert body["expires_at"] is None
    assert body["in_grace"] is False


@pytest.mark.asyncio
async def test_entitlement_requires_auth():
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        r = await c.get("/entitlement")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_free_plan_for_new_user():
    token, _ = await _register()
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        r = await c.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["plan"] == "free"
    assert r.json()["premium"] is False
