import sqlite3
import pytest
from test_ingestion import ADMIN, scope as scope
from test_index_jobs import prepare
from agent_nexus.models.usage import UsageStore
from agent_nexus.storage.database import Database
from agent_nexus_cli.database import upgrade


def test_override_zero_inheritance_and_persistence(scope):
    store, alias = prepare(scope)
    client, tenants, _, _, _, _ = scope
    path = f"/api/v1/admin/tenants/{tenants[0]['id']}/model-quota"
    assert (
        client.put(path, headers=ADMIN, json={"daily_limit": 0}).json()["effective_daily_limit"]
        == 0
    )
    member = {"Authorization": "Bearer " + tenants[0]["api_key"]}
    assert (
        client.post(
            "/api/v1/embeddings", headers=member, json={"model": alias, "input": ["x"]}
        ).status_code
        == 429
    )
    assert UsageStore(store.database).summary(tenants[0]["id"])["daily_used"] == 0
    assert UsageStore(store.database).get_policy(tenants[1]["id"])["daily_limit"] is None
    assert client.put(path, headers=ADMIN, json={"daily_limit": None}).status_code == 200
    assert (
        client.post(
            "/api/v1/embeddings", headers=member, json={"model": alias, "input": ["x"]}
        ).status_code
        == 200
    )
    assert client.put(path, headers=ADMIN, json={"daily_limit": 1}).status_code == 200
    assert (
        client.post(
            "/api/v1/embeddings", headers=member, json={"model": alias, "input": ["x"]}
        ).status_code
        == 429
    )
    assert client.put(path, headers=ADMIN, json={"daily_limit": True}).status_code == 422
    assert client.put(path, headers=member, json={"daily_limit": 100}).status_code == 401
    assert client.get("/api/v1/admin/tenants/missing/model-quota", headers=ADMIN).status_code == 404


def test_0008_explicit_upgrade(tmp_path):
    path = str(tmp_path / "old.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE tenant_model_quotas")
        db.execute("UPDATE alembic_version SET version_num='0008'")
    with pytest.raises(RuntimeError):
        Database(path)
    upgrade(path)
    database = Database(path)
    assert database.check()["revision"] == "0010"
    database.close()
