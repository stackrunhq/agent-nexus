import sqlite3
import pytest
from sqlalchemy import select
from agent_nexus.models.usage import UsageStore, calls
from agent_nexus.core.errors import GatewayError
from agent_nexus.storage.database import Database
from agent_nexus_cli.database import upgrade
from test_ingestion import scope as scope
from test_index_jobs import prepare


def test_batch_validation_rejects_partial_or_invalid_positions(scope):
    store, alias = prepare(scope)
    client, tenants, app, version, _, _ = scope
    task = store.enqueue(tenants[0]["id"], app["id"], version["id"], alias, "test", "r")
    config = client.app.state.gateway.resolve(alias, "embeddings")
    usage = UsageStore(store.database)
    for position in [(None, 0, 1), (0, 0, 1), (1, 1, 16), (1, 128, 1), (1, 112, 17), (True, 0, 1)]:
        with pytest.raises(GatewayError, match="position"):
            usage.start(tenants[0]["id"], config, "embeddings", "r", task["id"], *position)
    with pytest.raises(GatewayError):
        usage.start(tenants[0]["id"], config, "embeddings", "r", None, 1, 0, 1)


def test_0016_upgrade_keeps_batch_unknown(tmp_path):
    path = str(tmp_path / "old.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        for name in ("index_attempt", "index_batch_start", "index_batch_size"):
            db.execute("ALTER TABLE model_calls DROP COLUMN " + name)
        db.execute("INSERT INTO tenants (id,name,enabled,key_hash) VALUES ('t','t',1,'hash')")
        db.execute(
            "INSERT INTO model_calls (id,tenant_id,request_id,index_job_id,model,model_fingerprint,capability,created_at,status) VALUES ('old','t','r','job','m','f','embeddings',1,'failed')"
        )
        db.execute("UPDATE alembic_version SET version_num='0016'")
    upgrade(path)
    database = Database(path)
    with database.read() as db:
        row = db.execute(select(calls)).mappings().one()
        assert (
            row["index_job_id"] == "job"
            and row["index_attempt"] is None
            and row["index_batch_start"] is None
            and row["index_batch_size"] is None
        )
    database.close()
