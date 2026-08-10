"""IAP HTTP routes. Mounted at /api/iap/* by server.py.

Phase 1: All purchase/verify/webhook routes return 501 with a documented placeholder body.
Only GET /api/entitlement is fully wired against `effective_plan()`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from .common import EntitlementOut, Platform
from .effective_plan import entitlement_snapshot

router = APIRouter(prefix="/iap")


def _not_implemented(feature: str):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "error": "not_implemented",
            "feature": feature,
            "phase": "This endpoint activates in Phase 2 (Apple) / Phase 3 (Google).",
        },
    )


class AppleVerifyIn(BaseModel):
    jws_representation: str
    transaction_id: str
    product_id: str


class GoogleVerifyIn(BaseModel):
    purchase_token: str
    subscription_id: str
    base_plan_id: str
    product_id: str


class RestoreIn(BaseModel):
    platform: Platform
    entries: list[dict]


# ---------------------------------------------------------------------------
# Placeholder routes (501)
# ---------------------------------------------------------------------------
@router.post("/apple/verify")
async def apple_verify(_: AppleVerifyIn):
    _not_implemented("apple_verify")


@router.post("/google/verify")
async def google_verify(_: GoogleVerifyIn):
    _not_implemented("google_verify")


@router.post("/restore")
async def restore(_: RestoreIn):
    _not_implemented("restore")


@router.post("/apple/webhook")
async def apple_webhook(request: Request):
    _not_implemented("apple_webhook")


@router.post("/google/webhook")
async def google_webhook(request: Request):
    _not_implemented("google_webhook")
