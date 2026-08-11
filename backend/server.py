"""C1 backend – nutrition tracker with AI meal recognition and coach.

All routes under /api/*.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Any, Literal, Optional

import bcrypt
import httpx
import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Header, Request, status
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

from emergentintegrations.llm.chat import (
    ImageContent,
    LlmChat,
    StreamDone,
    TextDelta,
    UserMessage,
)

from iap.common import PLUS_FAIR_USE_LIMIT, SCAN_LIMITS, plan_limits
from iap.effective_plan import (
    effective_plan,
    entitlement_snapshot,
    recompute_and_cache_plan,
)
from iap.routes import router as iap_router
from deps import get_current_user  # shared dep — used by iap.routes as well

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = os.environ.get("JWT_ALG", "HS256")
JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "720"))

# Emergent-managed email (Resend proxy)
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMERGENT_EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "C1")

AI_TEXT_MODEL = ("gemini", "gemini-3-flash-preview")
AI_VISION_MODEL = ("gemini", "gemini-3-flash-preview")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("c1")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="C1 API")
api = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
Gender = Literal["male", "female", "other"]
Activity = Literal["sedentary", "light", "moderate", "active", "very_active"]
Goal = Literal["lose", "maintain", "gain"]
MealType = Literal["breakfast", "lunch", "dinner", "snack"]
Plan = Literal["free", "premium", "plus"]

# SCAN_LIMITS and PLUS_FAIR_USE_LIMIT are imported from iap.common

ACTIVITY_MULT = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AuthOut(BaseModel):
    token: str
    user_id: str
    email: EmailStr
    name: str
    onboarded: bool
    premium: bool


class ProfileIn(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = Field(default=None, ge=10, le=120)
    gender: Optional[Gender] = None
    height_cm: Optional[float] = Field(default=None, ge=80, le=250)
    weight_kg: Optional[float] = Field(default=None, ge=25, le=400)
    target_weight_kg: Optional[float] = Field(default=None, ge=25, le=400)
    activity: Optional[Activity] = None
    goal: Optional[Goal] = None
    language: Optional[str] = None
    theme: Optional[Literal["light", "dark", "system"]] = None


class Targets(BaseModel):
    bmr: int
    tdee: int
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    water_ml: int


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    age: Optional[int] = None
    gender: Optional[Gender] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    target_weight_kg: Optional[float] = None
    activity: Optional[Activity] = None
    goal: Optional[Goal] = None
    language: str = "en"
    theme: str = "system"
    onboarded: bool = False
    plan: Plan = "free"
    premium: bool = False  # legacy: true for premium OR plus
    streak: int = 0
    best_streak: int = 0
    targets: Optional[Targets] = None
    created_at: datetime


class FoodItem(BaseModel):
    name: str
    portion_g: float = 100
    calories: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    fiber_g: float = 0
    sugar_g: float = 0


class MealIn(BaseModel):
    meal_type: MealType
    log_date: str  # YYYY-MM-DD
    items: list[FoodItem]
    photo_b64: Optional[str] = None
    note: Optional[str] = None


class MealOut(MealIn):
    id: str
    total_calories: float
    total_protein_g: float
    total_carbs_g: float
    total_fat_g: float
    created_at: datetime


class ScanIn(BaseModel):
    image_b64: str  # data URI or raw base64


class ScanOut(BaseModel):
    items: list[FoodItem]
    disclaimer: str = "AI estimates only. Please review and adjust portions."


class WaterIn(BaseModel):
    log_date: str
    amount_ml: int = Field(ge=1, le=5000)


class WeightIn(BaseModel):
    log_date: str
    weight_kg: float = Field(ge=25, le=400)


class ChatIn(BaseModel):
    session_id: Optional[str] = None
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _check_pw(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def _make_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "iat": datetime.now(tz=timezone.utc),
        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


# get_current_user is imported from deps.py (line 46) — do not redefine here.


def _calc_targets(u: dict) -> Optional[Targets]:
    """Mifflin-St Jeor + activity multiplier + goal adjustment."""
    required = ("age", "gender", "height_cm", "weight_kg", "activity", "goal")
    if not all(u.get(k) is not None for k in required):
        return None
    age = u["age"]
    gender = u["gender"]
    h = u["height_cm"]
    w = u["weight_kg"]
    if gender == "male":
        bmr = 10 * w + 6.25 * h - 5 * age + 5
    elif gender == "female":
        bmr = 10 * w + 6.25 * h - 5 * age - 161
    else:
        bmr = 10 * w + 6.25 * h - 5 * age - 78  # avg
    tdee = bmr * ACTIVITY_MULT.get(u["activity"], 1.2)
    if u["goal"] == "lose":
        cal = tdee - 500
    elif u["goal"] == "gain":
        cal = tdee + 400
    else:
        cal = tdee
    cal = max(1200, cal)
    protein = round(1.8 * w)
    fat = round((cal * 0.25) / 9)
    carbs = round((cal - protein * 4 - fat * 9) / 4)
    water = round(w * 35)
    return Targets(
        bmr=round(bmr),
        tdee=round(tdee),
        calories=round(cal),
        protein_g=protein,
        carbs_g=max(50, carbs),
        fat_g=fat,
        water_ml=water,
    )


async def _user_out(u: dict) -> UserOut:
    u = {**u}
    u.pop("password_hash", None)
    # Plan is *derived* from verified subscriptions — never trust the cached field.
    plan = await effective_plan(db, u["id"])
    u["plan"] = plan
    u["premium"] = plan in ("premium", "plus")
    u["targets"] = _calc_targets(u)
    return UserOut(**u)


def _today() -> str:
    return date.today().isoformat()


def _sum_items(items: list[FoodItem]) -> dict:
    return {
        "total_calories": round(sum(i.calories for i in items), 1),
        "total_protein_g": round(sum(i.protein_g for i in items), 1),
        "total_carbs_g": round(sum(i.carbs_g for i in items), 1),
        "total_fat_g": round(sum(i.fat_g for i in items), 1),
    }


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@api.get("/")
async def root():
    return {"app": "C1", "status": "ok"}


@api.post("/auth/register", response_model=AuthOut)
async def register(inp: RegisterIn):
    existing = await db.users.find_one({"email": inp.email.lower()})
    if existing:
        raise HTTPException(400, "Email already registered")
    uid = str(uuid.uuid4())
    doc = {
        "id": uid,
        "email": inp.email.lower(),
        "name": inp.name,
        "password_hash": _hash_pw(inp.password),
        "language": "en",
        "theme": "system",
        "onboarded": False,
        "plan": "free",
        "premium": False,
        "plan_recomputed_at": datetime.now(tz=timezone.utc),
        "is_email_verified": False,
        "streak": 0,
        "best_streak": 0,
        "created_at": datetime.now(tz=timezone.utc),
    }
    await db.users.insert_one(doc)
    return AuthOut(
        token=_make_token(uid),
        user_id=uid,
        email=inp.email,
        name=inp.name,
        onboarded=False,
        premium=False,
    )


@api.post("/auth/login", response_model=AuthOut)
async def login(inp: LoginIn):
    u = await db.users.find_one({"email": inp.email.lower()})
    if not u or not _check_pw(inp.password, u["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    return AuthOut(
        token=_make_token(u["id"]),
        user_id=u["id"],
        email=u["email"],
        name=u["name"],
        onboarded=u.get("onboarded", False),
        premium=u.get("premium", False),
    )


@api.get("/auth/me", response_model=UserOut)
async def me(user=Depends(get_current_user)):
    return await _user_out(user)


@api.patch("/auth/profile", response_model=UserOut)
async def update_profile(inp: ProfileIn, user=Depends(get_current_user)):
    update = {k: v for k, v in inp.model_dump(exclude_none=True).items()}
    if update:
        # mark onboarded once required fields exist
        merged = {**user, **update}
        if all(
            merged.get(k) is not None
            for k in ("age", "gender", "height_cm", "weight_kg", "activity", "goal")
        ):
            update["onboarded"] = True
        await db.users.update_one({"id": user["id"]}, {"$set": update})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return await _user_out(fresh)


@api.post("/auth/premium-toggle")
async def premium_toggle_removed():
    """[REMOVED in Phase 1] Mock plan toggle no longer available.

    Use the IAP flow: /api/iap/apple/verify or /api/iap/google/verify.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={"error": "endpoint_removed", "migrated_to": "/api/iap/*/verify"},
    )


