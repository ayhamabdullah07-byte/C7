"""IAP HTTP routes. Mounted at /api/iap/* by server.py."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from deps import get_current_user
from .common import EntitlementOut, Platform, dedupe_hash
from .effective_plan import entitlement_snapshot, recompute_and_cache_plan
from . import google as google_iap

router = APIRouter(prefix="/iap")
logger = logging.getLogger("c1.iap")


def _not_implemented(feature: str):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "error": "not_implemented",
            "feature": feature,
            "phase": "This endpoint activates in the next phase.",
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
# Apple — still stubbed
# ---------------------------------------------------------------------------
@router.post("/apple/verify")
async def apple_verify(_: AppleVerifyIn):
    _not_implemented("apple_verify")


@router.post("/apple/webhook")
async def apple_webhook(request: Request):
    _not_implemented("apple_webhook")


# ---------------------------------------------------------------------------
# Google — real verification
# ---------------------------------------------------------------------------
@router.post("/google/verify")
async def google_verify(
    inp: GoogleVerifyIn,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Verify a Google Play purchase token, upsert the subscription doc,
    and refresh the user's cached plan projection."""
    ok, err = google_iap.credentials_configured()
    if not ok:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "play_api_not_configured",
                "message": (
                    "Google Play Developer API credentials are not set on the server. "
                    "Add GOOGLE_PLAY_SERVICE_ACCOUNT_JSON to backend/.env (either the "
                    "JSON string or a filesystem path to the service-account key)."
                ),
                "reason": err,
            },
        )

    # 1. Verify with Google (source of truth)
    try:
        snapshot = await google_iap.verify_and_normalize(
            inp.purchase_token, inp.subscription_id, inp.base_plan_id
        )
    except RuntimeError as e:
        raise HTTPException(400, detail={"error": "verification_failed", "message": str(e)})
    except Exception:
        logger.exception("google_verify unexpected error")
        raise HTTPException(500, "Google verification error")

    # 2. Upsert by purchase_token — idempotent for retries
    from motor.motor_asyncio import AsyncIOMotorDatabase  # type: ignore

    db: AsyncIOMotorDatabase = request.app.state.db  # set by server.py startup

    now = datetime.now(tz=timezone.utc)
    snapshot["user_id"] = user["id"]
    filt = {"platform": "google", "purchase_token": inp.purchase_token}
    existing = await db.subscriptions.find_one(filt)
    if existing:
        # Update mutable fields only; keep id + created_at
        snapshot.pop("created_at", None)
        snapshot["updated_at"] = now
        await db.subscriptions.update_one(filt, {"$set": snapshot})
        sub_id = existing["id"]
    else:
        snapshot["id"] = f"s-{uuid.uuid4().hex[:12]}"
        snapshot["created_at"] = now
        snapshot["updated_at"] = now
        await db.subscriptions.insert_one(snapshot)
        sub_id = snapshot["id"]

    # 3. Audit-log the verify event
    raw = str(snapshot.get("raw_state_snapshot") or "")
    try:
        await db.iap_events.insert_one(
            {
                "id": f"e-{uuid.uuid4().hex[:12]}",
                "user_id": user["id"],
                "platform": "google",
                "event_type": "verify",
                "notification_type": snapshot.get("status"),
                "raw_payload_hash": dedupe_hash(raw),
                "subscription_id": sub_id,
                "processed": True,
                "received_at": now,
                "processed_at": now,
            }
        )
    except Exception:
        # index conflict on a re-verify is fine — non-fatal
        logger.debug("iap_events insert skipped/duplicate", exc_info=True)

    # 4. Refresh cached plan projection
    plan = await recompute_and_cache_plan(db, user["id"])
    snap = await entitlement_snapshot(db, user["id"])

    return {
        "ok": True,
        "plan": plan,
        "period": snapshot.get("period"),
        "entitlement": snap.model_dump(mode="json"),
    }


@router.post("/google/webhook")
async def google_webhook(request: Request):
    _not_implemented("google_webhook_rtdn")


# ---------------------------------------------------------------------------
# Restore purchases — stub for now
# ---------------------------------------------------------------------------
@router.post("/restore")
async def restore(_: RestoreIn):
    _not_implemented("restore")
