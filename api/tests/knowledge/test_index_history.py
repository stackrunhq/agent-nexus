from agent_nexus.knowledge.index_jobs import IndexJobs, jobs
from test_ingestion import ADMIN, scope as scope


def test_cursor_survives_insert_and_deleted_anchor(scope):
    client, tenants, app, version, _, _ = scope
    store = IndexJobs(client.app.state.knowledge.database)
    tenant = tenants[0]["id"]
    for _ in range(4):
        task = store.enqueue(tenant, app["id"], version["id"], "model", "test", "test")
        with store.database.write("test") as db:
            db.execute(
                jobs.update().where(jobs.c.id == task["id"]).values(status="failed", created_at=100)
            )
    root = f"/api/v1/admin/tenants/{tenant}/applications/{app['id']}/versions/{version['id']}/index-jobs"
    all_ids = [row["id"] for row in client.get(root, headers=ADMIN).json()["data"]]
    first = client.get(root, headers=ADMIN, params={"model": "model", "limit": 2}).json()
    store.enqueue(tenant, app["id"], version["id"], "model", "test", "test")
    with store.database.write("test") as db:
        db.execute(jobs.delete().where(jobs.c.id == first["data"][-1]["id"]))
    second = client.get(
        root, headers=ADMIN, params={"model": "model", "limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert [row["id"] for row in second["data"]] == all_ids[2:]
    assert second["next_cursor"] is None
    for extra in [{"model": "other"}, {"offset": 1}, {"cursor": "bad"}, {"status": "failed"}]:
        params = {"model": "model", "cursor": first["next_cursor"], **extra}
        assert client.get(root, headers=ADMIN, params=params).status_code == 422


def test_history_indexes_migrate(tmp_path):
    import sqlite3
    from sqlalchemy import inspect
    from agent_nexus_cli.database import upgrade
    from agent_nexus.storage.database import Database

    path = str(tmp_path / "history.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP INDEX ix_index_history_scope")
        db.execute("DROP INDEX ix_index_history_model")
        db.execute("UPDATE alembic_version SET version_num='0014'")
    upgrade(path)
    database = Database(path)
    with database.read() as db:
        indexes = {entry["name"] for entry in inspect(db).get_indexes("knowledge_index_jobs")}
        assert {"ix_index_history_scope", "ix_index_history_model"} <= indexes
    database.close()


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
