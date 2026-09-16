import asyncio
import sqlite3

import pytest

from agent_nexus.knowledge import worker_presence as presence
from agent_nexus_cli.worker import index_loop
from agent_nexus_cli.database import upgrade
from agent_nexus.storage.database import Database
from test_ingestion import scope as scope


def test_presence_expiry_mismatch_and_cleanup(scope, monkeypatch):
    database = scope[0].app.state.knowledge.database
    monkeypatch.setattr(presence.time, "time", lambda: 100000)
    monkeypatch.setenv("NEXUS_INDEX_SCHEDULER", "fifo")
    presence.touch(database, "one")
    monkeypatch.setenv("NEXUS_INDEX_SCHEDULER", "tenant_round_robin")
    presence.touch(database, "two")
    with database.read() as db:
        assert presence.summary(db, 100029, "fifo") == {
            "recent": 2,
            "stale": 0,
            "mismatched": 1,
            "ttl_seconds": 30,
            "status": "mismatch",
        }
        assert presence.summary(db, 100030, "fifo")["status"] == "unknown"
        assert presence.summary(db, 99999, "fifo")["recent"] == 0
    presence.remove(database, "two")
    with database.read() as db:
        assert presence.summary(db, 100000, "fifo")["status"] == "matching"
    monkeypatch.setattr(presence.time, "time", lambda: 200000)
    presence.touch(database, "new")
    with database.read() as db:
        assert db.execute(presence.workers.select()).mappings().one()["id"] == "new"


@pytest.mark.parametrize("fail", [False, True])
def test_worker_pulses_during_task_and_removes_on_exit(scope, monkeypatch, fail):
    database = scope[0].app.state.knowledge.database
    monkeypatch.setattr(presence, "INTERVAL", 0.01)
    original = presence.touch
    calls = []

    def touch(*args):
        calls.append(1)
        if fail and len(calls) > 1:
            raise RuntimeError("heartbeat failed")
        original(*args)

    monkeypatch.setattr(presence, "touch", touch)

    async def work(*args):
        await asyncio.sleep(0.1)
        return False

    monkeypatch.setattr("agent_nexus.knowledge.index_jobs.run_once", work)
    if fail:
        with pytest.raises(RuntimeError, match="heartbeat failed"):
            asyncio.run(index_loop(database, True))
    else:
        asyncio.run(index_loop(database, True))
    assert len(calls) >= 2
    with database.read() as db:
        assert db.execute(presence.workers.select()).first() is None


def test_0013_upgrade_required(tmp_path):
    path = str(tmp_path / "old.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE knowledge_index_workers")
        db.execute("UPDATE alembic_version SET version_num='0013'")
    with pytest.raises(RuntimeError):
        Database(path)
    upgrade(path)
    database = Database(path)
    assert database.check()["revision"] == "0017"
    database.close()