class PlanIn(BaseModel):
    plan: Plan


@api.post("/auth/plan")
async def set_plan_removed(_: PlanIn):
    """[REMOVED in Phase 1] Mock plan setter no longer available.

    Use the IAP flow: /api/iap/apple/verify or /api/iap/google/verify.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={"error": "endpoint_removed", "migrated_to": "/api/iap/*/verify"},
    )


# ---------------------------------------------------------------------------
# Scan quota (per-plan, 24h rolling window, server-enforced)
#
# Two independent buckets — BASE and REWARDED — plus an optional fair-use cap.
#   scan_logs.kind ∈ {"base", "rewarded"}
#   rewarded_credits — one doc per SSV-verified reward, consumed on the next scan
#                       after the base bucket is exhausted.
# ---------------------------------------------------------------------------
async def _scan_counts_last_24h(user_id: str) -> dict:
    since = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    base = await db.scan_logs.count_documents(
        {"user_id": user_id, "created_at": {"$gte": since}, "kind": {"$ne": "rewarded"}}
    )
    rewarded = await db.scan_logs.count_documents(
        {"user_id": user_id, "created_at": {"$gte": since}, "kind": "rewarded"}
    )
    return {"base": base, "rewarded": rewarded, "total": base + rewarded}


async def _rewarded_credits_available(user_id: str) -> int:
    """Unconsumed rewarded-ad credits (24h window)."""
    since = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    return await db.rewarded_credits.count_documents(
        {"user_id": user_id, "consumed_at": None, "granted_at": {"$gte": since}}
    )


async def _scan_quota_state(user: dict) -> dict:
    # Derived from verified subscriptions (source of truth), not from the cached user.plan field.
    plan = await effective_plan(db, user["id"])
    limits = plan_limits(plan)
    base_limit = int(limits["base"] or 0)
    rewarded_limit = int(limits["rewarded"] or 0)
    total_cap = limits["total_cap"]  # None or int

    counts = await _scan_counts_last_24h(user["id"])
    base_used = counts["base"]
    rewarded_used = counts["rewarded"]
    total_used = counts["total"]

    base_remaining = max(0, base_limit - base_used)
    rewarded_remaining = max(0, rewarded_limit - rewarded_used)
    credits_available = await _rewarded_credits_available(user["id"])

    # Plus users: only the total_cap matters, no rewarded flow.
    if plan == "plus":
        can_watch_ad = False
        blocked = (total_cap is not None) and (total_used >= total_cap)
        fair_use = total_cap or base_limit
        total_remaining = max(0, (total_cap or base_limit) - total_used)
    else:
        # Free / Premium — base first, then rewarded via ads.
        can_watch_ad = base_remaining == 0 and rewarded_remaining > 0
        blocked = (
            base_remaining == 0
            and credits_available == 0
            and rewarded_remaining == 0
        )
        fair_use = base_limit + rewarded_limit
        total_remaining = base_remaining + rewarded_remaining

    # Reset time — 24h from oldest scan in window (whichever kind).
    reset_at = None
    if total_used > 0:
        oldest = await db.scan_logs.find_one(
            {
                "user_id": user["id"],
                "created_at": {"$gte": datetime.now(tz=timezone.utc) - timedelta(hours=24)},
            },
            sort=[("created_at", 1)],
        )
        if oldest:
            reset_at = (oldest["created_at"] + timedelta(hours=24)).isoformat()

    return {
        "plan": plan,
        # New (Turn A) — canonical fields
        "base_limit": base_limit,
        "base_used": base_used,
        "base_remaining": base_remaining,
        "rewarded_limit": rewarded_limit,
        "rewarded_used": rewarded_used,
        "rewarded_remaining": rewarded_remaining,
        "rewarded_credits_available": credits_available,
        "total_used": total_used,
        "total_remaining": total_remaining,
        "can_watch_ad": can_watch_ad,
        "fair_use_limit": fair_use,
        "blocked": blocked,
        "reset_at": reset_at,
        # Legacy fields (kept for older client builds)
        "limit": (total_cap if plan == "plus" else base_limit),
        "used": total_used,
        "remaining": (max(0, (total_cap or 0) - total_used) if plan == "plus" else base_remaining),
    }


@api.get("/scan-quota")
async def scan_quota(user=Depends(get_current_user)):
    return await _scan_quota_state(user)


# ---------------------------------------------------------------------------
# AdMob Rewarded-Ad SSV (Server-Side Verification)
#
# Flow:
#   1. Client (JWT-auth'd) calls  POST /api/ai/rewarded/token         → { token }
#   2. Client sets `customData` on the RewardedAd to that token, shows the ad
#   3. AdMob calls  GET/POST /api/ai/rewarded/redeem?ad_network=…&custom_data=<token>&
#         signature=…&key_id=…&transaction_id=…&user_id=…&…       (SSV)
#      → we verify the token, dedupe on transaction_id, insert one rewarded_credit
#   4. Client re-calls /api/ai/scan-meal — server consumes 1 credit if base is exhausted
#
# Signature verification against Google's ECDSA public keys is *stubbed* in Turn A
# behind ADMOB_SSV_ENFORCE (default false in dev). Full ECDSA verification will be
# activated in Turn B once ad flow is wired end-to-end on a real device.
# ---------------------------------------------------------------------------
# Two independent kill-switches control production safety:
#   ADMOB_SSV_ENFORCE       — when true, requires a valid ECDSA signature from
#                             Google's verifier keys. Full ECDSA activation is
#                             deferred until AdMob console verification is
#                             completed; when true today, this endpoint refuses
#                             ALL requests (fail-closed).
#   ADMOB_ALLOW_DEV_REWARD  — when true, accepts a dev-only synthetic signature
#                             so the reward flow can be exercised in Expo Go /
#                             web preview. **DEFAULT FALSE.** Set to true ONLY
#                             in dev/staging; leave unset in production. The
#                             frontend never sends a real reward until AdMob
#                             SSV is live — so the redeem endpoint is only
#                             reachable in prod when ADMOB_SSV_ENFORCE=true.
#
# Reward integrity guarantees regardless of the flags:
#   • Idempotency: unique index on rewarded_credits.transaction_id
#   • Per-plan cap check inside the endpoint (defense-in-depth)
#   • JWT-signed custom_data pinned to a real user_id (short-lived)
ADMOB_SSV_ENFORCE = os.environ.get("ADMOB_SSV_ENFORCE", "false").lower() == "true"
ADMOB_ALLOW_DEV_REWARD = (
    os.environ.get("ADMOB_ALLOW_DEV_REWARD", "false").lower() == "true"
)
REWARD_TOKEN_TTL_MIN = int(os.environ.get("REWARD_TOKEN_TTL_MIN", "20"))
REWARD_TOKEN_TYP = "c1_rw"


class RewardTokenOut(BaseModel):
    token: str
    expires_in: int


@api.post("/ai/rewarded/token", response_model=RewardTokenOut)
async def rewarded_token(user=Depends(get_current_user)):
    """Issue a short-lived signed token for the client to pass as AdMob customData."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "typ": REWARD_TOKEN_TYP,
        "sub": user["id"],
        "iat": now,
        "exp": now + timedelta(minutes=REWARD_TOKEN_TTL_MIN),
        "jti": uuid.uuid4().hex,
    }
    tok = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
    return RewardTokenOut(token=tok, expires_in=REWARD_TOKEN_TTL_MIN * 60)


