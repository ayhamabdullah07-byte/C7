"""Confirms /api/auth/plan and /api/auth/premium-toggle return 410 Gone."""
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
                "email": f"rm-{uuid.uuid4().hex[:8]}@c1.app",
                "password": "Test1234!",
                "name": "Rm",
            },
        )
    return r.json()["token"]


@pytest.mark.asyncio
async def test_plan_endpoint_removed():
    tok = await _token()
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        r = await c.post(
            "/auth/plan",
            json={"plan": "plus"},
            headers={"Authorization": f"Bearer {tok}"},
        )
    assert r.status_code == 410
    body = r.json()
    assert body["detail"]["error"] == "endpoint_removed"
    assert "/api/iap/" in body["detail"]["migrated_to"]


@pytest.mark.asyncio
async def test_premium_toggle_removed():
    tok = await _token()
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        r = await c.post(
            "/auth/premium-toggle",
            headers={"Authorization": f"Bearer {tok}"},
        )
    assert r.status_code == 410
    body = r.json()
    assert body["detail"]["error"] == "endpoint_removed"


@pytest.mark.asyncio
async def test_plan_endpoint_cannot_grant_paid_access():
    """Belt-and-braces: even if 410 changes to something else, /entitlement stays free."""
    tok = await _token()
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        await c.post(
            "/auth/plan",
            json={"plan": "plus"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        r = await c.get("/entitlement", headers={"Authorization": f"Bearer {tok}"})
    assert r.json()["plan"] == "free"
