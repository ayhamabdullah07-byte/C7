import os
import time
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://c1-meal-scanner.preview.emergentagent.com").rstrip("/")

@pytest.fixture(scope="session")
def base_url():
    return BASE

@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s

@pytest.fixture(scope="session")
def user_ctx(api_client, base_url):
    # register a fresh user
    email = f"TEST_{int(time.time())}@c1.app"
    pw = "Test1234!"
    r = api_client.post(f"{base_url}/api/auth/register", json={"email": email, "password": pw, "name": "TEST User"})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    uid = r.json()["user_id"]
    return {"email": email, "password": pw, "token": tok, "user_id": uid, "auth": {"Authorization": f"Bearer {tok}"}}