def _verify_admob_signature(query_string: str, signature: str, key_id: str) -> bool:
    """Synchronous wrapper — see _verify_admob_signature_async for the real work.

    Kept as a small helper so callers that need a sync result (unit tests,
    kill-switch checks) don't have to spin an event loop. Callers inside the
    async request handler should use `_verify_admob_signature_async` directly
    so signature verification runs on the same loop.
    """
    if ADMOB_SSV_ENFORCE:
        # Real production path — dev bypass MUST NOT be honored here.
        # The signature *must* verify against Google's public keys.
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # Called from within an async context — return a coroutine-safe
            # fallback: the async endpoint should call the async variant.
            logger.error(
                "_verify_admob_signature called synchronously from a running "
                "event loop; use _verify_admob_signature_async instead."
            )
            return False
        return asyncio.run(_verify_admob_signature_async(query_string, signature, key_id))

    # ADMOB_SSV_ENFORCE = False → we're in dev/staging.
    if ADMOB_ALLOW_DEV_REWARD:
        return True

    # Safe default: no verification possible AND dev bypass disabled → refuse.
    logger.warning(
        "Rewarded redeem refused: ADMOB_SSV_ENFORCE=false AND "
        "ADMOB_ALLOW_DEV_REWARD=false. Set one of them to true."
    )
    return False


async def _verify_admob_signature_async(
    query_string: str, signature: str, key_id: str
) -> bool:
    """Async ECDSA verifier — used by /api/ai/rewarded/redeem in production.

    Production (ADMOB_SSV_ENFORCE=true):
        Verify the signature against Google's published EC public keys.
        Fail-closed on any error (bad key, invalid signature, network failure
        with no cached keys, etc.).

    Dev/staging (ADMOB_SSV_ENFORCE=false + ADMOB_ALLOW_DEV_REWARD=true):
        Accept synthetic dev signature so the flow is testable in Expo Go.

    Locked (both flags false):
        Refuse. Safe default so a mis-configured deployment cannot grant
        unverified rewards.
    """
    if ADMOB_SSV_ENFORCE:
        from iap.admob_ssv import verify_ssv_request

        ok, reason = await verify_ssv_request(query_string, signature, key_id)
        if not ok:
            logger.warning(
                "AdMob SSV rejected (key_id=%s): %s", key_id, reason
            )
        return ok

    if ADMOB_ALLOW_DEV_REWARD:
        return True

    logger.warning(
        "Rewarded redeem refused: ADMOB_SSV_ENFORCE=false AND "
        "ADMOB_ALLOW_DEV_REWARD=false. Set one of them to true."
    )
    return False


@api.api_route("/ai/rewarded/redeem", methods=["GET", "POST"])
async def rewarded_redeem(request: Request):
    """AdMob SSV callback. Grants exactly one rewarded scan credit per transaction_id."""
    # AdMob may send either GET (default) or POST. Read both query params + body form.
    params = dict(request.query_params)
    if not params:
        try:
            form = await request.form()
            params = dict(form)
        except Exception:
            params = {}

    transaction_id: str = params.get("transaction_id") or ""
    custom_data: str = params.get("custom_data") or ""
    signature: str = params.get("signature") or ""
    key_id: str = params.get("key_id") or ""
    ad_network: str = params.get("ad_network") or ""
    ad_unit: str = params.get("ad_unit") or ""
    reward_amount: str = params.get("reward_amount") or ""
    reward_item: str = params.get("reward_item") or ""

    if not transaction_id or not custom_data:
        # AdMob expects a 2xx even for bad requests to avoid infinite retries,
        # but a 4xx is the correct signal per docs when params are malformed.
        raise HTTPException(400, "missing_ssv_params")

    # 1. Decode + validate the custom_data (our short-lived JWT).
    try:
        claims = jwt.decode(custom_data, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(400, "invalid_custom_data")
    if claims.get("typ") != REWARD_TOKEN_TYP:
        raise HTTPException(400, "invalid_token_type")
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(400, "invalid_token_subject")

    # 2. Verify AdMob signature. Production requires a valid Google ECDSA signature;
    #    dev builds may opt-in to a synthetic bypass via ADMOB_ALLOW_DEV_REWARD.
    raw_qs = str(request.url.query or "")
    if not await _verify_admob_signature_async(raw_qs, signature, key_id):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "reward_verification_disabled",
                "message": (
                    "Reward verification failed or is not enabled. In production, "
                    "the request must carry a valid AdMob signature; in dev, set "
                    "ADMOB_ALLOW_DEV_REWARD=true only for local testing."
                ),
            },
        )

    # 3. Confirm the user still exists.
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(400, "user_not_found")

    # 4. Enforce per-plan rewarded cap BEFORE granting credit (defense-in-depth).
    plan = await effective_plan(db, user_id)
    limits = plan_limits(plan)
    rewarded_cap = int(limits.get("rewarded") or 0)
    if rewarded_cap <= 0:
        raise HTTPException(400, "plan_disallows_rewarded")

    since = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    granted_in_window = await db.rewarded_credits.count_documents(
        {"user_id": user_id, "granted_at": {"$gte": since}}
    )
    if granted_in_window >= rewarded_cap:
        raise HTTPException(429, "rewarded_cap_reached")

    # 5. Insert credit — idempotent on (user_id, transaction_id).
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "transaction_id": transaction_id,
        "ad_network": ad_network,
        "ad_unit": ad_unit,
        "reward_amount": reward_amount,
        "reward_item": reward_item,
        "key_id": key_id,
        "signature": signature,
        "granted_at": datetime.now(tz=timezone.utc),
        "consumed_at": None,
        "raw_query": raw_qs[:1024],
    }
    try:
        await db.rewarded_credits.insert_one(doc)
    except Exception as e:
        # Duplicate key on transaction_id → idempotent success.
        if "duplicate key" in str(e).lower():
            return {"ok": True, "duplicate": True}
        logger.exception("rewarded_credits insert failed")
        raise HTTPException(500, "credit_persistence_failed")

    return {"ok": True, "credit_id": doc["id"]}


