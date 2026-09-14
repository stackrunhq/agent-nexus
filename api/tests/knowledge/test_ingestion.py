from concurrent.futures import ThreadPoolExecutor
import sqlite3
import subprocess

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import IntegrityError

from agent_nexus.app import Settings, create_app
from agent_nexus.knowledge import jobs
from agent_nexus.knowledge.store import KnowledgeStore, documents
from agent_nexus.storage.database import Database
from agent_nexus_cli.database import import_sqlite, upgrade

ADMIN = {"Authorization": "Bearer " + "a" * 32}
UPLOAD = {**ADMIN, "Content-Type": "application/octet-stream"}


@pytest.fixture
def scope(tmp_path):
    path = str(tmp_path / "knowledge.db")
    with TestClient(
        create_app(Settings("a" * 32, "b" * 32, path, {"localhost"}, "tenant"))
    ) as client:
        tenants = [
            client.post("/api/v1/admin/tenants", headers=ADMIN, json={"name": name}).json()
            for name in ("A", "B")
        ]
        apps = f"/api/v1/admin/tenants/{tenants[0]['id']}/applications"
        app = client.post(apps, headers=ADMIN, json={"slug": "erp", "name": "ERP"}).json()
        versions = apps + f"/{app['id']}/versions"
        version = client.post(versions, headers=ADMIN, json={"version": "1"}).json()
        root = versions + f"/{version['id']}"
        yield client, tenants, app, version, root, path


def upload(client, root, filename="manual.txt", content=None):
    return client.post(
        root + "/documents",
        params={"filename": filename},
        content=content if content is not None else "操作说明。".encode(),
        headers=UPLOAD,
    )


def test_upload_process_publish_withdraw_and_tenant_isolation(scope):
    client, tenants, app, version, root, _ = scope
    response = upload(client, root)
    assert response.status_code == 202
    document = response.json()
    assert document["status"] == "queued" and document["published"] is False
    assert not {"content", "claim_token", "lease_until"} & document.keys()
    assert upload(client, root).json()["id"] == document["id"]
    admin_doc = root + "/documents/" + document["id"]
    other_root = root.replace(tenants[0]["id"], tenants[1]["id"])
    assert upload(client, other_root).status_code == 404
    assert (
        client.get(
            other_root + "/documents/" + document["id"] + "/chunks", headers=ADMIN
        ).status_code
        == 404
    )
    assert client.get(admin_doc, headers={}).status_code == 401
    member = {"Authorization": "Bearer " + tenants[0]["api_key"]}
    other = {"Authorization": "Bearer " + tenants[1]["api_key"]}
    assert client.post(root + "/documents", headers=member, content=b"x").status_code == 401
    public = f"/api/v1/applications/{app['id']}/versions/{version['id']}/documents"
    assert client.get(public, headers=member).status_code == 404
    assert jobs.run_once(client.app.state.knowledge)
    assert not jobs.run_once(client.app.state.knowledge)
    assert client.get(admin_doc, headers=ADMIN).json()["status"] == "ready"
    assert client.patch(admin_doc, headers=ADMIN, json={"published": True}).status_code == 404
    client.patch(root, headers=ADMIN, json={"status": "published"})
    assert upload(client, root).status_code == 409
    assert client.get(public, headers=member).json()["data"] == []
    assert client.get(public + "/" + document["id"] + "/chunks", headers=member).status_code == 404
    assert client.patch(admin_doc, headers=ADMIN, json={"published": True}).status_code == 200
    assert client.get(public, headers=other).status_code == 404
    assert client.get(public, headers=member).json()["data"][0]["id"] == document["id"]
    chunks = client.get(public + "/" + document["id"] + "/chunks", headers=member).json()["data"]
    assert chunks[0]["text"] == "操作说明。" and chunks[0]["source_index"] == 1
    assert client.get(public, headers=member, params={"limit": 101}).status_code == 422
    client.patch(admin_doc, headers=ADMIN, json={"published": False})
    assert client.get(public, headers=member).json()["data"] == []
    client.patch(admin_doc, headers=ADMIN, json={"published": True})
    client.patch(root, headers=ADMIN, json={"status": "retired"})
    assert client.get(public, headers=member).status_code == 404


