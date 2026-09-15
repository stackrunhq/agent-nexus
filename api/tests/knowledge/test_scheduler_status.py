from agent_nexus.knowledge.index_jobs import IndexJobs, jobs
from test_ingestion import ADMIN, scope as scope


def test_tenant_queue_metrics_time_boundaries_and_auth(scope, monkeypatch):
    client, tenants, app, version, _, _ = scope
    store = IndexJobs(client.app.state.knowledge.database)
    now = 2_000_000_000
    monkeypatch.setattr("agent_nexus.knowledge.index_jobs.time.time", lambda: now)
    monkeypatch.setenv("NEXUS_INDEX_SCHEDULER", "tenant_round_robin")
    root = f"/api/v1/admin/tenants/{tenants[0]['id']}/index-usage"
    empty = client.get(root, headers=ADMIN).json()["scheduling"]
    assert empty["oldest_queued_age_seconds"] is None and empty["recovery_pending"] == 0
    ids = [
        store.enqueue(tenants[0]["id"], app["id"], version["id"], str(i), "test", "test")["id"]
        for i in range(4)
    ]
    other = store.enqueue(tenants[1]["id"], app["id"], version["id"], "other", "test", "test")
    with store.database.write("test") as db:
        db.execute(jobs.update().where(jobs.c.id == ids[0]).values(created_at=now - 90))
        db.execute(
            jobs.update()
            .where(jobs.c.id == ids[1])
            .values(status="processing", lease_until=now - 15)
        )
        db.execute(
            jobs.update()
            .where(jobs.c.id == ids[2])
            .values(status="processing", lease_until=now + 60)
        )
        db.execute(jobs.update().where(jobs.c.id == ids[3]).values(status="failed", created_at=0))
        db.execute(jobs.update().where(jobs.c.id == other["id"]).values(created_at=1))
    value = client.get(root, headers=ADMIN).json()["scheduling"]
    assert value == {
        "api_strategy": "tenant_round_robin",
        "observed_at": now,
        "queued": 1,
        "processing": 2,
        "recovery_pending": 1,
        "oldest_queued_age_seconds": 90,
        "oldest_recovery_overdue_seconds": 15,
    }
    assert client.get(root).status_code == 401
    assert client.get(root.replace(tenants[0]["id"], "missing"), headers=ADMIN).status_code == 404
    with store.database.write("test") as db:
        db.execute(
            jobs.update().where(jobs.c.tenant_id == tenants[0]["id"]).values(status="succeeded")
        )
    final = client.get(root, headers=ADMIN).json()["scheduling"]
    assert final["queued"] == 0 and final["processing"] == 0
    assert (
        final["oldest_queued_age_seconds"] is None
        and final["oldest_recovery_overdue_seconds"] is None
    )
