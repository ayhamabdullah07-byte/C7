"""Tests for the new AI meal & snack recommend + refine endpoints."""
import time
import pytest


@pytest.fixture(scope="module")
def premium_user(api_client, base_url):
    email = f"TEST_rec_{int(time.time())}@c1.app"
    pw = "Test1234!"
    r = api_client.post(f"{base_url}/api/auth/register",
                        json={"email": email, "password": pw, "name": "TEST Rec User"})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    auth = {"Authorization": f"Bearer {tok}"}
    # profile so targets exist
    r = api_client.patch(f"{base_url}/api/auth/profile", headers=auth,
                        json={"age": 30, "gender": "male", "height_cm": 180,
                              "weight_kg": 80, "target_weight_kg": 75,
                              "activity": "moderate", "goal": "lose"})
    assert r.status_code == 200, r.text
    # flip premium
    r = api_client.post(f"{base_url}/api/auth/premium-toggle", headers=auth)
    assert r.status_code == 200
    assert r.json()["premium"] is True
    yield {"auth": auth, "email": email}
    # cleanup
    api_client.delete(f"{base_url}/api/auth/account", headers=auth)


def _assert_item_shape(it: dict):
    for k in ("id", "kind", "emoji", "name", "description", "prep_minutes",
              "tags", "ingredients", "calories", "protein_g", "carbs_g", "fat_g"):
        assert k in it, f"missing {k}"
    assert it["kind"] in ("meal", "snack")
    assert isinstance(it["ingredients"], list)
    for ing in it["ingredients"]:
        assert "name" in ing and "portion_g" in ing


def test_recommend_any_all(api_client, base_url, premium_user):
    r = api_client.post(f"{base_url}/api/ai/recommend",
                        headers=premium_user["auth"],
                        json={"focus": "any", "only": "all"}, timeout=120)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "remaining" in body
    rem = body["remaining"]
    for k in ("calories", "protein_g", "carbs_g", "fat_g"):
        assert k in rem
    items = body.get("items") or []
    for it in items:
        _assert_item_shape(it)
    meals = [i for i in items if i["kind"] == "meal"]
    snacks = [i for i in items if i["kind"] == "snack"]
    assert len(meals) >= 3, f"expected >=3 meals, got {len(meals)}: {[i['name'] for i in items]}"
    assert len(snacks) >= 3, f"expected >=3 snacks, got {len(snacks)}: {[i['name'] for i in items]}"


def test_recommend_vegetarian(api_client, base_url, premium_user):
    r = api_client.post(f"{base_url}/api/ai/recommend",
                        headers=premium_user["auth"],
                        json={"focus": "vegetarian", "only": "all"}, timeout=120)
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    assert len(items) > 0, "expected items for vegetarian"
    # no obvious meats in ingredient/name (soft check)
    meat_words = ["chicken", "beef", "pork", "bacon", "ham", "turkey", "salmon",
                  "tuna", "shrimp", "fish", "sausage", "lamb"]
    for it in items:
        blob = (it["name"] + " " + it.get("description", "") + " " +
                " ".join(ing["name"] for ing in it["ingredients"])).lower()
        for w in meat_words:
            assert w not in blob, f"vegetarian item contains meat '{w}': {it['name']} / {blob}"


def test_recommend_only_snacks(api_client, base_url, premium_user):
    r = api_client.post(f"{base_url}/api/ai/recommend",
                        headers=premium_user["auth"],
                        json={"focus": "any", "only": "snacks"}, timeout=120)
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    assert len(items) > 0
    for it in items:
        assert it["kind"] == "snack", f"expected snack only, got {it}"


def test_refine_under_500_calories(api_client, base_url, premium_user):
    # First get an item
    r = api_client.post(f"{base_url}/api/ai/recommend",
                        headers=premium_user["auth"],
                        json={"focus": "any", "only": "meals"}, timeout=120)
    assert r.status_code == 200, r.text
    items = r.json().get("items") or []
    assert items, "need at least 1 meal to refine"
    item = items[0]
    original_id = item["id"]

    r = api_client.post(f"{base_url}/api/ai/recommend/refine",
                        headers=premium_user["auth"],
                        json={"session_id": "TEST_refine_1", "item": item,
                              "request": "Under 500 calories"}, timeout=120)
    assert r.status_code == 200, r.text
    updated = r.json()
    _assert_item_shape(updated)
    assert updated["id"] == original_id, "id should be preserved"
    assert updated["calories"] <= 600, f"expected under-500-ish, got {updated['calories']}"


def test_refine_higher_protein(api_client, base_url, premium_user):
    r = api_client.post(f"{base_url}/api/ai/recommend",
                        headers=premium_user["auth"],
                        json={"focus": "any", "only": "meals"}, timeout=120)
    assert r.status_code == 200
    items = r.json().get("items") or []
    assert items
    item = items[0]
    original_id = item["id"]
    orig_p = item["protein_g"]

    r = api_client.post(f"{base_url}/api/ai/recommend/refine",
                        headers=premium_user["auth"],
                        json={"session_id": "TEST_refine_2", "item": item,
                              "request": "Higher in protein"}, timeout=120)
    assert r.status_code == 200, r.text
    updated = r.json()
    _assert_item_shape(updated)
    assert updated["id"] == original_id
    # Higher protein should be >= original (with some tolerance)
    assert updated["protein_g"] >= orig_p - 1, \
        f"protein did not increase: orig={orig_p} new={updated['protein_g']}"
