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
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Header, status
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

SCAN_LIMITS: dict[str, Optional[int]] = {
    "free": 4,
    "premium": 20,
    "plus": None,  # unlimited, still fair-use limited below
}
PLUS_FAIR_USE_LIMIT = 60  # scans / 24h hard cap even for plus (abuse guard)

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


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


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


def _user_out(u: dict) -> UserOut:
    u = {**u}
    u.pop("password_hash", None)
    # Normalize plan and legacy premium bool
    plan = u.get("plan")
    if plan not in ("free", "premium", "plus"):
        plan = "premium" if u.get("premium") else "free"
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
    return _user_out(user)


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
    return _user_out(fresh)


@api.post("/auth/premium-toggle", response_model=UserOut)
async def premium_toggle(user=Depends(get_current_user)):
    """Legacy stub: cycles free → premium → plus → free (used by demo toggle)."""
    order = ["free", "premium", "plus"]
    current = user.get("plan")
    if current not in order:
        current = "premium" if user.get("premium") else "free"
    next_plan = order[(order.index(current) + 1) % 3]
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"plan": next_plan, "premium": next_plan in ("premium", "plus")}},
    )
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return _user_out(fresh)


class PlanIn(BaseModel):
    plan: Plan


@api.post("/auth/plan", response_model=UserOut)
async def set_plan(inp: PlanIn, user=Depends(get_current_user)):
    """Stubbed subscription setter — in production this is driven by verified IAP receipts."""
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"plan": inp.plan, "premium": inp.plan in ("premium", "plus")}},
    )
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return _user_out(fresh)


# ---------------------------------------------------------------------------
# Scan quota (per-plan, 24h rolling window, server-enforced)
# ---------------------------------------------------------------------------
async def _scan_count_last_24h(user_id: str) -> int:
    since = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    return await db.scan_logs.count_documents(
        {"user_id": user_id, "created_at": {"$gte": since}}
    )


async def _scan_quota_state(user: dict) -> dict:
    plan = user.get("plan") or ("premium" if user.get("premium") else "free")
    used = await _scan_count_last_24h(user["id"])
    if plan == "plus":
        limit = None
        fair = PLUS_FAIR_USE_LIMIT
        remaining = max(0, fair - used)
        blocked = used >= fair
    else:
        limit = SCAN_LIMITS[plan]
        fair = limit
        remaining = max(0, (limit or 0) - used) if limit is not None else None
        blocked = limit is not None and used >= limit
    # Reset time = when the oldest scan in the window falls out (i.e. +24h from its created_at)
    reset_at = None
    if used > 0:
        oldest = await db.scan_logs.find_one(
            {"user_id": user["id"], "created_at": {"$gte": datetime.now(tz=timezone.utc) - timedelta(hours=24)}},
            sort=[("created_at", 1)],
        )
        if oldest:
            reset_at = (oldest["created_at"] + timedelta(hours=24)).isoformat()
    return {
        "plan": plan,
        "limit": limit,
        "used": used,
        "remaining": remaining,
        "fair_use_limit": fair,
        "blocked": blocked,
        "reset_at": reset_at,
    }


@api.get("/scan-quota")
async def scan_quota(user=Depends(get_current_user)):
    return await _scan_quota_state(user)


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
    # Enforce per-plan scan limit (24h rolling window)
    quota = await _scan_quota_state(user)
    if quota["blocked"]:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "scan_limit_reached",
                "plan": quota["plan"],
                "limit": quota["fair_use_limit"],
                "reset_at": quota["reset_at"],
                "message": (
                    f"You've reached your daily scan limit ({quota['fair_use_limit']} scans / 24h) "
                    f"for the {quota['plan']} plan."
                ),
            },
        )
    raw_b64 = _strip_data_uri(inp.image_b64)
    # sanity check
    try:
        base64.b64decode(raw_b64[:200], validate=False)
    except Exception:
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
    if (user.get("plan") or ("premium" if user.get("premium") else "free")) != "plus":
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
    if (user.get("plan") or ("premium" if user.get("premium") else "free")) != "plus":
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
# Wire up
# ---------------------------------------------------------------------------
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