@api.delete("/auth/account")
async def delete_account(user=Depends(get_current_user)):
    uid = user["id"]
    await db.users.delete_one({"id": uid})
    await db.meals.delete_many({"user_id": uid})
    await db.water_logs.delete_many({"user_id": uid})
    await db.weight_logs.delete_many({"user_id": uid})
    await db.chat_messages.delete_many({"user_id": uid})
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Password reset (forgot password)
# ---------------------------------------------------------------------------
class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    email: EmailStr
    code: str
    new_password: str = Field(min_length=6)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _generic_forgot_ok():
    # Same response whether the email exists or not (avoid user enumeration).
    return {"ok": True, "message": "If that email is registered, a reset code has been sent."}


async def _send_reset_email(email: str, code: str) -> None:
    if not EMERGENT_EMAIL_KEY:
        logger.error("EMERGENT_EMAIL_KEY not configured; cannot send reset email")
        return
    html = f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0A0A0C;padding:32px 0;font-family:Arial,Helvetica,sans-serif;">
  <tr><td align="center">
    <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="background:#141417;border-radius:20px;padding:32px;">
      <tr><td align="center">
        <div style="display:inline-block;width:64px;height:64px;border-radius:18px;background:#D4AF37;line-height:64px;color:#0A0A0C;font-size:28px;font-weight:900;letter-spacing:-1px;">C1</div>
      </td></tr>
      <tr><td style="padding-top:24px;text-align:center;">
        <h1 style="color:#F4F4F5;font-size:22px;margin:0 0 8px 0;font-weight:800;">Reset your password</h1>
        <p style="color:#A1A1AA;font-size:14px;line-height:20px;margin:0 0 24px 0;">
          Use the code below to reset your C1 password. This code expires in 15 minutes.
        </p>
        <div style="display:inline-block;background:#332A0D;border:1px solid #D4AF37;border-radius:12px;padding:14px 28px;">
          <span style="color:#D4AF37;font-size:32px;font-weight:900;letter-spacing:8px;">{code}</span>
        </div>
        <p style="color:#71717A;font-size:12px;line-height:18px;margin:24px 0 0 0;">
          If you didn't request this, you can safely ignore this email.<br/>
          Your password won't change until you enter this code in the app.
        </p>
      </td></tr>
    </table>
    <p style="color:#52525B;font-size:11px;margin-top:16px;">C1 — Your AI nutrition coach</p>
  </td></tr>
