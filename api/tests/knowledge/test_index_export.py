import os
import json
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
    response = client.get(path, headers=ADMIN)
    result = response.json()
    events_path = root.split("/versions/")[0] + "/events"
    events = client.get(events_path, headers=ADMIN).json()["data"]
    event = events[0]
    assert event["actor"] == "platform_admin"
    assert event["request_id"] == response.headers["X-Request-ID"]
    assert event["version_id"] == version["id"]
    payload = json.loads(event["action"].split(":", 1)[1])
    assert payload["resource"] == result["resource"]
    assert payload["filters"] == result["filters"]
    assert payload["export"] == result["export"]
    assert payload["outcome"] == "generated"
    assert "secret-marker" not in str(event)
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
    exports = [
        e
        for e in client.get(events_path, headers=ADMIN).json()["data"]
        if e["action"].startswith("index_calls_exported:")
    ]
    assert len(exports) == 3
    audit_path = root + "/index-export-events"
    page = client.get(audit_path, headers=ADMIN, params={"limit": 2}).json()
    assert len(page["data"]) == 2 and page["next_cursor"]
    assert page["data"][0]["export"]["returned"] == 0
    assert page["data"][1]["filters"]["call_error"] == ""
    selected = client.get(
        audit_path,
        headers=ADMIN,
        params={"job_id": task["id"], "actor": "platform_admin", "limit": 1},
    ).json()
    assert len(selected["data"]) == 1 and selected["next_cursor"]
    assert selected["filters"]["job_id"] == task["id"]
    assert client.get(audit_path, headers=ADMIN, params={"actor": "platform"}).json()["data"] == []
    assert client.get(audit_path, headers=ADMIN, params={"job_id": "missing"}).json()["data"] == []
    assert client.get(audit_path, headers=ADMIN, params={"actor": ""}).status_code == 422
    older = client.get(audit_path, headers=ADMIN, params={"before": page["next_cursor"]}).json()
    assert len(older["data"]) == 1 and older["next_cursor"] is None
    assert older["data"][0]["export"]["truncated"] is True
    assert "action" not in older["data"][0]
    assert client.get(audit_path).status_code == 401
    assert client.get(audit_path, headers=ADMIN, params={"limit": 101}).status_code == 422
    assert (
        client.get(
            audit_path.replace(tenants[0]["id"], tenants[1]["id"]), headers=ADMIN
        ).status_code
        == 404
    )
    with database.write("test") as db:
        from agent_nexus.applications.store import ApplicationStore

        ApplicationStore.record(
            db, app["id"], "actor", "bad-record", "index_calls_exported:{bad", version["id"]
        )
    broken = client.get(audit_path, headers=ADMIN).json()["data"][0]
    assert broken["readable"] is False and "filters" not in broken
    assert json.loads(exports[1]["action"].split(":", 1)[1])["filters"]["call_error"] == ""
    assert client.get(events_path).status_code == 401
    assert (
        client.get(
            events_path.replace(tenants[0]["id"], tenants[1]["id"]), headers=ADMIN
        ).status_code
        == 404
    )


def test_audit_task_scan_continues_after_empty_segment(scope):
    client, tenants, app, version, root, _ = scope
    database = client.app.state.knowledge.database
    task = IndexJobs(database).enqueue(
        tenants[0]["id"], app["id"], version["id"], "local", "actor", "req"
    )
    client.get(root + "/index-jobs/" + task["id"] + "/export", headers=ADMIN)
    with database.write("test") as db:
        db.execute(
            metadata.tables["application_events"].insert(),
            [
                dict(
                    application_id=app["id"],
                    version_id=version["id"],
                    actor="platform_admin",
                    request_id="bad",
                    action="index_calls_exported:{bad",
                    created_at=1,
                )
                for _ in range(1001)
            ],
        )
    path = root + "/index-export-events"
    first = client.get(path, headers=ADMIN, params={"job_id": task["id"]}).json()
    assert first["data"] == [] and first["scanned"] == 1000 and first["next_cursor"]
    second = client.get(
        path, headers=ADMIN, params={"job_id": task["id"], "before": first["next_cursor"]}
    ).json()
    assert len(second["data"]) == 1 and second["next_cursor"] is None
    assert second["data"][0]["resource"]["job_id"] == task["id"]


def test_export_audit_failure_prevents_success(scope, monkeypatch):
    from agent_nexus.applications.store import ApplicationStore
    from sqlalchemy.exc import OperationalError

    client, tenants, app, version, root, _ = scope
    database = client.app.state.knowledge.database
    task = IndexJobs(database).enqueue(
        tenants[0]["id"], app["id"], version["id"], "local", "actor", "req"
    )
    original = ApplicationStore.record

    def fail(db, *args):
        original(db, *args)
        raise OperationalError("audit unavailable", {}, Exception("failure"))

    monkeypatch.setattr(ApplicationStore, "record", staticmethod(fail))
    response = client.get(root + "/index-jobs/" + task["id"] + "/export", headers=ADMIN)
    assert response.status_code >= 500
    with database.read() as db:
        actions = db.execute(select(metadata.tables["application_events"].c.action)).scalars().all()
    assert not any(action.startswith("index_calls_exported:") for action in actions)


@pytest.mark.skipif(not os.getenv("NEXUS_TEST_POSTGRES_URL"), reason="Requires test PostgreSQL")
def test_export_postgres(scope):
    from agent_nexus_cli.postgres_pipeline import disposable_database
    from agent_nexus_cli.database import upgrade, import_sqlite
    from agent_nexus.storage.database import Database
    from agent_nexus.knowledge.index_export import export, record_export

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
            record_export(database, filtered, "pg-actor", "pg-export-request")
            from agent_nexus.applications.store import ApplicationStore

            event = ApplicationStore(database).events(task["tenant_id"], task["app_id"])[0]
            assert event["actor"] == "pg-actor" and event["request_id"] == "pg-export-request"
            assert json.loads(event["action"].split(":", 1)[1])["export"] == filtered["export"]
            from agent_nexus.knowledge.export_audit import list_exports

            page = list_exports(
                database, task["tenant_id"], task["app_id"], task["version_id"], limit=1
            )
            assert page["data"][0]["actor"] == "pg-actor" and page["next_cursor"]
            selected = list_exports(
                database,
                task["tenant_id"],
                task["app_id"],
                task["version_id"],
                job_id=task["id"],
                actor="pg-actor",
            )
            assert len(selected["data"]) == 1 and selected["next_cursor"] is None
        finally:
            database.close()
