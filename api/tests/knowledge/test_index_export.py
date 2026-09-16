import os
import pytest
from sqlalchemy import select
from agent_nexus.knowledge.index_jobs import IndexJobs, jobs
from agent_nexus.storage.database import metadata
from test_ingestion import ADMIN, scope as scope


def test_export_limit_filters_metadata_and_scope(scope):
    client, tenants, app, version, root, _ = scope
    database = client.app.state.knowledge.database
    task = IndexJobs(database).enqueue(
        tenants[0]["id"], app["id"], version["id"], "local", "actor", "req"
    )
    with database.write("test") as db:
        db.execute(
            metadata.tables["model_calls"].insert(),
            [
                dict(
                    id=str(i),
                    tenant_id=tenants[0]["id"],
                    request_id="req",
                    index_job_id=task["id"],
                    index_attempt=1,
                    model="local",
                    model_fingerprint="secret-marker",
                    capability="embeddings",
                    status="failed",
                    error="provider_timeout" if i else None,
                    created_at=i,
                )
                for i in range(1001)
            ],
        )
    path = root + "/index-jobs/" + task["id"] + "/export"
    result = client.get(path, headers=ADMIN).json()
    assert result["export"] == {"limit": 1000, "returned": 1000, "truncated": True, "starts_at": 0}
    assert result["summary"]["attempts"][0]["calls"] == 1001
    assert result["resource"]["job_id"] == task["id"]
    assert result["calls"]["data"][0]["input_tokens"] is None
    assert "secret-marker" not in str(result) and "claim_token" not in result["task"]
    filtered = client.get(path, headers=ADMIN, params={"attempt": "1", "call_error": ""}).json()
    assert filtered["filters"] == {"attempt": "1", "call_status": None, "call_error": ""}
    assert filtered["export"]["returned"] == 1 and not filtered["export"]["truncated"]
    assert filtered["summary"] == result["summary"]
    assert (
        client.get(path, headers=ADMIN, params={"call_error": "missing"}).json()["export"][
            "returned"
        ]
        == 0
    )
    assert client.get(path).status_code == 401
    assert (
        client.get(path.replace(tenants[0]["id"], tenants[1]["id"]), headers=ADMIN).status_code
        == 404
    )
    assert client.get(path, headers=ADMIN, params={"attempt": "4"}).status_code == 422


@pytest.mark.skipif(not os.getenv("NEXUS_TEST_POSTGRES_URL"), reason="Requires test PostgreSQL")
def test_export_postgres(scope):
    from agent_nexus_cli.postgres_pipeline import disposable_database
    from agent_nexus_cli.database import upgrade, import_sqlite
    from agent_nexus.storage.database import Database
    from agent_nexus.knowledge.index_export import export

    test_export_limit_filters_metadata_and_scope(scope)
    with disposable_database(os.environ["NEXUS_TEST_POSTGRES_URL"]) as url:
        upgrade(url)
        import_sqlite(scope[5], url)
        database = Database(url)
        try:
            with database.read() as db:
                task = db.execute(select(jobs)).mappings().one()
            result = export(
                database, task["tenant_id"], task["app_id"], task["version_id"], task["id"]
            )
            assert result["export"]["truncated"] and len(result["calls"]["data"]) == 1000
            filtered = export(
                database,
                task["tenant_id"],
                task["app_id"],
                task["version_id"],
                task["id"],
                call_error="",
            )
            assert filtered["export"]["returned"] == 1 and filtered["summary"] == result["summary"]
        finally:
            database.close()