</table>
"""
    payload = {
        "to": [email],
        "subject": "Your C1 password reset code",
        "html": html,
        "from_name": EMAIL_FROM_NAME,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": EMERGENT_EMAIL_KEY},
                json=payload,
            )
        if resp.status_code >= 300:
            logger.error("password reset email failed: %s %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error("password reset email exception: %s", e)


@api.post("/auth/forgot-password")
async def forgot_password(inp: ForgotIn):
    email = inp.email.lower()
    user = await db.users.find_one({"email": email})
    if user:
        # 6-digit numeric code
        code = f"{secrets.randbelow(1_000_000):06d}"
        doc = {
            "email": email,
            "code_hash": _hash_code(code),
            "attempts": 0,
            "created_at": datetime.now(tz=timezone.utc),
            "expires_at": datetime.now(tz=timezone.utc) + timedelta(minutes=15),
            "used": False,
        }
        # Invalidate any prior codes for this email, then insert a fresh one.
        await db.password_resets.update_many(
            {"email": email, "used": False},
            {"$set": {"used": True, "invalidated_at": datetime.now(tz=timezone.utc)}},
        )
        await db.password_resets.insert_one(doc)
        # Send email but don't block on delivery failure.
        try:
            await _send_reset_email(email, code)
        except Exception as e:
            logger.warning("send_reset_email failed: %s", e)
    # Same response either way to prevent user enumeration.
    return _generic_forgot_ok()


@api.post("/auth/reset-password")
async def reset_password(inp: ResetIn):
    email = inp.email.lower()
    # Look up latest unused, unexpired code for this email.
    rec = await db.password_resets.find_one(
        {"email": email, "used": False, "expires_at": {"$gt": datetime.now(tz=timezone.utc)}},
        sort=[("created_at", -1)],
    )
    if not rec:
        raise HTTPException(400, "Invalid or expired code")
    # Cap attempts per code to prevent brute force (6-digit = 1M space).
    if rec.get("attempts", 0) >= 5:
        await db.password_resets.update_one({"_id": rec["_id"]}, {"$set": {"used": True}})
        raise HTTPException(429, "Too many attempts. Request a new code.")
    if not hmac.compare_digest(rec["code_hash"], _hash_code(inp.code.strip())):
        await db.password_resets.update_one({"_id": rec["_id"]}, {"$inc": {"attempts": 1}})
        raise HTTPException(400, "Invalid or expired code")
    # Verify the user still exists.
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(400, "Invalid or expired code")
    # Update password + invalidate this reset record.
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": _hash_pw(inp.new_password)}},
    )
    await db.password_resets.update_one(
        {"_id": rec["_id"]},
        {"$set": {"used": True, "used_at": datetime.now(tz=timezone.utc)}},
    )
    return {"ok": True}




# ---------------------------------------------------------------------------
# Food diary
# ---------------------------------------------------------------------------
@api.post("/meals", response_model=MealOut)
async def add_meal(inp: MealIn, user=Depends(get_current_user)):
    mid = str(uuid.uuid4())
    totals = _sum_items(inp.items)
    doc = {
        "id": mid,
        "user_id": user["id"],
        **inp.model_dump(),
        **totals,
        "created_at": datetime.now(tz=timezone.utc),
    }
    await db.meals.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("user_id", None)
    return MealOut(**doc)


@api.get("/meals", response_model=list[MealOut])
async def list_meals(
    log_date: Optional[str] = None,
    user=Depends(get_current_user),
):
    q = {"user_id": user["id"]}
    if log_date:
        q["log_date"] = log_date
    docs = await db.meals.find(q, {"_id": 0, "user_id": 0}).sort("created_at", 1).to_list(500)
    return [MealOut(**d) for d in docs]


@api.delete("/meals/{meal_id}")
async def delete_meal(meal_id: str, user=Depends(get_current_user)):
    r = await db.meals.delete_one({"id": meal_id, "user_id": user["id"]})
    if r.deleted_count == 0:
        raise HTTPException(404, "Meal not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Water & Weight
# ---------------------------------------------------------------------------
@api.post("/water")
async def add_water(inp: WaterIn, user=Depends(get_current_user)):
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "log_date": inp.log_date,
        "amount_ml": inp.amount_ml,
        "created_at": datetime.now(tz=timezone.utc),
    }
    await db.water_logs.insert_one(doc)
    total = await _water_total(user["id"], inp.log_date)
    return {"total_ml": total}


async def _water_total(user_id: str, log_date: str) -> int:
    pipeline = [
        {"$match": {"user_id": user_id, "log_date": log_date}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_ml"}}},
    ]
    res = await db.water_logs.aggregate(pipeline).to_list(1)
    return int(res[0]["total"]) if res else 0


@api.get("/water")
async def get_water(log_date: str, user=Depends(get_current_user)):
    return {"total_ml": await _water_total(user["id"], log_date)}


@api.post("/weight")
async def add_weight(inp: WeightIn, user=Depends(get_current_user)):
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "log_date": inp.log_date,
        "weight_kg": inp.weight_kg,
        "created_at": datetime.now(tz=timezone.utc),
    }
    await db.weight_logs.insert_one(doc)
    # keep user profile weight in sync
    await db.users.update_one({"id": user["id"]}, {"$set": {"weight_kg": inp.weight_kg}})
    return {"ok": True}


@api.get("/weight")
async def list_weight(user=Depends(get_current_user)):
    docs = await db.weight_logs.find(
        {"user_id": user["id"]}, {"_id": 0, "user_id": 0}
    ).sort("log_date", 1).to_list(365)
    return docs


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------
@api.get("/dashboard")
async def dashboard(log_date: Optional[str] = None, user=Depends(get_current_user)):
    d = log_date or _today()
    meals = await db.meals.find(
        {"user_id": user["id"], "log_date": d}, {"_id": 0, "user_id": 0}
    ).to_list(200)
    totals = {
        "calories": round(sum(m.get("total_calories", 0) for m in meals), 1),
        "protein_g": round(sum(m.get("total_protein_g", 0) for m in meals), 1),
        "carbs_g": round(sum(m.get("total_carbs_g", 0) for m in meals), 1),
        "fat_g": round(sum(m.get("total_fat_g", 0) for m in meals), 1),
    }
    water_ml = await _water_total(user["id"], d)
    targets = _calc_targets(user)
    return {
        "date": d,
        "totals": totals,
        "water_ml": water_ml,
        "meals_count": len(meals),
        "targets": targets.model_dump() if targets else None,
        "streak": user.get("streak", 0),
        "best_streak": user.get("best_streak", 0),
    }


# ---------------------------------------------------------------------------
# AI: Meal photo scan
# ---------------------------------------------------------------------------
SCAN_SYSTEM = (
    "You are a nutrition vision assistant. Analyze the food image and reply ONLY with "
    "valid minified JSON matching this schema: "
    '{"items":[{"name":str,"portion_g":number,"calories":number,"protein_g":number,'
    '"carbs_g":number,"fat_g":number,"fiber_g":number,"sugar_g":number}]}. '
    "Estimate portion size in grams from visual cues. Provide realistic per-100g nutrition scaled to the portion. "
    "If nothing edible is detected, return {\"items\":[]}. Do not add markdown or commentary."
)


def _strip_data_uri(b64: str) -> str:
    m = re.match(r"^data:image/\w+;base64,(.+)$", b64.strip())
    return m.group(1) if m else b64.strip()


def _parse_scan_json(text: str) -> list[FoodItem]:
    # try to extract JSON block
    text = text.strip()
    # remove markdown fences
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        obj = json.loads(text)
    except Exception:
        # try to find first { ... } block
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return []
        try:
            obj = json.loads(m.group(0))
        except Exception:
            return []
    items = []
    for raw in obj.get("items", []) or []:
        try:
            items.append(
                FoodItem(
                    name=str(raw.get("name", "Unknown")),
                    portion_g=float(raw.get("portion_g") or 100),
                    calories=float(raw.get("calories") or 0),
                    protein_g=float(raw.get("protein_g") or 0),
                    carbs_g=float(raw.get("carbs_g") or 0),
                    fat_g=float(raw.get("fat_g") or 0),
                    fiber_g=float(raw.get("fiber_g") or 0),
                    sugar_g=float(raw.get("sugar_g") or 0),
                )
            )
        except Exception:
            continue
    return items


@api.post("/ai/scan-meal", response_model=ScanOut)
async def scan_meal(inp: ScanIn, user=Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    # Enforce per-plan scan limit (24h rolling window) — base first, then rewarded credit.
    quota = await _scan_quota_state(user)
    if quota["blocked"]:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "scan_limit_reached",
                "plan": quota["plan"],
                "base_limit": quota["base_limit"],
                "base_used": quota["base_used"],
                "rewarded_limit": quota["rewarded_limit"],
                "rewarded_used": quota["rewarded_used"],
                "can_watch_ad": quota["can_watch_ad"],
                "fair_use_limit": quota["fair_use_limit"],
                "reset_at": quota["reset_at"],
                "message": (
                    f"You've hit today's scan cap ({quota['fair_use_limit']} scans/24h) "
                    f"on the {quota['plan']} plan."
                ),
            },
        )

    # Determine which bucket this scan will draw from.
    # Plus: always "base" (single bucket). Free/Premium: base while available, else rewarded credit.
    scan_kind: str = "base"
    consumed_credit_id: Optional[str] = None
    if quota["plan"] != "plus" and quota["base_remaining"] == 0:
        # Must consume a rewarded credit. Base is exhausted.
        if quota["rewarded_credits_available"] == 0:
            # Client should have shown an ad and waited for SSV. Ask them to watch (or upgrade).
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "base_limit_reached",
                    "plan": quota["plan"],
                    "base_limit": quota["base_limit"],
                    "base_used": quota["base_used"],
                    "rewarded_limit": quota["rewarded_limit"],
                    "rewarded_used": quota["rewarded_used"],
                    "rewarded_remaining": quota["rewarded_remaining"],
                    "can_watch_ad": quota["can_watch_ad"],
                    "reset_at": quota["reset_at"],
                    "message": (
                        "You've used your free daily scans. Watch a short ad to earn another scan, "
                        "or upgrade to Premium/Plus."
                    ),
                },
            )
        # Atomically claim the oldest unconsumed credit.
        since = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        credit = await db.rewarded_credits.find_one_and_update(
            {
                "user_id": user["id"],
                "consumed_at": None,
                "granted_at": {"$gte": since},
            },
            {"$set": {"consumed_at": datetime.now(tz=timezone.utc)}},
            sort=[("granted_at", 1)],
        )
        if not credit:
            # Lost a race — someone else consumed it. Treat as limit reached.
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "base_limit_reached",
                    "plan": quota["plan"],
                    "message": "No rewarded scan credits available. Watch an ad first.",
                },
            )
        consumed_credit_id = credit.get("id")
        scan_kind = "rewarded"

    raw_b64 = _strip_data_uri(inp.image_b64)
    # sanity check
    try:
        base64.b64decode(raw_b64[:200], validate=False)
    except Exception:
        # Refund the rewarded credit if we consumed one — the scan never happened.
        if consumed_credit_id:
            await db.rewarded_credits.update_one(
                {"id": consumed_credit_id}, {"$set": {"consumed_at": None, "refund_reason": "invalid_image"}}
            )
        raise HTTPException(400, "Invalid image data")

    async def _run_once() -> str:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"scan-{user['id']}-{uuid.uuid4().hex[:8]}",
            system_message=SCAN_SYSTEM,
        ).with_model(*AI_VISION_MODEL)
        image_content = ImageContent(image_base64=raw_b64)
        user_msg = UserMessage(
            text="Identify the foods in this photo and return the JSON as specified.",
            file_contents=[image_content],
        )
        buf = ""
        async for ev in chat.stream_message(user_msg):
            if isinstance(ev, TextDelta):
                buf += ev.content
            elif isinstance(ev, StreamDone):
                break
        return buf

    last_exc: Exception | None = None
    collected = ""
    for attempt in range(2):  # 1 retry on transient failure
        try:
            collected = await asyncio.wait_for(_run_once(), timeout=75)
            break
        except asyncio.TimeoutError as e:
            last_exc = e
            logger.warning("scan attempt %d timeout", attempt + 1)
        except Exception as e:
            last_exc = e
            logger.warning("scan attempt %d failed: %s", attempt + 1, e)
        if attempt == 0:
            await asyncio.sleep(1.0)
    else:
        # Refund the rewarded credit on total AI failure (fair to the user).
        if consumed_credit_id:
            await db.rewarded_credits.update_one(
                {"id": consumed_credit_id}, {"$set": {"consumed_at": None, "refund_reason": "ai_failed"}}
            )
        logger.exception("scan failed after retries")
        raise HTTPException(502, f"AI vision failed: {last_exc}")

    items = _parse_scan_json(collected)
    # Only count a scan when we successfully processed it (i.e. reached this line).
    await db.scan_logs.insert_one(
        {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "created_at": datetime.now(tz=timezone.utc),
            "items_count": len(items),
            "kind": scan_kind,
            "credit_id": consumed_credit_id,
        }
    )
    return ScanOut(items=items)


# ---------------------------------------------------------------------------
# AI Coach chat (SSE streaming)
# ---------------------------------------------------------------------------
COACH_SYSTEM = (
    "You are C1 Coach, a warm, supportive AI nutrition and fitness coach. "
    "Provide practical, non-judgmental advice on nutrition, calories, macros, hydration, meal planning, "
    "and healthy habits. Keep answers concise, actionable, and encouraging. "
    "Always remind users that C1 provides general information and is not a replacement for professional medical advice."
)


def _profile_context(user: dict) -> str:
    parts = [f"User name: {user.get('name')}"]
    for k in ("age", "gender", "height_cm", "weight_kg", "target_weight_kg", "activity", "goal"):
        if user.get(k) is not None:
            parts.append(f"{k}: {user[k]}")
    t = _calc_targets(user)
    if t:
        parts.append(
            f"Daily targets: {t.calories} kcal, P {t.protein_g}g / C {t.carbs_g}g / F {t.fat_g}g, water {t.water_ml} ml"
        )
    return " | ".join(parts)


@api.get("/ai/chat/history")
async def chat_history(session_id: str, user=Depends(get_current_user)):
    docs = await db.chat_messages.find(
        {"user_id": user["id"], "session_id": session_id},
        {"_id": 0, "user_id": 0},
    ).sort("created_at", 1).to_list(500)
    return docs


@api.post("/ai/chat")
async def chat_send(inp: ChatIn, user=Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    session_id = inp.session_id or f"coach-{user['id']}"
    now = datetime.now(tz=timezone.utc)
    await db.chat_messages.insert_one(
        {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "session_id": session_id,
            "role": "user",
            "content": inp.message,
            "created_at": now,
        }
    )
    system = COACH_SYSTEM + "\n\nUser profile: " + _profile_context(user)
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system,
    ).with_model(*AI_TEXT_MODEL)

    # Pull recent history and prepend to give context (excluding the msg we just saved to avoid dupe)
    history = await db.chat_messages.find(
        {"user_id": user["id"], "session_id": session_id},
        {"_id": 0},
    ).sort("created_at", 1).to_list(20)
    convo = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-10:])

    async def gen():
        full = ""
        try:
            async for ev in chat.stream_message(
                UserMessage(text=f"Recent conversation:\n{convo}\n\nRespond to the latest USER message.")
            ):
                if isinstance(ev, TextDelta):
                    full += ev.content
                    yield f"data: {json.dumps({'delta': ev.content})}\n\n"
                elif isinstance(ev, StreamDone):
                    break
        except Exception as e:
            logger.exception("chat error")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        # persist assistant reply
        await db.chat_messages.insert_one(
            {
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "session_id": session_id,
                "role": "assistant",
                "content": full,
                "created_at": datetime.now(tz=timezone.utc),
            }
        )
        yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api.post("/ai/chat-sync")
async def chat_sync(inp: ChatIn, user=Depends(get_current_user)):
    """Non-streaming fallback (easier to consume from RN without SSE)."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    session_id = inp.session_id or f"coach-{user['id']}"
    await db.chat_messages.insert_one(
        {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "session_id": session_id,
            "role": "user",
            "content": inp.message,
            "created_at": datetime.now(tz=timezone.utc),
        }
    )
    system = COACH_SYSTEM + "\n\nUser profile: " + _profile_context(user)
    history = await db.chat_messages.find(
        {"user_id": user["id"], "session_id": session_id},
        {"_id": 0},
    ).sort("created_at", 1).to_list(20)
    convo = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-10:])
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system,
    ).with_model(*AI_TEXT_MODEL)
    full = ""
    try:
        async for ev in chat.stream_message(
            UserMessage(text=f"Recent conversation:\n{convo}\n\nRespond to the latest USER message.")
        ):
            if isinstance(ev, TextDelta):
                full += ev.content
            elif isinstance(ev, StreamDone):
                break
    except Exception as e:
        raise HTTPException(502, f"AI failed: {e}")
    await db.chat_messages.insert_one(
        {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "session_id": session_id,
            "role": "assistant",
            "content": full,
            "created_at": datetime.now(tz=timezone.utc),
        }
    )
    return {"session_id": session_id, "reply": full}


