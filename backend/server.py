"""C1 backend – nutrition tracker with AI meal recognition and coach.

All routes under /api/*.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Any, Literal, Optional

import bcrypt
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
DB_NAME = os.environ.get("DB_NAME", "c1_database")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret")
JWT_ALG = os.environ.get("JWT_ALG", "HS256")
JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "720"))

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
    premium: bool = False
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
    """Stubbed paywall: flip premium on/off for demo."""
    new_val = not user.get("premium", False)
    await db.users.update_one({"id": user["id"]}, {"$set": {"premium": new_val}})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return _user_out(fresh)


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
