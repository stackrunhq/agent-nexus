import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from agent_nexus.app import Settings, create_app
from agent_nexus.storage.database import Database, run
from agent_nexus_cli.database import upgrade, import_sqlite
from agent_nexus.identity.schemas import UserCreate
from agent_nexus.identity.store import IdentityStore

ADMIN = {"Authorization": "Bearer " + "a" * 32}
PASSWORD = "correct-long-password"


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings("a" * 32, "b" * 32, str(tmp_path / "identity.db"), {"localhost"}))
    with TestClient(app) as client:
        yield client


def create(client, name="alice", role="platform_admin", tenant_id=None):
    result = client.post(
        "/api/v1/admin/users",
        headers=ADMIN,
        json={
            "username": name,
            "password": PASSWORD,
            "role": role,
            "tenant_id": tenant_id,
        },
    )
    assert result.status_code == 201, result.text
    assert "password" not in result.text
    return result.json()


def login(client, name="alice", password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"username": name, "password": password})


def bearer(response):
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_admin_login_audit_relogin_logout_and_password_hash(client):
    user = create(client)
    assert client.get("/api/v1/admin/users", headers=ADMIN).json()["data"][0]["enabled"] is True
    first = bearer(login(client))
    assert client.get("/api/v1/auth/me", headers=first).json()["id"] == user["id"]
    assert client.get("/api/v1/admin/tenants", headers=first).status_code == 200
    config = {
        "alias": "audit-test",
        "provider": "ollama",
        "model": "test",
        "base_url": "http://localhost:11434",
        "deployment": "local",
        "capabilities": ["chat"],
    }
    assert (
        client.put(
            "/api/v1/admin/models/audit-test", headers={**first, "If-None-Match": "*"}, json=config
        ).status_code
        == 200
    )
    assert (
        client.get("/api/v1/admin/audit-events", headers=first).json()["data"][0]["actor"]
        == user["id"]
    )
    assert client.get("/api/v1/models", headers=first).status_code == 403
    with client.app.state.identity.database.read() as db:
        stored = run(db, "SELECT password_hash FROM users").scalar_one()
        assert stored.startswith("scrypt$") and PASSWORD not in stored
        assert (
            run(db, "SELECT key_hash FROM user_sessions").scalar_one()
            != first["Authorization"].split()[1]
        )
    second = bearer(login(client))
    assert client.get("/api/v1/auth/me", headers=first).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=second).status_code == 204
    assert client.get("/api/v1/auth/me", headers=second).status_code == 401
    events = client.get("/api/v1/admin/user-events", headers=ADMIN).json()["data"]
    assert events[0]["action"] == "logout"
    assert events[0]["actor"] == user["id"]
    assert PASSWORD not in str(events)


def test_member_scope_and_admin_denial_even_in_bootstrap_mode(client):
    tenant = client.post("/api/v1/admin/tenants", headers=ADMIN, json={"name": "A"}).json()
    other = client.post("/api/v1/admin/tenants", headers=ADMIN, json={"name": "B"}).json()
    for alias in ["model-a", "model-b"]:
        config = {
            "alias": alias,
            "provider": "ollama",
            "model": "demo",
            "base_url": "http://localhost:11434",
            "deployment": "local",
            "capabilities": ["chat"],
        }
        assert (
            client.put(
                f"/api/v1/admin/models/{alias}",
                json=config,
                headers={**ADMIN, "If-None-Match": "*"},
            ).status_code
            == 200
        )
    client.put(f"/api/v1/admin/tenants/{tenant['id']}/models/model-a", headers=ADMIN)
    client.put(f"/api/v1/admin/tenants/{other['id']}/models/model-b", headers=ADMIN)
    create(client, role="tenant_user", tenant_id=tenant["id"])
    session = bearer(login(client))
    assert [m["id"] for m in client.get("/api/v1/models", headers=session).json()["data"]] == [
        "model-a"
    ]
    assert client.get("/api/v1/admin/users", headers=session).status_code == 403
    assert client.get("/api/v1/admin/tenants", headers=session).status_code == 403
    assert (
        client.post(
            "/api/v1/admin/users",
            headers=session,
            json={"username": "mallory", "password": PASSWORD, "role": "platform_admin"},
        ).status_code
        == 403
    )
    denied = client.post(
        "/api/v1/chat/completions",
        headers=session,
        json={"model": "model-b", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert denied.status_code == 403
    client.patch(f"/api/v1/admin/tenants/{tenant['id']}", headers=ADMIN, json={"enabled": False})
    assert client.get("/api/v1/models", headers=session).status_code == 401
    assert login(client).status_code == 401


def test_disable_reset_and_expiration(client):
    user = create(client)
    session = bearer(login(client))
    path = f"/api/v1/admin/users/{user['id']}"
    assert client.patch(path, headers=ADMIN, json={"enabled": False}).status_code == 204
    assert client.get("/api/v1/auth/me", headers=session).status_code == 401
    assert login(client).status_code == 401
    client.patch(path, headers=ADMIN, json={"enabled": True})
    session = bearer(login(client))
    assert (
        client.post(
            path + "/reset-password", headers=ADMIN, json={"password": "another-long-password"}
        ).status_code
        == 204
    )
    assert login(client).status_code == 401
    assert client.get("/api/v1/auth/me", headers=session).status_code == 401
    session = bearer(login(client, password="another-long-password"))
    with client.app.state.identity.database.write("identity") as db:
        run(db, "UPDATE user_sessions SET expires_at=:now", now=int(time.time()) - 1)
    assert client.get("/api/v1/auth/me", headers=session).status_code == 401


def test_login_throttle_persists_and_recovers(client):
    create(client)
    for _ in range(5):
        assert login(client, password="wrong").status_code == 401
    assert login(client).status_code == 401
    with client.app.state.identity.database.write("identity") as db:
        assert run(db, "SELECT failed_attempts FROM users").scalar_one() == 5
        run(db, "UPDATE users SET blocked_until=:past", past=int(time.time()) - 1)
    assert login(client).status_code == 200
    assert login(client, name="unknown").status_code == 401


def test_invalid_roles_and_missing_scope(client):
    for body in [
        {"role": "tenant_user"},
        {"role": "root"},
        {"role": "platform_admin", "tenant_id": "somewhere"},
    ]:
        result = client.post(
            "/api/v1/admin/users",
            headers=ADMIN,
            json={"username": "alice", "password": PASSWORD, **body},
        )
        assert result.status_code == 422
    assert client.get("/api/v1/auth/me", headers=ADMIN).status_code == 401


def test_upgrade_old_version_requires_explicit_migration(tmp_path):
    path = str(tmp_path / "old.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE user_sessions")
        db.execute("DROP TABLE user_events")
        db.execute("DROP TABLE users")
        db.execute("UPDATE alembic_version SET version_num='0001'")
    with pytest.raises(RuntimeError):
        Database(path)
    upgrade(path)
    database = Database(path)
    assert database.check()["revision"] == "0006"
    database.close()


def test_import_preserves_personal_credentials_and_sessions(tmp_path):
    source, target = str(tmp_path / "source.db"), str(tmp_path / "target.db")
    database = Database(source)
    identity = IdentityStore(database)
    user = identity.create(
        UserCreate(username="alice", password=PASSWORD, role="platform_admin"), "platform_admin"
    )
    token = identity.login("alice", PASSWORD)["access_token"]
    database.close()
    counts = import_sqlite(source, target)
    assert counts["users"] == 1 and counts["user_events"] == 2
    restored = Database(target)
    assert IdentityStore(restored).authenticate(token)["id"] == user["id"]
    restored.close()
