import asyncio
import sqlite3

import pytest
from sqlalchemy import select
from agent_nexus.core.errors import GatewayError
from agent_nexus.knowledge.index_jobs import run_once
from agent_nexus.models.usage import UsageStore, calls
from agent_nexus.storage.database import Database
from agent_nexus_cli.database import upgrade
from test_ingestion import ADMIN, scope as scope
from test_index_jobs import prepare


def test_explicit_tasks_survive_duplicate_requests_and_sync_build(scope):
    store, alias = prepare(scope)
    client, tenants, app, version, root, _ = scope
    identifiers = []
    for _ in range(2):
        task = store.enqueue(tenants[0]["id"], app["id"], version["id"], alias, "test", "duplicate")
        identifiers.append(task["id"])
        assert asyncio.run(run_once(store.database, client.app.state.gateway))
    for identifier in identifiers:
        result = client.get(root + "/index-jobs/" + identifier, headers=ADMIN).json()
        assert result["calls"]["data"]
        assert all(
            row["association"] == "exact" and row["index_job_id"] == identifier
            for row in result["calls"]["data"]
        )
    config = client.app.state.gateway.resolve(alias, "embeddings")
    usage = UsageStore(store.database)
    usage.start(tenants[0]["id"], config, "embeddings", "duplicate")
    result = client.get(root + "/index-jobs/" + identifiers[0], headers=ADMIN).json()
    assert {row["association"] for row in result["calls"]["data"]} == {"exact", "request_match"}
    with pytest.raises(GatewayError):
        usage.start(tenants[1]["id"], config, "embeddings", "duplicate", identifiers[0])
    assert (
        client.post(root + "/vector-index", headers=ADMIN, json={"model": alias}).status_code == 200
    )
    with store.database.read() as db:
        linked = (
            db.execute(select(calls.c.index_job_id).where(calls.c.index_job_id.is_not(None)))
            .scalars()
            .all()
        )
    assert len(set(linked)) == 3


def test_0015_upgrade_preserves_unlinked_calls(tmp_path):
    path = str(tmp_path / "old.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP INDEX ix_model_calls_tenant_job")
        db.execute("ALTER TABLE model_calls DROP COLUMN index_job_id")
        db.execute("INSERT INTO tenants (id,name,enabled,key_hash) VALUES ('t','t',1,'hash')")
        db.execute(
            "INSERT INTO model_calls (id,tenant_id,request_id,model,model_fingerprint,capability,created_at,status) VALUES ('old','t','r','m','f','embeddings',1,'pending')"
        )
        db.execute("UPDATE alembic_version SET version_num='0015'")
    with pytest.raises(RuntimeError):
        Database(path)
    upgrade(path)
    database = Database(path)
    with database.read() as db:
        row = db.execute(select(calls).where(calls.c.id == "old")).mappings().one()
        assert row["index_job_id"] is None and row["status"] == "pending"
    database.close()
