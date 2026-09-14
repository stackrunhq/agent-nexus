import sqlite3
import pytest
from sqlalchemy import select
from agent_nexus.knowledge.vectors import VectorService, index_metadata
from agent_nexus.storage.database import Database
from agent_nexus_cli.database import upgrade
from test_ingestion import ADMIN, scope as scope
from test_index_jobs import prepare


def test_status_uses_metadata_and_legacy_fallback(scope, monkeypatch):
    store, alias = prepare(scope)
    client, tenants, app, version, root, _ = scope
    assert (
        client.post(root + "/vector-index", headers=ADMIN, json={"model": alias}).status_code == 200
    )
    service = VectorService(store.database, client.app.state.gateway)
    expected = service.load_metadata(version["id"], alias)
    with monkeypatch.context() as patch:
        patch.setattr(
            service, "load", lambda *args: pytest.fail("Status must not load vector JSON")
        )
        assert (
            service.describe(tenants[0]["id"], app["id"], version["id"], alias)["chunks"]
            == expected["chunks"]
        )
    with store.database.write("test") as db:
        db.execute(index_metadata.delete())
    assert service.load_metadata(version["id"], alias) == expected


def test_0009_backfills_existing_snapshots(scope):
    store, alias = prepare(scope)
    client, _, _, version, root, path = scope
    assert (
        client.post(root + "/vector-index", headers=ADMIN, json={"model": alias}).status_code == 200
    )
    service = VectorService(store.database, client.app.state.gateway)
    expected = service.load_metadata(version["id"], alias)
    upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE knowledge_vector_metadata")
        db.execute("UPDATE alembic_version SET version_num='0009'")
    with pytest.raises(RuntimeError):
        Database(path)
    upgrade(path)
    with store.database.read() as db:
        assert dict(db.execute(select(index_metadata)).mappings().one()) == expected