# ---------------------------------------------------------------------------
# AI Meal & Snack Recommendations (Complete My Day)
# ---------------------------------------------------------------------------
class RecommendIngredient(BaseModel):
    name: str
    portion_g: float


class RecommendItem(BaseModel):
    id: str
    kind: Literal["meal", "snack"]
    emoji: str = "🍽️"
    name: str
    description: str = ""
    prep_minutes: int = 15
    tags: list[str] = []
    ingredients: list[RecommendIngredient] = []
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float


class RecommendOut(BaseModel):
    remaining: dict
    items: list[RecommendItem]


class RecommendIn(BaseModel):
    focus: Optional[Literal["high_protein", "low_calorie", "vegetarian", "vegan", "quick", "any"]] = "any"
    only: Optional[Literal["all", "meals", "snacks"]] = "all"
    log_date: Optional[str] = None


class RefineIn(BaseModel):
    session_id: str
    item: RecommendItem
    request: str


REC_SYSTEM = (
    "You are C1 Premium, an expert AI nutrition planner. "
    "Given a user's remaining daily calorie/protein/carbs/fat budget and preferences, propose realistic meal and snack ideas. "
    "Reply ONLY with valid minified JSON matching exactly: "
    '{"items":[{"id":str,"kind":"meal"|"snack","emoji":str,"name":str,"description":str,'
    '"prep_minutes":int,"tags":[str],"ingredients":[{"name":str,"portion_g":number}],'
    '"calories":number,"protein_g":number,"carbs_g":number,"fat_g":number}]}. '
    "Macros must be the SUM across the ingredients and be realistic. "
    "Keep ideas concrete and diverse (different proteins, cuisines). "
    "Snacks should be under 300 kcal; meals typically 300-800 kcal. "
    "Never exceed the remaining budget by more than 15%. "
    "Do NOT wrap the JSON in markdown, comments, or prose."
)

