"""Effective-plan derivation. The single source of truth for entitlement.

Rules:
  - Read only from the `subscriptions` collection.
  - Never accept a client-supplied plan value.
  - `expires_at` is the store's canonical expiration; we never mutate it.
  - `grace_period_expires_at` is a *separate*, store-provided extension.
  - A subscription is "effective" if:
       revoked == False
       AND status not in {"revoked", "paused"}
       AND now < expires_at   OR   now < (grace_period_expires_at or 0)
  - Among multiple effective subs, the highest rank wins (plus > premium).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from .common import EntitlementOut, Plan, rank_of


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _as_aware(dt):
    """Coerce Mongo's naive UTC datetimes to timezone-aware for safe comparison."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_effective(sub: dict, now: datetime) -> bool:
    if sub.get("revoked"):
        return False
    if sub.get("status") in ("revoked", "paused"):
        return False
    exp = _as_aware(sub.get("expires_at"))
    grace = _as_aware(sub.get("grace_period_expires_at"))
    if exp and now < exp:
        return True
    if grace and now < grace:
        return True
    return False


async def _active_subscriptions(db: AsyncIOMotorDatabase, user_id: str) -> list[dict]:
    now = _now()
    # Broad query; final filter in Python so we can honor grace_period_expires_at cleanly.
    cursor = db.subscriptions.find(
        {"user_id": user_id, "revoked": {"$ne": True}},
        {"_id": 0},
    )
    docs = await cursor.to_list(50)
    return [d for d in docs if _is_effective(d, now)]


async def effective_plan(db: AsyncIOMotorDatabase, user_id: str) -> Plan:
    """Return the highest-rank plan the user currently holds. Derived only."""
    subs = await _active_subscriptions(db, user_id)
    if not subs:
        return "free"
    best = max(subs, key=lambda s: rank_of(s.get("tier", "free")))
    tier = best.get("tier")
    return tier if tier in ("premium", "plus") else "free"


async def entitlement_snapshot(db: AsyncIOMotorDatabase, user_id: str) -> EntitlementOut:
    subs = await _active_subscriptions(db, user_id)
    if not subs:
        return EntitlementOut(plan="free")
    best = max(subs, key=lambda s: rank_of(s.get("tier", "free")))
    now = _now()
    grace = _as_aware(best.get("grace_period_expires_at"))
    exp = _as_aware(best.get("expires_at"))
    in_grace = bool(grace and now < grace and (not exp or now >= exp))
    manage_url = (
        "https://apps.apple.com/account/subscriptions"
        if best.get("platform") == "apple"
        else "https://play.google.com/store/account/subscriptions"
    )
    return EntitlementOut(
        plan=best.get("tier") if best.get("tier") in ("premium", "plus") else "free",
        tier_source=best.get("product_id"),
        platform=best.get("platform"),
        expires_at=exp,
        grace_period_expires_at=grace,
        in_grace=in_grace,
        auto_renew=bool(best.get("auto_renew")),
        will_renew_at=exp if best.get("auto_renew") else None,
        manage_url=manage_url,
        trial={"end_at": best.get("trial_end_at")} if best.get("in_trial") else None,
        canceled_at=best.get("cancellation_date"),
    )


async def recompute_and_cache_plan(db: AsyncIOMotorDatabase, user_id: str) -> Plan:
    """Recompute the derived plan and update the users.plan cache projection."""
    plan = await effective_plan(db, user_id)
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"plan": plan, "premium": plan in ("premium", "plus"), "plan_recomputed_at": _now()}},
    )
    return plan


# ---------------------------------------------------------------------------
# FastAPI dependency helpers
# ---------------------------------------------------------------------------
class PlanRequirementError(Exception):
    def __init__(self, required: str, actual: str):
        self.required = required
        self.actual = actual
        super().__init__(f"plan '{required}' required (have '{actual}')")


async def check_plan_requirement(
    db: AsyncIOMotorDatabase, user_id: str, min_tier: Plan
) -> Plan:
    """Raises PlanRequirementError if the user's derived plan is below min_tier."""
    plan = await effective_plan(db, user_id)
    if rank_of(plan) < rank_of(min_tier):
        raise PlanRequirementError(min_tier, plan)
    return plan
