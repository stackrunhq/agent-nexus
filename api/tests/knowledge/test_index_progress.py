import asyncio
import sqlite3

import httpx
import pytest
from sqlalchemy import event

from agent_nexus.core.errors import GatewayError
from agent_nexus.knowledge.content_revisions import bump, current
from agent_nexus.knowledge.index_checkpoints import IndexCheckpoint, batches, checkpoints
from agent_nexus.knowledge.index_jobs import IndexJobs, run_once
from agent_nexus.knowledge.vectors import VectorService
from agent_nexus_cli.database import upgrade
from test_ingestion import ADMIN, upload, scope as scope
from test_search import publish_catalog
from test_vectors import configure, provider


def test_content_revision_publication_noop_and_rollback(scope):
    client, tenants, app, version, root, _ = scope
    database = client.app.state.knowledge.database

    def revision():
        with database.read() as db:
            return current(db, version["id"])

    assert revision() == 0
    first, _, _ = publish_catalog(client, root)
    before = revision()
    assert before == 5  # Three parse completions and two publications.
    path = root + "/documents/" + first["id"]
    assert client.patch(path, headers=ADMIN, json={"published": True}).status_code == 200
    assert revision() == before
    client.patch(path, headers=ADMIN, json={"published": False})
    client.patch(path, headers=ADMIN, json={"published": True})
    assert revision() == before + 2
    with pytest.raises(RuntimeError), database.write("test") as db:
        bump(db, version["id"])
        raise RuntimeError("rollback")
    assert revision() == before + 2


def test_batches_append_without_rewriting_prefix_and_reject_gaps(scope):
    client, tenants, app, version, _, _ = scope
    store = IndexJobs(client.app.state.knowledge.database)
    store.enqueue(tenants[0]["id"], app["id"], version["id"], "model", "test", "test")
    task = store.claim()
    checkpoint = IndexCheckpoint(store.database, task)
    checkpoint.save("content", "model", [[1, 0]] * 16, 2)
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(store.database.engine, "before_cursor_execute", capture)
    try:
        checkpoint.save("content", "model", [[0, 1]] * 3, 2, start=16)
    finally:
        event.remove(store.database.engine, "before_cursor_execute", capture)
    assert not any(
        "delete from knowledge_index" in s or "update knowledge_index_batches" in s
        for s in statements
    )
    assert checkpoint.load("content", "model") == ([[1, 0]] * 16 + [[0, 1]] * 3, 2)
    with pytest.raises(GatewayError):
        checkpoint.save("content", "model", [[1, 0]], 2, start=20)
    with store.database.read() as db:
        assert len(db.execute(batches.select()).all()) == 2
    store.fail(task, "test_failure")
    with store.database.read() as db:
        assert db.execute(batches.select()).first() is None
        assert db.execute(checkpoints.select()).first() is None


def test_multi_batch_worker_only_reads_full_snapshot_at_boundaries(scope, monkeypatch):
    client, tenants, _, _, root, _ = scope
    large = upload(client, root, "large.txt", ("password settings " * 1800).encode()).json()
    publish_catalog(client, root)
    client.patch(root + "/documents/" + large["id"], headers=ADMIN, json={"published": True})
    model = configure(client)
    client.app.state.tenants.grant(tenants[0]["id"], model.alias, True)
    client.app.state.gateway.client._transport = httpx.MockTransport(provider)
    client.post(root + "/index-jobs", headers=ADMIN, json={"model": model.alias})
    calls = []
    original = VectorService.snapshot

    def snapshot(self, *args):
        calls.append(1)
        return original(self, *args)

    monkeypatch.setattr(VectorService, "snapshot", snapshot)
    assert asyncio.run(run_once(client.app.state.knowledge.database, client.app.state.gateway))
    assert len(calls) == 2
    result = client.get(root + "/vector-index", headers=ADMIN, params={"model": model.alias})
    assert result.json()["status"] == "ready" and result.json()["chunks"] > 16


def test_0011_upgrade_discards_only_old_progress(scope):
    client, tenants, app, version, _, path = scope
    upgrade(path)
    store = IndexJobs(client.app.state.knowledge.database)
    store.enqueue(tenants[0]["id"], app["id"], version["id"], "model", "test", "test")
    task = store.claim()
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE knowledge_index_batches")
        db.execute("DROP TABLE knowledge_content_revisions")
        db.execute(
            "INSERT INTO knowledge_index_checkpoints VALUES (?, ?, ?, ?, ?)",
            (task["id"], "content", "model", 2, "[[1,0]]"),
        )
        db.execute("UPDATE alembic_version SET version_num='0011'")
    upgrade(path)
    with store.database.read() as db:
        assert db.execute(checkpoints.select()).first() is None
        assert db.execute(batches.select()).first() is None
    assert IndexCheckpoint(store.database, task).load("content", "model") == ([], None)
