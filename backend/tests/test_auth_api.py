"""认证与接口契约回归测试，使用隔离的 SQLite 数据库。"""

import atexit
import os
import tempfile
import uuid
from pathlib import Path

_TEST_DIR = tempfile.TemporaryDirectory(prefix="agent_scope_tests_")
atexit.register(_TEST_DIR.cleanup)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{Path(_TEST_DIR.name) / 'test.db'}"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["SEED_DEMO_USERS"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def login(client, account, password):
    response = client.post("/api/auth/login", json={"account": account, "password": password})
    assert response.status_code == 200
    assert response.json()["code"] == 200
    return response.json()["data"]


def auth_headers(data):
    return {"Authorization": f"Bearer {data['access_token']}"}


def create_user(client, admin, password):
    username = f"test_{uuid.uuid4().hex[:12]}"
    response = client.post(
        "/api/admin/users",
        json={"username": username, "password": password, "nickname": username},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200
    return response.json()["data"]["id"], username


def test_refresh_rotation_and_replay_revokes_family(client):
    data = login(client, settings.seed_admin_username, settings.seed_admin_password)
    original = data["refresh_token"]
    response = client.post("/api/auth/refresh", json={"refresh_token": original})
    assert response.status_code == 200
    rotated = response.json()["data"]["refresh_token"]
    assert rotated != original

    replay = client.post("/api/auth/refresh", json={"refresh_token": original})
    assert replay.status_code == 401
    assert replay.json()["code"] == 401

    revoked = client.post("/api/auth/refresh", json={"refresh_token": rotated})
    assert revoked.status_code == 401
    assert revoked.json()["code"] == 401


def test_password_change_revokes_refresh_tokens(client):
    admin = login(client, settings.seed_admin_username, settings.seed_admin_password)
    password = "Test-Password-123!"
    user_id, username = create_user(client, admin, password)
    try:
        data = login(client, username, password)
        response = client.post(
            "/api/auth/change-password",
            json={"old_password": password, "new_password": "New-Password-456!"},
            headers=auth_headers(data),
        )
        assert response.status_code == 200
        refresh = client.post(
            "/api/auth/refresh", json={"refresh_token": data["refresh_token"]}
        )
        assert refresh.status_code == 401
        assert refresh.json()["msg"] == "刷新令牌已失效，请重新登录"
    finally:
        client.delete(f"/api/admin/users/{user_id}", headers=auth_headers(admin))


def test_logout_revokes_refresh_family(client):
    admin = login(client, settings.seed_admin_username, settings.seed_admin_password)
    password = "Test-Password-123!"
    user_id, username = create_user(client, admin, password)
    try:
        data = login(client, username, password)
        refresh = client.post(
            "/api/auth/refresh", json={"refresh_token": data["refresh_token"]}
        ).json()["data"]["refresh_token"]
        logout = client.post("/api/auth/logout", json={"refresh_token": refresh})
        assert logout.status_code == 200
        revoked = client.post("/api/auth/refresh", json={"refresh_token": refresh})
        assert revoked.status_code == 401
    finally:
        client.delete(f"/api/admin/users/{user_id}", headers=auth_headers(admin))


def test_register_returns_usable_refresh_session(client):
    admin = login(client, settings.seed_admin_username, settings.seed_admin_password)
    username = f"test_{uuid.uuid4().hex[:12]}"
    password = "Test-Password-123!"
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "nickname": username},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    tokens = data["tokens"]
    try:
        me = client.get("/api/auth/me", headers=auth_headers(tokens))
        assert me.status_code == 200
        refresh = client.post(
            "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refresh.status_code == 200
    finally:
        client.delete(f"/api/admin/users/{data['user']['id']}", headers=auth_headers(admin))


def test_http_status_matches_business_error(client):
    invalid = client.post("/api/auth/login", json={})
    assert invalid.status_code == 400
    assert invalid.json()["code"] == 400

    admin = login(client, settings.seed_admin_username, settings.seed_admin_password)
    password = "Test-Password-123!"
    user_id, username = create_user(client, admin, password)
    try:
        user = login(client, username, password)
        forbidden = client.get("/api/admin/users", headers=auth_headers(user))
        assert forbidden.status_code == 403
        assert forbidden.json()["code"] == 403
        missing = client.get(
            "/api/agent/conversations/00000000-0000-0000-0000-000000000000/messages",
            headers=auth_headers(user),
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == 404
    finally:
        client.delete(f"/api/admin/users/{user_id}", headers=auth_headers(admin))


def test_openapi_declares_response_envelope_and_a2a_key(client):
    spec = client.get("/openapi.json").json()
    assert "ApiResponse" in spec["components"]["schemas"]
    for path_item in spec["paths"].values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            media = operation.get("responses", {}).get("200", {}).get("content", {})
            if "application/json" not in media:
                continue
            schema = media["application/json"].get("schema")
            assert schema not in (None, {})
    security = spec["paths"]["/api/a2a/agents"]["get"]["security"]
    assert security == [{"APIKeyHeader": []}]
