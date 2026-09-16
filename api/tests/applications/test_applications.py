from concurrent.futures import ThreadPoolExecutor
import sqlite3
import pytest
from fastapi.testclient import TestClient
from agent_nexus.app import Settings, create_app
from agent_nexus.applications.schemas import VersionCreate
from agent_nexus.storage.database import Database
from agent_nexus_cli.database import upgrade, import_sqlite

ADMIN = {"Authorization": "Bearer " + "a" * 32}


@pytest.fixture
def setup(tmp_path):
    path = str(tmp_path / "test.db")
    with TestClient(
        create_app(Settings("a" * 32, "b" * 32, path, {"localhost"}, auth_mode="tenant"))
    ) as client:
        tenants = [
            client.post("/api/v1/admin/tenants", headers=ADMIN, json={"name": name}).json()
            for name in ["A", "B"]
        ]
        root = f"/api/v1/admin/tenants/{tenants[0]['id']}/applications"
        app = client.post(root, headers=ADMIN, json={"slug": "erp", "name": "ERP"}).json()
        yield client, tenants, root, app, path


def test_versions_lifecycle_isolation_and_audit(setup):
    client, tenants, root, app, _ = setup
    versions = f"{root}/{app['id']}/versions"
    version = client.post(
        versions, headers=ADMIN, json={"version": "1.0", "notes": "manual scope"}
    ).json()
    member = {"Authorization": "Bearer " + tenants[0]["api_key"]}
    other = {"Authorization": "Bearer " + tenants[1]["api_key"]}
    public = f"/api/v1/applications/{app['id']}/versions"
    assert client.get(public, headers=member).json()["data"] == []
    assert client.get(public, headers=other).status_code == 404
    assert client.get(root, headers=member).status_code == 401
    bad = f"/api/v1/admin/tenants/{tenants[1]['id']}/applications/{app['id']}/versions"
    assert client.get(bad, headers=ADMIN).status_code == 404
    assert (
        client.patch(
            versions + "/" + version["id"], headers=ADMIN, json={"status": "retired"}
        ).status_code
        == 409
    )
    for _ in range(2):
        assert (
            client.patch(
                versions + "/" + version["id"], headers=ADMIN, json={"status": "published"}
            ).status_code
            == 200
        )
    assert client.get(public, headers=member).json()["data"][0]["id"] == version["id"]
    events = client.get(f"{root}/{app['id']}/events", headers=ADMIN).json()["data"]
    assert [e["action"] for e in events].count("version_published") == 1
    assert all(e["actor"] == "platform_admin" and e["request_id"] for e in events)
    assert (
        client.patch(
            versions + "/" + version["id"], headers=ADMIN, json={"status": "retired"}
        ).status_code
        == 200
    )
    assert client.get(public, headers=member).json()["data"] == []
    assert (
        client.patch(
            versions + "/" + version["id"], headers=ADMIN, json={"status": "published"}
        ).status_code
        == 409
    )


def test_duplicates_disabled_and_wrong_version(setup):
    client, tenants, root, app, _ = setup
    assert (
        client.post(root, headers=ADMIN, json={"slug": "erp", "name": "Duplicate"}).status_code
        == 409
    )
    other = f"/api/v1/admin/tenants/{tenants[1]['id']}/applications"
    assert (
        client.post(other, headers=ADMIN, json={"slug": "erp", "name": "Other ERP"}).status_code
        == 201
    )
    versions = f"{root}/{app['id']}/versions"
    version = client.post(versions, headers=ADMIN, json={"version": "1"}).json()
    assert client.post(versions, headers=ADMIN, json={"version": "1"}).status_code == 409
    client.patch(root + "/" + app["id"], headers=ADMIN, json={"enabled": False})
    assert (
        client.patch(
            versions + "/" + version["id"], headers=ADMIN, json={"status": "published"}
        ).status_code
        == 409
    )
    member = {"Authorization": "Bearer " + tenants[0]["api_key"]}
    assert client.get("/api/v1/applications", headers=member).json()["data"] == []
    assert (
        client.get(f"/api/v1/applications/{app['id']}/versions", headers=member).status_code == 404
    )
    assert (
        client.patch(versions + "/missing", headers=ADMIN, json={"status": "published"}).status_code
        == 404
    )
    assert client.post(root, headers=ADMIN, json={"slug": "bad", "name": "   "}).status_code == 422


def test_concurrent_publication_is_idempotent_and_import(setup, tmp_path):
    client, tenants, root, app, path = setup
    store = client.app.state.applications
    version = store.create_version(
        tenants[0]["id"], app["id"], VersionCreate(version="1"), "tester", "request"
    )

    def publish(_):
        return store.transition(
            tenants[0]["id"], app["id"], version["id"], "published", "tester", "request"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(row["status"] == "published" for row in pool.map(publish, range(2)))
    assert len(store.events(tenants[0]["id"], app["id"])) == 3
    target = str(tmp_path / "copy.db")
    counts = import_sqlite(path, target)
    assert (
        counts["applications"] == 1
        and counts["application_versions"] == 1
        and counts["application_events"] == 3
    )


def test_old_0002_upgrade_and_bootstrap_has_no_application_scope(tmp_path):
    path = str(tmp_path / "old.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        for name in ["application_events", "application_versions", "applications"]:
            db.execute("DROP TABLE " + name)
        db.execute("UPDATE alembic_version SET version_num='0002'")
    with pytest.raises(RuntimeError):
        Database(path)
    upgrade(path)
    database = Database(path)
    assert database.check()["revision"] == "0017"
    database.close()
    with TestClient(create_app(Settings("a" * 32, "b" * 32, path, {"localhost"}))) as client:
        assert (
            client.get(
                "/api/v1/applications", headers={"Authorization": "Bearer " + "b" * 32}
            ).status_code
            == 403
        )
