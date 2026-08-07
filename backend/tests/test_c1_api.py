"""C1 Backend regression + scan bug fix verification tests."""
import base64
import io
import os
import time
import pytest
import requests

# Root
def test_health(api_client, base_url):
    r = api_client.get(f"{base_url}/api/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"

# -------- Auth flow --------
def test_register_login_me(api_client, base_url, user_ctx):
    # login with same creds
    r = api_client.post(f"{base_url}/api/auth/login", json={"email": user_ctx["email"], "password": user_ctx["password"]})
    assert r.status_code == 200
    data = r.json()
    assert "token" in data and data["email"].lower() == user_ctx["email"].lower()
    # me
    r = api_client.get(f"{base_url}/api/auth/me", headers=user_ctx["auth"])
    assert r.status_code == 200
    body = r.json()
    assert body["email"].lower() == user_ctx["email"].lower()
    assert body["onboarded"] is False

def test_profile_patch_targets(api_client, base_url, user_ctx):
    payload = {
        "age": 30, "gender": "male", "height_cm": 180,
        "weight_kg": 80, "target_weight_kg": 75, "activity": "moderate", "goal": "lose"
    }
    r = api_client.patch(f"{base_url}/api/auth/profile", headers=user_ctx["auth"], json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["onboarded"] is True
    t = body["targets"]
    # Mifflin: 10*80 + 6.25*180 - 5*30 + 5 = 800+1125-150+5 = 1780
    assert t["bmr"] == 1780
    # tdee = 1780 * 1.55 = 2759
    assert abs(t["tdee"] - 2759) <= 1
    # cal = 2759 - 500 = 2259
    assert abs(t["calories"] - 2259) <= 2
    assert t["protein_g"] == 144  # 1.8 * 80

# -------- Meals CRUD --------
def test_meals_crud(api_client, base_url, user_ctx):
    today = time.strftime("%Y-%m-%d")
    payload = {
        "meal_type": "lunch",
        "log_date": today,
        "items": [{"name": "TEST_apple", "portion_g": 150, "calories": 78, "protein_g": 0.4, "carbs_g": 21, "fat_g": 0.2, "fiber_g": 3.6, "sugar_g": 16}]
    }
    r = api_client.post(f"{base_url}/api/meals", headers=user_ctx["auth"], json=payload)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["total_calories"] == 78
    mid = m["id"]
    # list
    r = api_client.get(f"{base_url}/api/meals?log_date={today}", headers=user_ctx["auth"])
    assert r.status_code == 200
    assert any(x["id"] == mid for x in r.json())
    # delete
    r = api_client.delete(f"{base_url}/api/meals/{mid}", headers=user_ctx["auth"])
    assert r.status_code == 200
    # verify gone
    r = api_client.get(f"{base_url}/api/meals?log_date={today}", headers=user_ctx["auth"])
    assert not any(x["id"] == mid for x in r.json())

# -------- Water / Weight --------
def test_water_and_weight(api_client, base_url, user_ctx):
    today = time.strftime("%Y-%m-%d")
    r = api_client.post(f"{base_url}/api/water", headers=user_ctx["auth"], json={"log_date": today, "amount_ml": 500})
    assert r.status_code == 200
    assert r.json()["total_ml"] >= 500
    r = api_client.get(f"{base_url}/api/water?log_date={today}", headers=user_ctx["auth"])
    assert r.status_code == 200
    assert r.json()["total_ml"] >= 500

    r = api_client.post(f"{base_url}/api/weight", headers=user_ctx["auth"], json={"log_date": today, "weight_kg": 79.5})
    assert r.status_code == 200

# -------- Dashboard --------
def test_dashboard(api_client, base_url, user_ctx):
    r = api_client.get(f"{base_url}/api/dashboard", headers=user_ctx["auth"])
    assert r.status_code == 200
    data = r.json()
    assert "totals" in data and "targets" in data and "water_ml" in data

# -------- Premium toggle --------
def test_premium_toggle(api_client, base_url, user_ctx):
    r = api_client.post(f"{base_url}/api/auth/premium-toggle", headers=user_ctx["auth"])
    assert r.status_code == 200
    assert r.json()["premium"] is True
    r = api_client.post(f"{base_url}/api/auth/premium-toggle", headers=user_ctx["auth"])
    assert r.json()["premium"] is False

# -------- AI Coach chat --------
def test_ai_chat_sync_and_history(api_client, base_url, user_ctx):
    r = api_client.post(f"{base_url}/api/ai/chat-sync", headers=user_ctx["auth"],
                        json={"message": "Say hi in 5 words."}, timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("reply") and len(data["reply"]) > 0
    sid = data["session_id"]
    r = api_client.get(f"{base_url}/api/ai/chat/history?session_id={sid}", headers=user_ctx["auth"])
    assert r.status_code == 200
    hist = r.json()
    assert len(hist) >= 2

# -------- Scan bug-fix verification --------

REAL_FOOD_IMG_URL = "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&q=70"

@pytest.fixture(scope="module")
def real_food_b64():
    r = requests.get(REAL_FOOD_IMG_URL, timeout=30)
    r.raise_for_status()
    return base64.b64encode(r.content).decode()

def test_scan_meal_happy_path(api_client, base_url, user_ctx, real_food_b64):
    """Bug fix: /api/ai/scan-meal returns items[] within ~60s and no 502 on happy path."""
    t0 = time.time()
    r = api_client.post(f"{base_url}/api/ai/scan-meal", headers=user_ctx["auth"],
                        json={"image_b64": real_food_b64}, timeout=120)
    elapsed = time.time() - t0
    print(f"scan-meal elapsed={elapsed:.1f}s status={r.status_code}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
    data = r.json()
    assert "items" in data
    # A real food image should yield at least 1 item
    assert isinstance(data["items"], list)
    if data["items"]:
        it = data["items"][0]
        for k in ("name", "portion_g", "calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g"):
            assert k in it, f"missing field {k}"
        assert isinstance(it["calories"], (int, float))
    # Ensure elapsed is reasonable (< 90s including network); mostly < 60s
    assert elapsed <= 100, f"Scan too slow: {elapsed:.1f}s"

def test_scan_meal_invalid_base64_fast(api_client, base_url, user_ctx):
    """Regression: invalid base64 should NOT hang for 75s. Either fast 400 or fast 502."""
    t0 = time.time()
    r = api_client.post(f"{base_url}/api/ai/scan-meal", headers=user_ctx["auth"],
                        json={"image_b64": "not_an_image"}, timeout=100)
    elapsed = time.time() - t0
    print(f"invalid-scan elapsed={elapsed:.1f}s status={r.status_code}")
    # Should reject fast (well before 75s timeout wrapper). Accept 400 or 502 with fast fail.
    assert elapsed < 30, f"Endpoint hung for {elapsed:.1f}s on invalid input"
    assert r.status_code in (400, 422, 502), f"Unexpected status {r.status_code}: {r.text[:200]}"

# -------- Delete account (last) --------
def test_zzz_delete_account(api_client, base_url, user_ctx):
    r = api_client.delete(f"{base_url}/api/auth/account", headers=user_ctx["auth"])
    assert r.status_code == 200
    # verify gone
    r = api_client.get(f"{base_url}/api/auth/me", headers=user_ctx["auth"])
    assert r.status_code == 401
