from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_nexus.app import Settings, create_app

ADMIN = {"Authorization": "Bearer " + "a" * 32}


def auth(key):
    return {"Authorization": "Bearer " + key}


@pytest.fixture
def env(tmp_path):
    calls = []

    def upstream(request):
        calls.append(request)
        if request.url.path.endswith("embeddings"):
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    settings = Settings(
        "a" * 32, "c" * 32, str(tmp_path / "db.sqlite"), {"provider.test"}, "tenant"
    )
    with TestClient(create_app(settings, httpx.MockTransport(upstream))) as client:
        for alias in ("alpha", "beta"):
            response = client.put(
                f"/api/v1/admin/models/{alias}",
                headers={**ADMIN, "If-None-Match": "*"},
                json={
                    "alias": alias,
                    "provider": "openai_compatible",
                    "model": alias,
                    "base_url": "https://provider.test/v1",
                    "deployment": "cloud",
                    "capabilities": ["chat", "embeddings"],
                },
            )
            assert response.status_code == 200
        a = client.post("/api/v1/admin/tenants", headers=ADMIN, json={"name": "企业甲"}).json()
        b = client.post("/api/v1/admin/tenants", headers=ADMIN, json={"name": "企业乙"}).json()
        yield client, settings, a, b, calls


def grant(client, tenant, alias):
    return client.put(f"/api/v1/admin/tenants/{tenant['id']}/models/{alias}", headers=ADMIN)


def chat(client, tenant, alias):
    return client.post(
        "/api/v1/chat/completions",
        headers=auth(tenant["api_key"]),
        json={"model": alias, "messages": [{"role": "user", "content": "test"}]},
    )


def test_tenant_model_isolation(env):
    client, _, a, b, calls = env
    assert client.get("/api/v1/models", headers=auth(a["api_key"])).json() == {"data": []}
    assert grant(client, a, "alpha").status_code == 204
    assert grant(client, b, "beta").status_code == 204
    assert [
        m["id"] for m in client.get("/api/v1/models", headers=auth(a["api_key"])).json()["data"]
    ] == ["alpha"]
    assert chat(client, a, "beta").status_code == 403
    assert chat(client, b, "alpha").status_code == 403
    assert not calls
    assert chat(client, a, "alpha").status_code == 200
    assert len(calls) == 1


def test_embedding_authorization_and_forged_tenant(env):
    client, _, a, b, calls = env
    grant(client, a, "alpha")
    body = {"model": "beta", "input": ["test"]}
    assert (
        client.post("/api/v1/embeddings", headers=auth(a["api_key"]), json=body).status_code == 403
    )
    body["tenant_id"] = b["id"]
    assert (
        client.post("/api/v1/embeddings", headers=auth(a["api_key"]), json=body).status_code == 422
    )
    assert not calls
    response = client.post(
        "/api/v1/embeddings", headers=auth(a["api_key"]), json={"model": "alpha", "input": ["test"]}
    )
    assert response.status_code == 200


def test_global_and_admin_tokens_cannot_bypass_tenant_mode(env):
    client, _, a, _, _ = env
    for headers in (ADMIN, auth("c" * 32), auth("invalid")):
        assert client.get("/api/v1/models", headers=headers).status_code == 401
    for path in ("/api/v1/admin/tenants", "/api/v1/admin/models", "/api/v1/admin/audit-events"):
        assert client.get(path, headers=auth(a["api_key"])).status_code == 401


def test_revoke_disable_rotate_and_restart(env):
    client, settings, a, _, calls = env
    grant(client, a, "alpha")
    path = f"/api/v1/admin/tenants/{a['id']}"
    rotated = client.post(path + "/rotate-key", headers=ADMIN).json()
    assert chat(client, a, "alpha").status_code == 401
    a["api_key"] = rotated["api_key"]
    assert chat(client, a, "alpha").status_code == 200
    assert client.patch(path, headers=ADMIN, json={"enabled": False}).status_code == 200
    assert chat(client, a, "alpha").status_code == 401
    client.patch(path, headers=ADMIN, json={"enabled": True})
    assert client.delete(path + "/models/alpha", headers=ADMIN).status_code == 204
    assert chat(client, a, "alpha").status_code == 403
    assert len(calls) == 1
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get("/api/v1/models", headers=auth(a["api_key"])).json() == {"data": []}


def test_keys_not_in_database_listing_or_events(env):
    client, settings, a, b, _ = env
    listing = client.get("/api/v1/admin/tenants", headers=ADMIN)
    events = client.get(f"/api/v1/admin/tenants/{a['id']}/events", headers=ADMIN)
    assert "key_hash" not in listing.text and "api_key" not in listing.text
    for tenant in (a, b):
        assert tenant["api_key"] not in listing.text + events.text
        assert tenant["api_key"].encode() not in Path(settings.database_path).read_bytes()


def test_invalid_grants_and_idempotent_events(env):
    client, _, a, _, _ = env
    assert grant(client, a, "missing").status_code == 404
    grant(client, a, "alpha")
    grant(client, a, "alpha")
    path = f"/api/v1/admin/tenants/{a['id']}"
    events = client.get(path + "/events", headers=ADMIN).json()["data"]
    assert [e["action"] for e in events] == ["model_granted", "created"]
    assert client.get(path + "/models", headers=ADMIN).json() == {"data": ["alpha"]}
    assert (
        client.post("/api/v1/admin/tenants", headers=ADMIN, json={"name": " "}).status_code == 422
    )
    assert client.post("/api/v1/admin/tenants/missing/rotate-key", headers=ADMIN).status_code == 404


def test_invalid_mode_fails_closed(tmp_path):
    settings = Settings("a" * 32, "", str(tmp_path / "db"), set(), "tennat")
    with pytest.raises(RuntimeError), TestClient(create_app(settings)):
        pass


def test_tenant_mode_does_not_need_global_token(tmp_path):
    settings = Settings("a" * 32, "", str(tmp_path / "db"), set(), "tenant")
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").status_code == 200
