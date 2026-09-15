from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from agent_nexus.knowledge.index_jobs import IndexJobs, jobs
from agent_nexus.knowledge import index_scheduler
from agent_nexus.storage.database import Database
from agent_nexus_cli.database import upgrade
from test_ingestion import ADMIN, scope as scope


def prepare(scope):
    client, tenants, app, version, _, _ = scope
    store = IndexJobs(client.app.state.knowledge.database)
    root = f"/api/v1/admin/tenants/{tenants[1]['id']}/applications"
    second_app = client.post(root, headers=ADMIN, json={"name": "B", "slug": "b"}).json()
    second_version = client.post(
        root + f"/{second_app['id']}/versions", headers=ADMIN, json={"version": "1"}
    ).json()
    identifiers = []
    for tenant, application, revision, count in (
        (tenants[0], app, version, 3),
        (tenants[1], second_app, second_version, 2),
    ):
        for i in range(count):
            task = store.enqueue(
                tenant["id"], application["id"], revision["id"], f"m{i}", "test", "test"
            )
            identifiers.append(task["id"])
            with store.database.write("test") as db:
                db.execute(
                    jobs.update().where(jobs.c.id == task["id"]).values(created_at=len(identifiers))
                )
    return store, tenants, identifiers


def test_round_robin_persists_across_store_instances(scope, monkeypatch):
    store, tenants, identifiers = prepare(scope)
    monkeypatch.setenv("NEXUS_INDEX_SCHEDULER", "tenant_round_robin")
    claimed = [IndexJobs(store.database).claim() for _ in identifiers]
    first, second = sorted(tenant["id"] for tenant in tenants)
    expected = [first, second, first, second, tenants[0]["id"]]
    assert [task["tenant_id"] for task in claimed] == expected
    assert len({task["id"] for task in claimed}) == 5
    assert store.claim() is None


def test_default_fifo_and_invalid_setting(scope, monkeypatch):
    store, _, identifiers = prepare(scope)
    monkeypatch.delenv("NEXUS_INDEX_SCHEDULER", raising=False)
    assert [store.claim()["id"] for _ in identifiers] == identifiers
    monkeypatch.setenv("NEXUS_INDEX_SCHEDULER", "invalid")
    with pytest.raises(RuntimeError, match="NEXUS_INDEX_SCHEDULER"):
        store.claim()


def test_concurrent_claim_and_rollback(scope, monkeypatch):
    store, _, identifiers = prepare(scope)
    monkeypatch.setenv("NEXUS_INDEX_SCHEDULER", "tenant_round_robin")
    original = index_scheduler.advance

    def fail(db, tenant):
        original(db, tenant)
        raise RuntimeError("rollback")

    monkeypatch.setattr(index_scheduler, "advance", fail)
    with pytest.raises(RuntimeError, match="rollback"):
        store.claim()
    with store.database.read() as db:
        assert db.execute(index_scheduler.state.select()).first() is None
        assert all(
            row[0] == "queued" for row in db.execute(jobs.select().with_only_columns(jobs.c.status))
        )
    monkeypatch.setattr(index_scheduler, "advance", original)
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = list(pool.map(lambda _: store.claim(), range(5)))
    assert {task["id"] for task in tasks} == set(identifiers)


def test_0012_upgrade_required(tmp_path):
    path = str(tmp_path / "old.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE knowledge_index_scheduler")
        db.execute("UPDATE alembic_version SET version_num='0012'")
    with pytest.raises(RuntimeError):
        Database(path)
    upgrade(path)
    database = Database(path)
    assert database.check()["revision"] == "0015"
    database.close()