REFINE_SYSTEM = (
    "You are C1 Premium, refining a single recommended meal or snack based on a user's request "
    "(e.g. replace an ingredient, adjust calories, dietary restriction, less prep time). "
    "Reply ONLY with valid minified JSON for a single item using exactly this schema: "
    '{"id":str,"kind":"meal"|"snack","emoji":str,"name":str,"description":str,'
    '"prep_minutes":int,"tags":[str],"ingredients":[{"name":str,"portion_g":number}],'
    '"calories":number,"protein_g":number,"carbs_g":number,"fat_g":number}. '
    "Keep the item's id unchanged. Recompute macros from the updated ingredients. "
    "Respect any dietary restrictions the user mentions. Stay close to the user's remaining budget if provided. "
    "Do NOT wrap the JSON in markdown."
)


def _parse_json_object(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}


def _coerce_rec_item(raw: dict, default_kind: str = "meal") -> Optional[RecommendItem]:
    try:
        ings = []
        for ing in raw.get("ingredients", []) or []:
            ings.append(
                RecommendIngredient(
                    name=str(ing.get("name", "")).strip() or "Ingredient",
                    portion_g=float(ing.get("portion_g") or 0),
                )
            )
        return RecommendItem(
            id=str(raw.get("id") or uuid.uuid4().hex[:8]),
            kind=raw.get("kind") if raw.get("kind") in ("meal", "snack") else default_kind,  # type: ignore
            emoji=str(raw.get("emoji") or "🍽️")[:4],
            name=str(raw.get("name") or "Meal idea")[:80],
            description=str(raw.get("description") or "")[:280],
            prep_minutes=int(raw.get("prep_minutes") or 15),
            tags=[str(t)[:20] for t in (raw.get("tags") or [])][:6],
            ingredients=ings,
            calories=float(raw.get("calories") or 0),
            protein_g=float(raw.get("protein_g") or 0),
            carbs_g=float(raw.get("carbs_g") or 0),
            fat_g=float(raw.get("fat_g") or 0),
        )
    except Exception:
        return None