def test_failure_retry_and_lease_fencing(scope, monkeypatch):
    client, _, _, _, root, _ = scope
    document = upload(client, root, "bad.pdf", b"broken").json()
    store = client.app.state.knowledge
    assert jobs.run_once(store)
    path = root + "/documents/" + document["id"]
    failed = client.get(path, headers=ADMIN).json()
    assert failed["status"] == "failed" and failed["error"] == "invalid_document"
    assert client.post(path + "/retry", headers=ADMIN).status_code == 202
    assert client.post(path + "/retry", headers=ADMIN).status_code == 409
    first = store.claim()
    assert first["id"] == document["id"]
    assert store.claim() is None
    with store.database.write("test") as db:
        db.execute(documents.update().values(lease_until=0))
    second = store.claim()
    assert second["claim_token"] != first["claim_token"]
    assert not store.finish(first["id"], first["claim_token"], error="stale")
    assert store.finish(second["id"], second["claim_token"], error="parser_timeout")
    monkeypatch.setattr(
        jobs.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("parser", 60)),
    )
    assert jobs.parse_isolated("test.txt", b"text") == {"error": "parser_timeout"}


def test_restart_import_chunks_bytes_and_concurrent_claim(scope, tmp_path):
    client, tenants, app, version, root, path = scope
    document = upload(client, root, content=("文档内容" * 600).encode()).json()
    database = Database(path)
    try:
        store = KnowledgeStore(database)
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _: store.claim(), range(2)))
        assert sum(task is not None for task in claims) == 1
        task = next(task for task in claims if task)
        result = jobs.parse_isolated(task["filename"], task["content"])
        assert "error" not in result
        assert store.finish(task["id"], task["claim_token"], result=result)
        target = str(tmp_path / "copy.db")
        counts = import_sqlite(path, target)
        assert counts["knowledge_documents"] == 1 and counts["knowledge_chunks"] > 1
        copied = Database(target)
        try:
            rows = KnowledgeStore(copied).get(
                tenants[0]["id"], app["id"], version["id"], document["id"], with_chunks=True
            )
            assert rows[0]["text"] == result["chunks"][0]["text"]
        finally:
            copied.close()
    finally:
        database.close()


def test_upload_validation_and_expired_attempts(scope, monkeypatch):
    client, _, _, _, root, _ = scope
    assert upload(client, root, "../x.txt").status_code == 422
    assert upload(client, root, "x.exe").status_code == 415
    assert upload(client, root, content=b"").status_code == 422
    from agent_nexus.knowledge import router

    monkeypatch.setattr(router, "MAX_FILE_BYTES", 2)
    assert upload(client, root, content=b"abc").status_code == 413
    document = upload(client, root, content=b"ok").json()
    store = client.app.state.knowledge
    for _ in range(3):
        assert store.claim() is not None
        with store.database.write("test") as db:
            db.execute(documents.update().values(lease_until=0))
    assert store.claim() is None
    assert (
        client.get(root + "/documents/" + document["id"], headers=ADMIN).json()["error"]
        == "worker_interrupted"
    )


def test_0003_requires_upgrade(tmp_path):
    path = str(tmp_path / "old.db")
    upgrade(path)
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE knowledge_chunks")
        db.execute("DROP TABLE knowledge_documents")
        db.execute("UPDATE alembic_version SET version_num='0003'")
    with pytest.raises(RuntimeError):
        Database(path)
    upgrade(path)
    database = Database(path)
    try:
        assert database.check()["revision"] == "0010"
    finally:
        database.close()


def test_chunk_write_is_atomic_and_publication_requires_ready(scope):
    client, _, _, _, root, _ = scope
    document = upload(client, root).json()
    store = client.app.state.knowledge
    task = store.claim()
    result = jobs.parse_isolated(task["filename"], task["content"])
    result["chunks"].append({**result["chunks"][0], "index": 1, "text": None})
    with pytest.raises(IntegrityError):
        store.finish(task["id"], task["claim_token"], result=result)
    path = root + "/documents/" + document["id"]
    assert client.get(path + "/chunks", headers=ADMIN).json()["data"] == []
    assert client.get(path, headers=ADMIN).json()["status"] == "processing"
    client.patch(root, headers=ADMIN, json={"status": "published"})
    assert client.patch(path, headers=ADMIN, json={"published": True}).status_code == 409


def test_bootstrap_has_no_document_scope(tmp_path):
    with TestClient(
        create_app(Settings("a" * 32, "b" * 32, str(tmp_path / "boot.db"), set()))
    ) as client:
        response = client.get(
            "/api/v1/applications/missing/versions/missing/documents",
            headers={"Authorization": "Bearer " + "b" * 32},
        )
        assert response.status_code == 403
