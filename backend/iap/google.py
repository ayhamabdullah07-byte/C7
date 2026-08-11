"""Google Play Developer API integration for subscription verification.

Uses `androidpublisher.purchases.subscriptionsv2.get` — the canonical source
of subscription state. RTDN is a signal only; entitlement is always derived
from this endpoint.

Requires env:
  GOOGLE_PLAY_PACKAGE_NAME   — defaults to com.ayhamabdullah.c1
  GOOGLE_PLAY_SERVICE_ACCOUNT_JSON — either an inline JSON string OR a filesystem path
                                     to the service-account JSON key with the
                                     androidpublisher scope. Optional in dev —
                                     when absent, /iap/google/verify returns 503
                                     with a clear "not configured" message.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("c1.iap.google")

PACKAGE_NAME = os.environ.get("GOOGLE_PLAY_PACKAGE_NAME", "com.ayhamabdullah.c1")
SCOPE = "https://www.googleapis.com/auth/androidpublisher"

_SERVICE_ACCOUNT_INFO: Optional[dict] = None
_CREDS_ERROR: Optional[str] = None


def _load_service_account_info() -> Optional[dict]:
    """Load service-account JSON from env — either inline or from a file path."""
    global _SERVICE_ACCOUNT_INFO, _CREDS_ERROR
    if _SERVICE_ACCOUNT_INFO is not None:
        return _SERVICE_ACCOUNT_INFO
    raw = os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        _CREDS_ERROR = (
            "GOOGLE_PLAY_SERVICE_ACCOUNT_JSON is not set. Provide either the JSON "
            "content or the absolute filesystem path to your Play Developer API "
            "service-account key."
        )
        return None
    try:
        if raw.startswith("{"):
            _SERVICE_ACCOUNT_INFO = json.loads(raw)
        else:
            with open(raw, "r", encoding="utf-8") as f:
                _SERVICE_ACCOUNT_INFO = json.load(f)
    except Exception as e:
        _CREDS_ERROR = f"Failed to load service-account credentials: {e}"
        logger.exception("Failed to load Play service-account")
        return None
    return _SERVICE_ACCOUNT_INFO


def _google_creds():
    """Return authorized google-auth Credentials with the androidpublisher scope."""
    info = _load_service_account_info()
    if not info:
        return None
    # Lazy imports — only when configured, so dev/test doesn't need google-auth.
    from google.oauth2 import service_account  # type: ignore

    return service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])


def credentials_configured() -> tuple[bool, Optional[str]]:
    """Return (available, error_message). Used by /iap/google/verify to fail
    fast with a helpful 503 when the operator hasn't provisioned creds yet."""
    creds = _google_creds()
    return (creds is not None), _CREDS_ERROR


async def _get_access_token() -> Optional[str]:
    creds = _google_creds()
    if not creds:
        return None
    from google.auth.transport.requests import Request as GARequest  # type: ignore

    # Refresh synchronously — google-auth is sync-only but the token cache is O(1)
    # in the hot path so this is fine inside an async request.
    if not creds.valid:
        creds.refresh(GARequest())
    return creds.token


async def fetch_subscriptionsv2(purchase_token: str) -> dict:
    """Call subscriptionsv2.get. Returns the raw JSON body."""
    token = await _get_access_token()
    if not token:
        raise RuntimeError("Play API credentials not configured")
    url = (
        "https://androidpublisher.googleapis.com/androidpublisher/v3/"
        f"applications/{PACKAGE_NAME}/purchases/subscriptionsv2/tokens/{purchase_token}"
    )
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        # Play API returns structured error info in body — include for debugging.
        logger.warning("subscriptionsv2.get %s → %s", r.status_code, r.text[:400])
        raise RuntimeError(f"Play API returned {r.status_code}: {r.text[:200]}")
    return r.json()


async def acknowledge_subscription(purchase_token: str, subscription_id: str) -> None:
    """Acknowledge to prevent auto-refund after the 3-day window. Idempotent."""
    token = await _get_access_token()
    if not token:
        raise RuntimeError("Play API credentials not configured")
    url = (
        "https://androidpublisher.googleapis.com/androidpublisher/v3/"
        f"applications/{PACKAGE_NAME}/purchases/subscriptions/{subscription_id}/"
        f"tokens/{purchase_token}:acknowledge"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json={})
    if r.status_code not in (200, 204):
        logger.warning("acknowledge %s → %s %s", subscription_id, r.status_code, r.text[:300])
        # Not fatal — a later reconcile can retry.


