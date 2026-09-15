import asyncio
import json
import sqlite3

import httpx
import pytest

from agent_nexus.core.errors import GatewayError
from agent_nexus.knowledge.index_checkpoints import IndexCheckpoint, checkpoints, batches
from agent_nexus.knowledge.index_jobs import IndexJobs, jobs, run_once
from agent_nexus.knowledge.jobs import run_once as parse_once
from agent_nexus.knowledge.vectors import indexes
from agent_nexus.storage.database import Database
from agent_nexus_cli.database import upgrade
from test_ingestion import ADMIN, upload, scope as scope
from test_search import publish_catalog
from test_vectors import configure, provider


@pytest.mark.parametrize("change", ["none", "content", "model"])
def test_interrupted_worker_resumes_only_matching_revision(scope, monkeypatch, change):
    client, tenants, app, version, root, _ = scope
    large = upload(client, root, "large.txt", ("password settings " * 1800).encode()).json()
    publish_catalog(client, root)
    while parse_once(client.app.state.knowledge):
        pass
    client.patch(root + "/documents/" + large["id"], headers=ADMIN, json={"published": True})
    model = configure(client)
    client.app.state.tenants.grant(tenants[0]["id"], model.alias, True)
    calls = []

    def upstream(request):
        calls.append(len(json.loads(request.content)["input"]))
        return provider(request)

    client.app.state.gateway.client._transport = httpx.MockTransport(upstream)
    previous = client.post(root + "/vector-index", headers=ADMIN, json={"model": model.alias})
    assert previous.status_code == 200 and previous.json()["chunks"] > 16
    database = client.app.state.knowledge.database
    with database.read() as db:
        old = dict(db.execute(indexes.select()).mappings().one())
    calls.clear()
    task = client.post(root + "/index-jobs", headers=ADMIN, json={"model": model.alias}).json()
    save = IndexCheckpoint.save

    def interrupted(self, *args, **kwargs):
        save(self, *args, **kwargs)
        raise asyncio.CancelledError()

    monkeypatch.setattr(IndexCheckpoint, "save", interrupted)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_once(database, client.app.state.gateway))
    assert calls == [16]
    with database.read() as db:
        saved = dict(db.execute(batches.select()).mappings().one())
        assert len(json.loads(saved["payload"])) == 16
        assert dict(db.execute(indexes.select()).mappings().one()) == old
    monkeypatch.setattr(IndexCheckpoint, "save", save)
    if change == "content":
        client.patch(root + "/documents/" + large["id"], headers=ADMIN, json={"published": False})
    elif change == "model":
        client.app.state.gateway.store.put(
            model.model_copy(update={"model": "new-model"}),
            expected_etag=client.app.state.gateway.store.etag(model),
        )
    with database.write("test") as db:
        db.execute(jobs.update().where(jobs.c.id == task["id"]).values(lease_until=0))
    calls.clear()
    assert asyncio.run(run_once(database, client.app.state.gateway))
    result = client.get(root + "/vector-index", headers=ADMIN, params={"model": model.alias}).json()
    assert result["status"] == "ready"
    assert sum(calls) == result["chunks"] - (16 if change == "none" else 0)
    with database.read() as db:
        assert db.execute(checkpoints.select()).first() is None
        row = db.execute(jobs.select().where(jobs.c.id == task["id"])).mappings().one()
        assert row["status"] == "succeeded" and row["attempts"] == 2


def test_reclaimed_worker_cannot_change_checkpoint(scope):
    client, tenants, app, version, _, _ = scope
    store = IndexJobs(client.app.state.knowledge.database)
    store.enqueue(tenants[0]["id"], app["id"], version["id"], "model", "test", "test")
    old = store.claim()
    checkpoint = IndexCheckpoint(store.database, old)
    checkpoint.save("content", "model", [[1, 0]], 2)
    with store.database.write("test") as db:
        db.execute(jobs.update().values(lease_until=0))
    current = store.claim()
    for action in (
        lambda: checkpoint.load("content", "model"),
        lambda: checkpoint.save("changed", "model", [[0, 1]], 2),
    ):
        with pytest.raises(GatewayError, match="lease"):
            action()
    assert IndexCheckpoint(store.database, current).load("content", "model") == ([[1, 0]], 2)
    store.fail(current, "test_failure")
    with store.database.read() as db:
        assert db.execute(checkpoints.select()).first() is None


def test_0010_requires_explicit_upgrade(tmp_path):
    path = str(tmp_path / "old.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE knowledge_index_checkpoints")
        db.execute("UPDATE alembic_version SET version_num='0010'")
    with pytest.raises(RuntimeError):
        Database(path)
    upgrade(path)
    database = Database(path)
    assert database.check()["revision"] == "0015"
    database.close()
