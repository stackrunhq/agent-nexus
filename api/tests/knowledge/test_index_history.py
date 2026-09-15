from agent_nexus.knowledge.index_jobs import IndexJobs, jobs
from test_ingestion import ADMIN, scope as scope


def test_history_filters_before_paging_and_validates_scope(scope):
    client, tenants, app, version, _, _ = scope
    store = IndexJobs(client.app.state.knowledge.database)
    tenant = tenants[0]["id"]
    for i in range(25):
        task = store.enqueue(
            tenant, app["id"], version["id"], "old" if i < 3 else "new", "test", "test"
        )
        with store.database.write("test") as db:
            db.execute(
                jobs.update()
                .where(jobs.c.id == task["id"])
                .values(status="failed", error=None if i == 0 else "provider_timeout", created_at=i)
            )
    root = f"/api/v1/admin/tenants/{tenant}/applications/{app['id']}/versions/{version['id']}/index-jobs"
    result = client.get(root, headers=ADMIN).json()
    assert len(result["data"]) == 20 and result["has_more"]
    result = client.get(
        root,
        headers=ADMIN,
        params={"model": "old", "status": "failed", "error": "provider_timeout", "limit": 1},
    ).json()
    assert len(result["data"]) == 1 and result["has_more"]
    next_page = client.get(
        root,
        headers=ADMIN,
        params={"model": "old", "error": "provider_timeout", "limit": 1, "offset": 1},
    ).json()
    assert not next_page["has_more"] and next_page["data"][0]["id"] != result["data"][0]["id"]
    assert len(client.get(root, headers=ADMIN, params={"error": ""}).json()["data"]) == 1
    assert (
        client.get(
            root, headers=ADMIN, params={"status": "succeeded", "error": "provider_timeout"}
        ).json()["data"]
        == []
    )
    for params in [{"limit": 101}, {"offset": -1}, {"status": "invalid"}, {"model": ""}]:
        assert client.get(root, headers=ADMIN, params=params).status_code == 422
    assert client.get(root).status_code == 401
    assert client.get(root.replace(tenant, tenants[1]["id"]), headers=ADMIN).status_code == 404
