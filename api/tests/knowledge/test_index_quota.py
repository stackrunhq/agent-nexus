from agent_nexus.core.errors import GatewayError
from test_ingestion import ADMIN, scope as scope
from test_index_jobs import prepare


def test_sync_and_queue_share_daily_quota(scope, monkeypatch):
    monkeypatch.setenv("NEXUS_INDEX_DAILY_LIMIT", "1")
    _, alias = prepare(scope)
    client, tenants, _, _, root, _ = scope
    assert (
        client.post(root + "/vector-index", headers=ADMIN, json={"model": alias}).status_code == 200
    )
    for path in ("/vector-index", "/index-jobs"):
        response = client.post(root + path, headers=ADMIN, json={"model": alias})
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "index_daily_quota_exceeded"
    usage = client.get(
        f"/api/v1/admin/tenants/{tenants[0]['id']}/index-usage", headers=ADMIN
    ).json()
    assert usage["daily_used"] == 1 and usage["active"] == 0


def test_duplicate_does_not_charge_and_day_rollover(scope, monkeypatch):
    monkeypatch.setenv("NEXUS_INDEX_DAILY_LIMIT", "1")
    store, alias = prepare(scope)
    client, tenants, app, version, root, _ = scope
    monkeypatch.setattr("agent_nexus.knowledge.index_jobs.time.time", lambda: 86401)
    one = store.enqueue(tenants[0]["id"], app["id"], version["id"], alias, "test", "test")
    assert (
        store.enqueue(tenants[0]["id"], app["id"], version["id"], alias, "test", "test")["id"]
        == one["id"]
    )
    assert store.usage(tenants[0]["id"])["daily_used"] == 1
    task = store.claim()
    store.fail(task, "test_failure")
    assert store.usage(tenants[0]["id"])["daily_used"] == 1
    monkeypatch.setattr("agent_nexus.knowledge.index_jobs.time.time", lambda: 172801)
    assert store.usage(tenants[0]["id"])["daily_used"] == 0
    assert (
        store.enqueue(tenants[0]["id"], app["id"], version["id"], alias, "test", "test")["id"]
        != one["id"]
    )


def test_sync_cannot_overlap_queued_task(scope):
    _, alias = prepare(scope)
    client, _, _, _, root, _ = scope
    assert (
        client.post(root + "/index-jobs", headers=ADMIN, json={"model": alias}).status_code == 202
    )
    response = client.post(root + "/vector-index", headers=ADMIN, json={"model": alias})
    assert response.status_code == 409 and response.json()["error"]["code"] == "index_job_active"


def test_concurrent_admissions_do_not_exceed_quota(scope, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setenv("NEXUS_INDEX_DAILY_LIMIT", "2")
    store, _ = prepare(scope)
    _, tenants, app, version, _, _ = scope

    def submit(number):
        try:
            store.enqueue(tenants[0]["id"], app["id"], version["id"], str(number), "test", "test")
            return True
        except GatewayError as exc:
            assert exc.code == "index_daily_quota_exceeded"
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(submit, range(8))) == 2
    assert store.usage(tenants[0]["id"])["daily_used"] == 2
