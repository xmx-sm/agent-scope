"""认证与接口契约回归测试，使用隔离的 SQLite 数据库。"""

import atexit
import hashlib
import hmac
import json
import os
import tempfile
import time
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


def test_runtime_config_metadata_and_range_validation(client):
    admin = login(client, settings.seed_admin_username, settings.seed_admin_password)
    headers = auth_headers(admin)
    configs = client.get("/api/admin/configs", headers=headers).json()["data"]
    item = next(row for row in configs if row["key"] == "runtime.ai_max_concurrent_streams")
    assert item["group"] == "运行资源"
    assert item["min"] == 1
    assert item["max"] == 128
    assert any(row["key"] == "runtime.external_call_max_concurrency" for row in configs)

    invalid = client.put(
        "/api/admin/configs/runtime.ai_max_concurrent_streams",
        json={"value": 0},
        headers=headers,
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == 400

    updated = client.put(
        "/api/admin/configs/runtime.ai_max_concurrent_streams",
        json={"value": 2},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["value"] == 2
    client.post(
        "/api/admin/configs/runtime.ai_max_concurrent_streams/reset",
        headers=headers,
    )


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


def signed_bot_request(client, bot, secret, payload):
    """生成带 HMAC 签名的机器人请求。"""
    raw = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        secret.encode(),
        timestamp.encode() + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    return client.post(
        f"/api/public/bots/{bot['id']}/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Event-Id": payload["event_id"],
            "X-Webhook-Signature": signature,
        },
    )


def test_bot_management_is_user_scoped(client):
    admin = login(client, settings.seed_admin_username, settings.seed_admin_password)
    password = "Test-Password-123!"
    user_id, username = create_user(client, admin, password)
    other_id = None
    try:
        user = login(client, username, password)
        created = client.post(
            "/api/bots",
            json={"name": "CRM 机器人", "platform": "webhook"},
            headers=auth_headers(user),
        )
        assert created.status_code == 200
        bot = created.json()["data"]
        assert bot["secret"]
        assert bot["tools_enabled"] is False
        assert bot["platform"] == "webhook"

        listed = client.get("/api/bots", headers=auth_headers(user)).json()["data"]
        assert [item["id"] for item in listed] == [bot["id"]]
        assert "secret" not in listed[0]

        other_id, other_name = create_user(client, admin, password)
        other = login(client, other_name, password)
        missing = client.get(f"/api/bots/{bot['id']}", headers=auth_headers(other))
        assert missing.status_code == 404
    finally:
        client.delete(f"/api/admin/users/{user_id}", headers=auth_headers(admin))
        if other_id:
            client.delete(f"/api/admin/users/{other_id}", headers=auth_headers(admin))


def test_bot_webhook_signature_dedupe_and_session_isolation(client, monkeypatch):
    from app.services.integrations.bots import webhook

    admin = login(client, settings.seed_admin_username, settings.seed_admin_password)
    password = "Test-Password-123!"
    user_id, username = create_user(client, admin, password)
    try:
        user = login(client, username, password)
        bot = client.post(
            "/api/bots",
            json={"name": "Webhook 测试机器人"},
            headers=auth_headers(user),
        ).json()["data"]
        calls = []

        async def fake_run_turn(params):
            """记录 Agent 调用参数。"""
            calls.append(params)
            return "机器人回复"

        monkeypatch.setattr(webhook, "async_run_turn", fake_run_turn)
        payload = {
            "event_id": "event-1",
            "sender_id": "sender-1",
            "chat_id": "chat-1",
            "chat_type": "private",
            "text": "你好",
        }
        invalid = signed_bot_request(client, bot, "wrong-secret", payload)
        assert invalid.status_code == 401

        valid = signed_bot_request(client, bot, bot["secret"], payload)
        assert valid.status_code == 200
        assert valid.json()["data"]["reply"] == "机器人回复"
        assert calls[0]["source"] == "bot"
        assert calls[0]["tools_enabled"] is False

        duplicate = signed_bot_request(client, bot, bot["secret"], payload)
        assert duplicate.status_code == 409

        payload["event_id"] = "event-2"
        payload["sender_id"] = "sender-2"
        second = signed_bot_request(client, bot, bot["secret"], payload)
        assert second.status_code == 200
        assert second.json()["data"]["conversation_id"] != valid.json()["data"]["conversation_id"]

        rotated = client.post(
            f"/api/bots/{bot['id']}/rotate-secret", headers=auth_headers(user)
        ).json()["data"]
        payload["event_id"] = "event-3"
        old_secret = signed_bot_request(client, bot, bot["secret"], payload)
        assert old_secret.status_code == 401
        new_secret = signed_bot_request(client, bot, rotated["secret"], payload)
        assert new_secret.status_code == 200

        client.patch(f"/api/bots/{bot['id']}", json={"enabled": False}, headers=auth_headers(user))
        payload["event_id"] = "event-4"
        disabled = signed_bot_request(client, bot, rotated["secret"], payload)
        assert disabled.status_code == 403
    finally:
        client.delete(f"/api/admin/users/{user_id}", headers=auth_headers(admin))
