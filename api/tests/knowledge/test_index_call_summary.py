import os
import pytest
from sqlalchemy import select
from agent_nexus.knowledge.index_jobs import IndexJobs, jobs
from agent_nexus.storage.database import metadata
from test_ingestion import ADMIN, scope as scope


def test_attempt_summary_is_unpaged_and_excludes_unconfirmed_and_other_scope(scope):
    client, tenants, app, version, root, _ = scope
    database = client.app.state.knowledge.database
    task = IndexJobs(database).enqueue(
        tenants[0]["id"], app["id"], version["id"], "local", "actor", "same"
    )
    path = root + "/index-jobs/" + task["id"]
    assert client.get(path, headers=ADMIN).json()["summary"]["attempts"] == []
    calls = metadata.tables["model_calls"]
    with database.write("test") as db:
        for i in range(26):
            db.execute(
                calls.insert().values(
                    id=str(i),
                    tenant_id=tenants[1]["id"] if i == 23 else tenants[0]["id"],
                    request_id="same",
                    index_job_id=None if i == 22 else "different-task" if i == 25 else task["id"],
                    index_attempt=1 if i < 20 else 2 if i == 20 else None,
                    model="other" if i == 24 else "local",
                    model_fingerprint="test",
                    capability="embeddings",
                    created_at=i,
                    status="succeeded" if i == 0 else "failed" if i == 20 else "pending",
                    input_tokens=0 if i == 0 else 7 if i == 20 else None,
                    output_tokens=0 if i == 0 else None,
                    elapsed_ms=0 if i == 0 else 12 if i == 20 else None,
                )
            )
    first = client.get(path, headers=ADMIN, params={"limit": 1}).json()
    second = client.get(path, headers=ADMIN, params={"limit": 1, "offset": 20}).json()
    assert first["summary"] == second["summary"]
    summary = first["summary"]
    filtered = client.get(
        path, headers=ADMIN, params={"attempt": "2", "call_status": "failed", "limit": 1}
    ).json()
    assert [row["id"] for row in filtered["calls"]["data"]] == ["20"]
    assert filtered["summary"] == summary
    unknown_page = client.get(path, headers=ADMIN, params={"attempt": "unknown"}).json()
    assert [row["id"] for row in unknown_page["calls"]["data"]] == ["21"]
    assert client.get(path, headers=ADMIN, params={"attempt": "3"}).json()["calls"]["data"] == []
    pending = client.get(
        path,
        headers=ADMIN,
        params={"attempt": "1", "call_status": "pending", "offset": 18, "limit": 1},
    ).json()
    assert len(pending["calls"]["data"]) == 1 and not pending["calls"]["has_more"]
    for params in [
        {"attempt": "0"},
        {"attempt": "4"},
        {"attempt": "banana"},
        {"call_status": "queued"},
    ]:
        assert client.get(path, headers=ADMIN, params=params).status_code == 422
    assert summary["unconfirmed_request_calls"] == 1
    one, two, unknown = summary["attempts"]
    assert (
        one["attempt"] == 1
        and one["calls"] == 20
        and one["succeeded"] == 1
        and one["pending"] == 19
        and one["failed"] == 0
    )

    assert one["known_input_tokens"] == 0 and one["unknown_input_tokens_calls"] == 19
    assert one["known_elapsed_ms"] == 0 and one["unknown_elapsed_ms_calls"] == 19
    assert two["attempt"] == 2 and two["calls"] == 1 and two["failed"] == 1
    assert (
        two["known_input_tokens"] == 7
        and two["known_output_tokens"] is None
        and two["unknown_output_tokens_calls"] == 1
    )
    assert (
        unknown["attempt"] is None
        and unknown["calls"] == 1
        and unknown["known_input_tokens"] is None
    )


@pytest.mark.skipif(not os.getenv("NEXUS_TEST_POSTGRES_URL"), reason="Requires test PostgreSQL")
def test_attempt_summary_postgres(scope):
    from agent_nexus_cli.postgres_pipeline import disposable_database
    from agent_nexus_cli.database import upgrade, import_sqlite
    from agent_nexus.storage.database import Database
    from agent_nexus.knowledge.index_details import detail

    test_attempt_summary_is_unpaged_and_excludes_unconfirmed_and_other_scope(scope)
    with disposable_database(os.environ["NEXUS_TEST_POSTGRES_URL"]) as url:
        upgrade(url)
        import_sqlite(scope[5], url)
        database = Database(url)
        try:
            with database.read() as db:
                task = db.execute(select(jobs)).mappings().one()
            result = detail(
                database,
                task["tenant_id"],
                task["app_id"],
                task["version_id"],
                task["id"],
                offset=20,
                limit=1,
            )["summary"]
            assert [row["calls"] for row in result["attempts"]] == [20, 1, 1]
            assert result["attempts"][0]["known_input_tokens"] == 0
            assert result["attempts"][-1]["attempt"] is None
            assert result["unconfirmed_request_calls"] == 1
            filtered = detail(
                database,
                task["tenant_id"],
                task["app_id"],
                task["version_id"],
                task["id"],
                attempt="2",
                call_status="failed",
            )
            assert [row["id"] for row in filtered["calls"]["data"]] == ["20"]
            assert filtered["summary"] == result
        finally:
            database.close()
