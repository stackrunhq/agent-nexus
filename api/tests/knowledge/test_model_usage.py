import sqlite3
import httpx
import pytest
from test_ingestion import ADMIN, scope as scope
from test_index_jobs import prepare
from agent_nexus.models.usage import UsageStore
from agent_nexus.storage.database import Database
from agent_nexus_cli.database import upgrade


def test_records_embedding_and_failed_invocation_without_content(scope):
    store, alias = prepare(scope)
    client, tenants, _, _, root, _ = scope
    client.app.state.gateway.client._transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"embeddings": [[1, 0]], "prompt_eval_count": 7})
    )
    member = {"Authorization": "Bearer " + tenants[0]["api_key"]}
    assert (
        client.post(
            "/api/v1/embeddings", headers=member, json={"model": alias, "input": ["private text"]}
        ).status_code
        == 200
    )
    usage = UsageStore(store.database)
    row = usage.list(tenants[0]["id"])["data"][0]
    assert row["status"] == "succeeded" and row["input_tokens"] == 7
    assert row["output_tokens"] is None and "private text" not in str(row)
    assert usage.list(tenants[1]["id"])["data"] == []
    client.app.state.gateway.client._transport = httpx.MockTransport(
        lambda request: httpx.Response(429)
    )
    assert (
        client.post(
            "/api/v1/embeddings", headers=member, json={"model": alias, "input": ["secret"]}
        ).status_code
        == 429
    )
    assert any(
        row["error"] == "provider_rate_limited" for row in usage.list(tenants[0]["id"])["data"]
    )
    path = f"/api/v1/admin/tenants/{tenants[0]['id']}/model-calls"
    assert client.get(path, headers=member).status_code == 401
    assert len(client.get(path, headers=ADMIN, params={"limit": 1}).json()["data"]) == 1


def test_interrupted_record_stays_pending(scope):
    store, alias = prepare(scope)
    client, tenants, _, _, _, _ = scope
    usage = UsageStore(store.database)
    usage.start(
        tenants[0]["id"],
        client.app.state.gateway.resolve(alias, "embeddings"),
        "embeddings",
        "test",
    )
    assert usage.list(tenants[0]["id"])["data"][0]["status"] == "pending"


def test_0007_explicit_upgrade(tmp_path):
    path = str(tmp_path / "old.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE model_calls")
        db.execute("UPDATE alembic_version SET version_num='0007'")
    with pytest.raises(RuntimeError):
        Database(path)
    upgrade(path)
    database = Database(path)
    assert database.check()["revision"] == "0010"
    database.close()
