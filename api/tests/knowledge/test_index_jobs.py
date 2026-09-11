import asyncio
import sqlite3
import httpx
import pytest
from sqlalchemy import select

from agent_nexus.core.errors import GatewayError
from agent_nexus.knowledge.index_jobs import IndexJobs, jobs, run_once
from agent_nexus.knowledge.vectors import VectorService, indexes
from test_ingestion import ADMIN, scope as scope
from test_search import publish_catalog
from test_vectors import configure, provider


def test_0005_requires_upgrade(tmp_path):
    from agent_nexus_cli.database import upgrade
    from agent_nexus.storage.database import Database

    path = str(tmp_path / "old.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE knowledge_index_jobs")
        db.execute("UPDATE alembic_version SET version_num='0005'")
    with pytest.raises(RuntimeError):
        Database(path)
    upgrade(path)
    database = Database(path)
    assert database.check()["revision"] == "0007"
    database.close()


def prepare(scope):
    client, tenants, app, version, root, _ = scope
    publish_catalog(client, root)
    model = configure(client)
    client.app.state.tenants.grant(tenants[0]["id"], model.alias, True)
    client.app.state.gateway.client._transport = httpx.MockTransport(provider)
    return IndexJobs(client.app.state.knowledge.database), model.alias


def test_enqueue_deduplicates_worker_persists_result(scope):
    store, alias = prepare(scope)
    client, _, _, _, root, _ = scope
    first = client.post(root + "/index-jobs", headers=ADMIN, json={"model": alias})
    assert first.status_code == 202 and first.json()["status"] == "queued"
    assert (
        client.post(root + "/index-jobs", headers=ADMIN, json={"model": alias}).json()["id"]
        == first.json()["id"]
    )
    assert asyncio.run(run_once(store.database, client.app.state.gateway))
    result = client.get(root + "/index-jobs", headers=ADMIN).json()["data"]
    assert result[0]["status"] == "succeeded"
    assert "claim_token" not in result[0]
    assert (
        client.get(root + "/vector-index", headers=ADMIN, params={"model": alias}).json()["status"]
        == "ready"
    )
    assert not asyncio.run(run_once(store.database, client.app.state.gateway))


def test_old_claim_cannot_publish_and_retry_limit(scope):
    store, alias = prepare(scope)
    client, tenants, app, version, root, _ = scope
    client.post(root + "/index-jobs", headers=ADMIN, json={"model": alias})
    old = store.claim()
    with store.database.write("test") as db:
        db.execute(jobs.update().values(lease_until=0))
    new = store.claim()
    assert new["claim_token"] != old["claim_token"] and new["attempts"] == 2
    with pytest.raises(GatewayError) as error:
        asyncio.run(
            VectorService(store.database, client.app.state.gateway).build(
                tenants[0]["id"],
                app["id"],
                version["id"],
                alias,
                "test",
                "test",
                on_save=lambda db: store.finish(db, old),
            )
        )
    assert error.value.code == "index_lease_lost"
    with store.database.read() as db:
        assert db.execute(select(indexes)).first() is None
    with store.database.write("test") as db:
        db.execute(jobs.update().values(lease_until=0, attempts=3))
    assert store.claim() is None
    assert (
        client.get(root + "/index-jobs", headers=ADMIN).json()["data"][0]["error"]
        == "worker_interrupted"
    )


def test_revoked_model_fails_and_queue_capacity(scope):
    store, alias = prepare(scope)
    client, tenants, app, version, root, _ = scope
    client.post(root + "/index-jobs", headers=ADMIN, json={"model": alias})
    client.app.state.tenants.grant(tenants[0]["id"], alias, False)
    assert asyncio.run(run_once(store.database, client.app.state.gateway))
    assert (
        client.get(root + "/index-jobs", headers=ADMIN).json()["data"][0]["error"]
        == "model_not_allowed"
    )
    for i in range(5):
        store.enqueue(tenants[0]["id"], app["id"], version["id"], str(i), "test", "test")
    with pytest.raises(GatewayError) as error:
        store.enqueue(tenants[0]["id"], app["id"], version["id"], "overflow", "test", "test")
    assert error.value.code == "index_queue_full"