async def _remaining_budgets(user: dict, log_date: str) -> dict:
    targets = _calc_targets(user)
    if not targets:
        return {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    meals = await db.meals.find(
        {"user_id": user["id"], "log_date": log_date}, {"_id": 0}
    ).to_list(500)
    consumed_cal = sum(m.get("total_calories", 0) for m in meals)
    consumed_p = sum(m.get("total_protein_g", 0) for m in meals)
    consumed_c = sum(m.get("total_carbs_g", 0) for m in meals)
    consumed_f = sum(m.get("total_fat_g", 0) for m in meals)
    return {
        "calories": max(0, round(targets.calories - consumed_cal)),
        "protein_g": max(0, round(targets.protein_g - consumed_p)),
        "carbs_g": max(0, round(targets.carbs_g - consumed_c)),
        "fat_g": max(0, round(targets.fat_g - consumed_f)),
    }


@api.post("/ai/recommend", response_model=RecommendOut)
async def recommend(inp: RecommendIn, user=Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    if await effective_plan(db, user["id"]) != "plus":
        raise HTTPException(
            status_code=402,
            detail={"error": "plus_required", "message": "Meal recommendations are a C1 Plus feature."},
        )
    log_date = inp.log_date or _today()
    remaining = await _remaining_budgets(user, log_date)

    only = inp.only or "all"
    if only == "meals":
        want = "3 meal options"
    elif only == "snacks":
        want = "4 snack options"
    else:
        want = "3 meal options AND 3 snack options"
    focus_hint = {
        "high_protein": "Prioritize high-protein options (>=25g protein per meal).",
        "low_calorie": "Prioritize low-calorie options.",
        "vegetarian": "All items must be vegetarian.",
        "vegan": "All items must be vegan (no animal products).",
        "quick": "Prioritize items that take <=10 minutes to prepare.",
        "any": "",
    }.get(inp.focus or "any", "")

    user_prompt = (
        f"Remaining daily budget for the user today: {remaining['calories']} kcal, "
        f"protein {remaining['protein_g']}g, carbs {remaining['carbs_g']}g, fat {remaining['fat_g']}g. "
        f"User profile: {_profile_context(user)}. "
        f"Produce {want} that together help the user complete their day close to targets. "
        f"{focus_hint} "
        "Return the JSON only."
    )

    session_id = f"rec-{user['id']}-{uuid.uuid4().hex[:6]}"

    async def _run() -> str:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=REC_SYSTEM,
        ).with_model(*AI_TEXT_MODEL)
        buf = ""
        async for ev in chat.stream_message(UserMessage(text=user_prompt)):
            if isinstance(ev, TextDelta):
                buf += ev.content
            elif isinstance(ev, StreamDone):
                break
        return buf

    last_exc: Exception | None = None
    text = ""
    for attempt in range(2):
        try:
            text = await asyncio.wait_for(_run(), timeout=60)
            break
        except Exception as e:
            last_exc = e
            logger.warning("recommend attempt %d failed: %s", attempt + 1, e)
            if attempt == 0:
                await asyncio.sleep(1.0)
    else:
        raise HTTPException(502, f"AI failed: {last_exc}")

    obj = _parse_json_object(text)
    items: list[RecommendItem] = []
    for raw in obj.get("items", []) or []:
        it = _coerce_rec_item(
            raw,
            default_kind="snack" if only == "snacks" else "meal",
        )
        if it:
            items.append(it)

    if only == "meals":
        items = [i for i in items if i.kind == "meal"]
    elif only == "snacks":
        items = [i for i in items if i.kind == "snack"]

    return RecommendOut(remaining=remaining, items=items)


@api.post("/ai/recommend/refine", response_model=RecommendItem)
async def recommend_refine(inp: RefineIn, user=Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    if await effective_plan(db, user["id"]) != "plus":
        raise HTTPException(
            status_code=402,
            detail={"error": "plus_required", "message": "Meal recommendations are a C1 Plus feature."},
        )
    remaining = await _remaining_budgets(user, _today())
    user_prompt = (
        f"Current recommendation JSON: {inp.item.model_dump_json()}. "
        f"User's request: \"{inp.request}\". "
        f"User remaining daily budget: {remaining['calories']} kcal, "
        f"P {remaining['protein_g']}g / C {remaining['carbs_g']}g / F {remaining['fat_g']}g. "
        f"User profile: {_profile_context(user)}. "
        "Return the updated single-item JSON only. Keep the same id."
    )

    async def _run() -> str:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=inp.session_id,
            system_message=REFINE_SYSTEM,
        ).with_model(*AI_TEXT_MODEL)
        buf = ""
        async for ev in chat.stream_message(UserMessage(text=user_prompt)):
            if isinstance(ev, TextDelta):
                buf += ev.content
            elif isinstance(ev, StreamDone):
                break
        return buf

    last_exc: Exception | None = None
    text = ""
    for attempt in range(2):
        try:
            text = await asyncio.wait_for(_run(), timeout=60)
            break
        except Exception as e:
            last_exc = e
            logger.warning("refine attempt %d failed: %s", attempt + 1, e)
            if attempt == 0:
                await asyncio.sleep(1.0)
    else:
        raise HTTPException(502, f"AI failed: {last_exc}")

    obj = _parse_json_object(text)
    # Some models may still wrap under 'items' or 'item'; unwrap defensively
    if "items" in obj and isinstance(obj["items"], list) and obj["items"]:
        obj = obj["items"][0]
    if "item" in obj and isinstance(obj["item"], dict):
        obj = obj["item"]
    obj.setdefault("id", inp.item.id)
    updated = _coerce_rec_item(obj, default_kind=inp.item.kind)
    if not updated:
        raise HTTPException(502, "AI returned an invalid recommendation")
    # preserve id
    updated.id = inp.item.id
    return updated





# ---------------------------------------------------------------------------
# Entitlement (derived from verified subscriptions — never client-set)
# ---------------------------------------------------------------------------
@api.get("/entitlement")
async def entitlement(user=Depends(get_current_user)):
    snap = await entitlement_snapshot(db, user["id"])
    return snap.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Startup: ensure subscriptions + iap_events indexes exist
# ---------------------------------------------------------------------------
async def _ensure_iap_indexes():
    # subscriptions
    await db.subscriptions.create_index([("user_id", 1), ("expires_at", -1)])
    await db.subscriptions.create_index(
        [("platform", 1), ("original_transaction_id", 1)],
        unique=True,
        partialFilterExpression={"platform": "apple", "original_transaction_id": {"$type": "string"}},
        name="apple_original_tx_uniq",
    )
    await db.subscriptions.create_index(
        [("platform", 1), ("purchase_token", 1)],
        unique=True,
        partialFilterExpression={"platform": "google", "purchase_token": {"$type": "string"}},
        name="google_purchase_token_uniq",
    )
    await db.subscriptions.create_index(
        [("latest_transaction_id", 1)],
        sparse=True,
        name="latest_tx_sparse",
    )
    await db.subscriptions.create_index([("expires_at", 1), ("status", 1)], name="expiry_sweep")

    # iap_events
    await db.iap_events.create_index(
        [("notification_uuid", 1)], unique=True, sparse=True, name="apple_notif_uuid_uniq"
    )
    await db.iap_events.create_index(
        [("pubsub_message_id", 1)], unique=True, sparse=True, name="google_msg_id_uniq"
    )
    await db.iap_events.create_index([("raw_payload_hash", 1)], name="payload_hash_audit")
    await db.iap_events.create_index(
        [("platform", 1), ("notification_type", 1), ("received_at", -1)],
        name="events_lookup",
    )
    await db.iap_events.create_index(
        [("user_id", 1), ("received_at", -1)], sparse=True, name="events_by_user"
    )

    # rewarded_credits — 1 doc per SSV redemption. Unique per transaction_id (idempotency).
    await db.rewarded_credits.create_index(
        [("transaction_id", 1)],
        unique=True,
        partialFilterExpression={"transaction_id": {"$type": "string"}},
        name="reward_tx_uniq",
    )
    await db.rewarded_credits.create_index(
        [("user_id", 1), ("consumed_at", 1), ("granted_at", 1)],
        name="reward_consume_lookup",
    )
    await db.rewarded_credits.create_index(
        [("user_id", 1), ("granted_at", -1)],
        name="reward_history",
    )


@app.on_event("startup")
async def _startup():
    # Expose db handle to router modules (used by iap/routes.py)
    app.state.db = db
    try:
        await _ensure_iap_indexes()
        logger.info("IAP indexes ensured")
    except Exception as e:
        logger.error("Failed to ensure IAP indexes: %s", e)


# ---------------------------------------------------------------------------
# Wire up
# ---------------------------------------------------------------------------
# IAP router requires JWT auth on every route (Phase 1: routes are 501 stubs).
api.include_router(iap_router, dependencies=[Depends(get_current_user)])
app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def _shutdown():
    client.close()
