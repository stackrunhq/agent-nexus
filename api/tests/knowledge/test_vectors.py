import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_nexus.app import Settings, create_app
from agent_nexus.models.schemas import ModelConfig
from agent_nexus.storage.database import Database
from agent_nexus.knowledge.vectors import indexes
from agent_nexus_cli.database import upgrade, import_sqlite
from test_ingestion import ADMIN, scope as scope
from test_search import publish_catalog


def configure(client):
    model = ModelConfig(
        alias="embed-local",
        provider="ollama",
        model="embedding-v1",
        base_url="http://localhost:11434",
        deployment="local",
        capabilities=["embeddings"],
    )
    client.app.state.gateway.store.put(model)
    return model


def provider(request):
    body = json.loads(request.content)
    return httpx.Response(
        200,
        json={
            "embeddings": [
                [1.0, 0.1] if "password" in text.lower() or "密码" in text else [0.1, 1.0]
                for text in body["input"]
            ]
        },
    )


def test_persist_search_model_binding_and_withdrawal(scope, tmp_path):
    client, tenants, app, version, root, path = scope
    first, _, _ = publish_catalog(client, root)
    model = configure(client)
    client.app.state.tenants.grant(tenants[0]["id"], model.alias, True)
    client.app.state.gateway.client._transport = httpx.MockTransport(provider)
    # Gateway HTTP transport is supplied by the application's client attribute.
    assert (
        client.post(root + "/vector-index", headers=ADMIN, json={"model": model.alias}).status_code
        == 200
    )
    assert (
        client.get(root + "/vector-index", headers=ADMIN, params={"model": model.alias}).json()[
            "status"
        ]
        == "ready"
    )
    public = f"/api/v1/applications/{app['id']}/versions/{version['id']}/vector-search"
    member = {"Authorization": "Bearer " + tenants[0]["api_key"]}
    body = {"model": model.alias, "query": "password"}
    result = client.post(public, headers=member, json=body)
    assert result.status_code == 200 and result.json()["data"][0]["document_id"] == first["id"]
    assert result.json()["method"] == "vector_cosine"
    assert (
        client.post(
            public, headers={"Authorization": "Bearer " + tenants[1]["api_key"]}, json=body
        ).status_code
        == 404
    )
    target = str(tmp_path / "copy.db")
    assert import_sqlite(path, target)["knowledge_vector_indexes"] == 1
    with TestClient(
        create_app(
            Settings("a" * 32, "b" * 32, target, {"localhost"}, "tenant"),
            httpx.MockTransport(provider),
        )
    ) as copied:
        assert copied.post(public, headers=member, json=body).status_code == 200
    client.app.state.gateway.store.put(
        model.model_copy(update={"model": "embedding-v2"}),
        expected_etag=client.app.state.gateway.store.etag(model),
    )
    assert client.post(public, headers=member, json=body).json()["error"]["code"] == "index_stale"
    assert (
        client.post(root + "/vector-index", headers=ADMIN, json={"model": model.alias}).status_code
        == 200
    )
    client.patch(root + "/documents/" + first["id"], headers=ADMIN, json={"published": False})
    assert (
        client.get(root + "/vector-index", headers=ADMIN, params={"model": model.alias}).json()[
            "status"
        ]
        == "stale"
    )
    assert client.post(public, headers=member, json=body).json()["error"]["code"] == "index_stale"


def test_grants_zero_vectors_failure_preserves_index_and_inflight_withdrawal(scope):
    client, tenants, _, _, root, _ = scope
    first, _, _ = publish_catalog(client, root)
    model = configure(client)
    calls = []
    mode = "normal"

    def upstream(request):
        calls.append(request)
        if mode == "withdraw":
            client.app.state.knowledge.publish(
                tenants[0]["id"],
                root.split("/applications/")[1].split("/")[0],
                first["version_id"],
                first["id"],
                False,
                "test",
                "test",
            )
        if mode == "zero":
            return httpx.Response(
                200, json={"embeddings": [[0, 0] for _ in json.loads(request.content)["input"]]}
            )
        return provider(request)

    client.app.state.gateway.client._transport = httpx.MockTransport(upstream)
    assert (
        client.post(root + "/vector-index", headers=ADMIN, json={"model": model.alias}).status_code
        == 403
    )
    assert calls == []
    client.app.state.tenants.grant(tenants[0]["id"], model.alias, True)
    assert (
        client.post(
            root + "/vector-search", headers=ADMIN, json={"model": model.alias, "query": "password"}
        ).json()["error"]["code"]
        == "index_missing"
    )
    assert calls == []
    assert (
        client.post(root + "/vector-index", headers=ADMIN, json={"model": model.alias}).status_code
        == 200
    )
    with client.app.state.knowledge.database.read() as db:
        old = db.execute(indexes.select()).mappings().one()["payload"]
    mode = "zero"
    assert (
        client.post(root + "/vector-index", headers=ADMIN, json={"model": model.alias}).status_code
        == 502
    )
    with client.app.state.knowledge.database.read() as db:
        assert db.execute(indexes.select()).mappings().one()["payload"] == old
    mode = "withdraw"
    assert (
        client.post(
            root + "/vector-search", headers=ADMIN, json={"model": model.alias, "query": "password"}
        ).json()["error"]["code"]
        == "index_stale"
    )


def test_old_0004_requires_explicit_upgrade(tmp_path):
    path = str(tmp_path / "old.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE knowledge_vector_indexes")
        db.execute("UPDATE alembic_version SET version_num='0004'")
    with pytest.raises(RuntimeError):
        Database(path)
    upgrade(path)
    database = Database(path)
    assert database.check()["revision"] == "0017"
    database.close()


def test_capacity_and_inflight_model_change(scope, monkeypatch):
    client, tenants, _, _, root, _ = scope
    publish_catalog(client, root)
    model = configure(client)
    client.app.state.tenants.grant(tenants[0]["id"], model.alias, True)
    calls = []

    def changed(request):
        calls.append(request)
        client.app.state.gateway.store.put(
            model.model_copy(update={"model": "changed-during-build"}),
            expected_etag=client.app.state.gateway.store.etag(model),
        )
        return provider(request)

    client.app.state.gateway.client._transport = httpx.MockTransport(changed)
    from agent_nexus.knowledge import vectors

    monkeypatch.setattr(vectors, "MAX_INDEX_CHUNKS", 1)
    assert (
        client.post(root + "/vector-index", headers=ADMIN, json={"model": model.alias}).status_code
        == 409
    )
    assert calls == []
    monkeypatch.setattr(vectors, "MAX_INDEX_CHUNKS", 128)
    response = client.post(root + "/vector-index", headers=ADMIN, json={"model": model.alias})
    assert response.status_code == 409 and response.json()["error"]["code"] == "index_stale"
    with client.app.state.knowledge.database.read() as db:
        assert db.execute(indexes.select()).first() is None