# ---------------------------------------------------------------------------
# High-level verify: called from the /iap/google/verify HTTP route
# ---------------------------------------------------------------------------
def _parse_iso(dt: Optional[str]) -> Optional[datetime]:
    if not dt:
        return None
    try:
        # Play returns RFC 3339 with 'Z'
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except Exception:
        return None


async def verify_and_normalize(
    purchase_token: str, subscription_id: str, base_plan_id: str
) -> dict:
    """Verify a purchase token + return a normalized snapshot ready to upsert.

    Raises RuntimeError with a user-facing reason if verification fails.
    """
    from .common import resolve_google_product  # circular-safe: same package

    mapping = resolve_google_product(subscription_id, base_plan_id)
    if not mapping:
        raise RuntimeError(
            f"Unknown Google product '{subscription_id}/{base_plan_id}'. "
            "Create it in Play Console → Monetize → Subscriptions."
        )
    tier, period = mapping

    body = await fetch_subscriptionsv2(purchase_token)

    # Defensive checks — Play must confirm the productId matches
    line_items = body.get("lineItems") or []
    matching = next(
        (li for li in line_items if li.get("productId") == subscription_id),
        None,
    )
    if not matching:
        raise RuntimeError(
            f"Purchase token does not include product '{subscription_id}'."
        )
    expiry_time = _parse_iso(matching.get("expiryTime"))
    if not expiry_time:
        raise RuntimeError("Play response missing expiryTime.")

    state = body.get("subscriptionState")
    if state not in ("SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"):
        raise RuntimeError(f"Subscription not active: {state}")

    now = datetime.now(tz=timezone.utc)
    normalized = {
        "platform": "google",
        "product_id": subscription_id,
        "base_plan_id": base_plan_id,
        "tier": tier,
        "period": period,
        "purchase_token": purchase_token,
        "linked_purchase_token": body.get("linkedPurchaseToken"),
        "status": (
            "in_grace" if state == "SUBSCRIPTION_STATE_IN_GRACE_PERIOD" else "active"
        ),
        "auto_renew": bool(
            (body.get("subscribeWithGoogleInfo") or {}).get("givenName")
            is not None
            or (matching.get("autoRenewingPlan") or {}).get("autoRenewEnabled", True)
        ),
        "purchase_date": _parse_iso(body.get("startTime")) or now,
        "expires_at": expiry_time,
        "original_purchase_date": _parse_iso(body.get("startTime")) or now,
        "grace_period_expires_at": None,  # Play exposes this as state=IN_GRACE; expiry_time carries it
        "environment": "production",
        "revoked": False,
        "raw_state_snapshot": body,
        "created_at": now,
        "updated_at": now,
        "last_webhook_at": now,
    }

    # Best-effort acknowledgement so Google doesn't auto-refund the purchase.
    ack_state = body.get("acknowledgementState")
    if ack_state == "ACKNOWLEDGEMENT_STATE_PENDING":
        try:
            await acknowledge_subscription(purchase_token, subscription_id)
            normalized["raw_state_snapshot"]["_acknowledged_at"] = now.isoformat()
        except Exception as e:
            logger.warning("acknowledge failed for token=%s: %s", purchase_token[:12], e)

    return normalized


# ---------------------------------------------------------------------------
# Legacy stubs kept for import compatibility
# ---------------------------------------------------------------------------
async def verify_purchase(
    purchase_token: str, subscription_id: str, base_plan_id: str
) -> dict:
    return await verify_and_normalize(purchase_token, subscription_id, base_plan_id)


async def refetch_subscription(purchase_token: str) -> dict:
    return await fetch_subscriptionsv2(purchase_token)


async def handle_rtdn(pubsub_message: dict) -> dict:
    """RTDN handler stays a stub — Phase 3 (RTDN) lands separately from purchase verify."""
    raise NotImplementedError("RTDN handling arrives in a follow-up phase.")
