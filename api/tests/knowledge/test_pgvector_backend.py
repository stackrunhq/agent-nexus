import json
import os
from uuid import uuid4
import pytest
from sqlalchemy import text
from agent_nexus.core.errors import GatewayError
from agent_nexus.knowledge import pgvector_backend as backend
from agent_nexus.storage.database import Database
from test_ingestion import scope as scope


def test_backend_explicit_opt_in_and_sqlite_rejection(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "test.db"))
    try:
        monkeypatch.delenv("NEXUS_VECTOR_BACKEND", raising=False)
        assert not backend.enabled(database)
        monkeypatch.setenv("NEXUS_VECTOR_BACKEND", "pgvector")
        with pytest.raises(GatewayError) as error:
            backend.enabled(database)
        assert error.value.code == "vector_backend_unavailable"
        monkeypatch.setenv("NEXUS_VECTOR_BACKEND", "typo")
        with pytest.raises(RuntimeError):
            backend.enabled(database)
    finally:
        database.close()


def test_snapshot_signature_binds_vector_values():
    assert backend.signature("[[1,0]]") != backend.signature("[[0,1]]")


@pytest.mark.skipif(
    not os.getenv("NEXUS_TEST_PGVECTOR_URL"), reason="Requires dedicated pgvector test database"
)
def test_native_exact_ranking_scope_and_rebuild():
    database = Database(os.environ["NEXUS_TEST_PGVECTOR_URL"], prepare=False)
    version = str(uuid4())
    payload = json.dumps([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])
    try:
        backend.setup(database)
        with database.write("test-pgvector") as db:
            backend.save(db, version, "test", payload)
        ranked = backend.rank(database, version, "test", payload, [1.0, 0.0], 3)
        assert [row["ordinal"] for row in ranked] == [0, 1, 2]
        assert [row["score"] for row in ranked] == pytest.approx([1, 0, -1], abs=1e-6)
        for other_version, other_model, other_payload in [
            ("missing", "test", payload),
            (version, "missing", payload),
            (version, "test", "[[0,1]]"),
        ]:
            with pytest.raises(GatewayError) as error:
                backend.rank(database, other_version, other_model, other_payload, [1, 0], 3)
            assert error.value.code == "pgvector_rebuild_required"
    finally:
        with database.write("test-pgvector") as db:
            db.execute(
                text("DELETE FROM nexus_vectors.entries WHERE version_id=:version"),
                {"version": version},
            )
        database.close()


@pytest.mark.skipif(
    not os.getenv("NEXUS_TEST_PGVECTOR_URL"), reason="Requires dedicated pgvector test database"
)
def test_native_api_matches_portable_and_honors_withdrawal(scope, monkeypatch):
    import httpx
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from agent_nexus.app import Settings, create_app
    from agent_nexus_cli.database import upgrade, import_sqlite
    from test_index_jobs import prepare
    from test_ingestion import ADMIN
    from test_vectors import provider

    monkeypatch.setenv("NEXUS_VECTOR_BACKEND", "portable")
    _, alias = prepare(scope)
    source_client, tenants, app, version, root, source = scope
    assert (
        source_client.post(root + "/vector-index", headers=ADMIN, json={"model": alias}).status_code
        == 200
    )
    admin_url = make_url(os.environ["NEXUS_TEST_PGVECTOR_URL"])
    database_name = "nexus_native_" + uuid4().hex
    owner = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    target = admin_url.set(database=database_name).render_as_string(hide_password=False)
    with owner.connect() as db:
        db.execute(text("CREATE DATABASE " + database_name))
    try:
        upgrade(target)
        database = Database(target)
        try:
            backend.setup(database)
        finally:
            database.close()
        import_sqlite(source, target)
        legacy = create_engine(target)
        try:
            with legacy.begin() as db:
                db.execute(text("DROP TABLE knowledge_index_workers"))
                db.execute(text("DROP TABLE knowledge_index_scheduler"))
                db.execute(text("DROP TABLE knowledge_index_batches"))
                db.execute(text("DROP TABLE knowledge_content_revisions"))
                db.execute(text("DROP TABLE knowledge_index_checkpoints"))
                db.execute(text("DROP TABLE knowledge_vector_metadata"))
                db.execute(text("UPDATE alembic_version SET version_num='0009'"))
            upgrade(target)
        finally:
            legacy.dispose()
        monkeypatch.setenv("NEXUS_VECTOR_BACKEND", "pgvector")
        with TestClient(
            create_app(
                Settings("a" * 32, "b" * 32, target, {"localhost"}, "tenant"),
                httpx.MockTransport(provider),
            )
        ) as client:
            built = client.post(root + "/vector-index", headers=ADMIN, json={"model": alias})
            assert built.status_code == 200, built.text
            public = f"/api/v1/applications/{app['id']}/versions/{version['id']}/vector-search"
            member = {"Authorization": "Bearer " + tenants[0]["api_key"]}
            body = {"model": alias, "query": "password"}
            from agent_nexus.knowledge.vectors import VectorService

            with monkeypatch.context() as patch:
                patch.setattr(
                    VectorService,
                    "load",
                    lambda *args: pytest.fail("Native search must not load vector JSON"),
                )
                native = client.post(public, headers=member, json=body)
            assert native.status_code == 200, native.text
            assert native.json()["method"] == "pgvector_cosine"
            monkeypatch.setenv("NEXUS_VECTOR_BACKEND", "portable")
            portable = client.post(public, headers=member, json=body).json()
            assert [(r["document_id"], r["chunk_index"]) for r in native.json()["data"]] == [
                (r["document_id"], r["chunk_index"]) for r in portable["data"]
            ]
            monkeypatch.setenv("NEXUS_VECTOR_BACKEND", "pgvector")
            assert (
                client.post(
                    public, headers={"Authorization": "Bearer " + tenants[1]["api_key"]}, json=body
                ).status_code
                == 404
            )
            document = native.json()["data"][0]["document_id"]
            client.patch(root + "/documents/" + document, headers=ADMIN, json={"published": False})
            assert (
                client.post(public, headers=member, json=body).json()["error"]["code"]
                == "index_stale"
            )
    finally:
        with owner.connect() as db:
            db.execute(text("DROP DATABASE " + database_name + " WITH (FORCE)"))
        owner.dispose()
