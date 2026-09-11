import hashlib
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from agent_nexus.app import Settings, create_app
from agent_nexus.storage.database import Database, run
from agent_nexus_cli.database import check, import_sqlite, upgrade
from agent_nexus.models.schemas import ModelConfig
from agent_nexus.models.store import ModelStore
from agent_nexus.tenants.store import TenantStore


def seed(target):
    store = ModelStore(target)
    model = ModelConfig(
        alias="local",
        provider="ollama",
        model="test",
        base_url="http://localhost:11434",
        deployment="local",
        capabilities=["chat"],
    )
    store.put(model)
    tenants = TenantStore(store.database)
    tenant = tenants.create("示例企业")
    tenants.grant(tenant["id"], "local", True)
    store.database.close()
    return model, tenant


def test_upgrade_new_and_legacy_sqlite(tmp_path):
    path = str(tmp_path / "old.db")
    model, tenant = seed(path)
    upgrade(path)
    upgrade(path)
    database = Database(path)
    with database.read() as db:
        assert run(db, "SELECT version_num FROM alembic_version").scalar_one() == "0008"
    assert ModelStore(database).get("local") == model
    assert TenantStore(database).authenticate(tenant["api_key"]) == tenant["id"]
    database.close()
    fresh = str(tmp_path / "new.db")
    upgrade(fresh)
    assert ModelStore(fresh).list() == []


def test_copy_preserves_source_credentials_and_events(tmp_path):
    src, dst = str(tmp_path / "source.db"), str(tmp_path / "target.db")
    model, tenant = seed(src)
    before = hashlib.sha256((tmp_path / "source.db").read_bytes()).digest()
    counts = import_sqlite(src, dst)
    assert counts == {
        "models": 1,
        "model_audit": 1,
        "tenants": 1,
        "tenant_models": 1,
        "tenant_events": 2,
        "users": 0,
        "user_sessions": 0,
        "user_events": 0,
        "applications": 0,
        "application_versions": 0,
        "application_events": 0,
        "knowledge_documents": 0,
        "knowledge_chunks": 0,
        "knowledge_vector_indexes": 0,
        "knowledge_index_jobs": 0,
        "tenant_index_quotas": 0,
        "model_calls": 0,
    }
    database = Database(dst)
    assert ModelStore(database).get("local") == model
    assert TenantStore(database).authenticate(tenant["api_key"]) == tenant["id"]
    assert TenantStore(database).grants(tenant["id"]) == ["local"]
    assert hashlib.sha256((tmp_path / "source.db").read_bytes()).digest() == before
    with pytest.raises(ValueError, match="empty"):
        import_sqlite(src, dst)
    assert len(ModelStore(database).audit()["data"]) == 1
    database.close()


def test_failed_import_rolls_back_all_tables(tmp_path):
    src, dst = str(tmp_path / "source.db"), str(tmp_path / "target.db")
    seed(src)
    with sqlite3.connect(src) as db:
        # Simulate corrupt legacy data; foreign keys are off on this independent connection.
        db.execute("INSERT INTO tenant_models VALUES ('missing', 'local')")
    with pytest.raises(IntegrityError):
        import_sqlite(src, dst)
    assert ModelStore(dst).list() == []
    assert TenantStore(dst).list() == []


def test_unknown_legacy_layout_not_stamped(tmp_path):
    path = str(tmp_path / "bad.db")
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE models(unexpected TEXT)")
    with pytest.raises(RuntimeError, match="columns"):
        upgrade(path)


def test_database_url_precedence(tmp_path):
    target = tmp_path / "url.db"
    settings = Settings(
        "a" * 32,
        "b" * 32,
        str(tmp_path / "unused.db"),
        set(),
        database_url="sqlite:///" + target.as_posix(),
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").status_code == 200
    assert target.exists() and not (tmp_path / "unused.db").exists()


def test_import_rejects_missing_and_same_source(tmp_path):
    path = str(tmp_path / "db.sqlite")
    with pytest.raises(FileNotFoundError):
        import_sqlite(path, str(tmp_path / "target.db"))
    seed(path)
    with pytest.raises(ValueError, match="differ"):
        import_sqlite(path, path)


def test_import_source_path_with_uri_characters(tmp_path):
    source = str(tmp_path / "知识库 #1.db")
    seed(source)
    assert import_sqlite(source, str(tmp_path / "target.db"))["models"] == 1


def test_diagnostics_do_not_create_missing_database(tmp_path):
    missing = tmp_path / "missing" / "db.sqlite"
    for target in (str(missing), "sqlite:///" + missing.as_posix()):
        with pytest.raises(ValueError, match="exist"):
            check(target)
    assert not missing.parent.exists()


def test_diagnostics_report_revision_without_parsing_model_data(tmp_path):
    path = str(tmp_path / "db.sqlite")
    seed(path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE models SET config = 'intentionally malformed'")
    before = hashlib.sha256((tmp_path / "db.sqlite").read_bytes()).digest()
    assert check(path) == {"status": "ok", "backend": "sqlite", "revision": "unversioned"}
    assert hashlib.sha256((tmp_path / "db.sqlite").read_bytes()).digest() == before
    upgrade(path)
    assert check(path)["revision"] == "0008"


def test_readiness_detects_missing_table_and_recovers(tmp_path):
    path = str(tmp_path / "db.sqlite")
    settings = Settings("a" * 32, "b" * 32, path, set())
    with TestClient(create_app(settings)) as client:
        with sqlite3.connect(path) as db:
            db.execute("ALTER TABLE tenant_events RENAME TO temporarily_missing")
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "database_not_ready"
        assert "tenant_events" not in response.text and path not in response.text
        assert response.headers["x-request-id"] == response.json()["request_id"]
        assert client.get("/health/live").status_code == 200
        with sqlite3.connect(path) as db:
            db.execute("ALTER TABLE temporarily_missing RENAME TO tenant_events")
        assert client.get("/health/ready").status_code == 200


def test_readiness_rejects_changed_schema_revision(tmp_path):
    path = str(tmp_path / "db.sqlite")
    upgrade(path)
    with TestClient(create_app(Settings("a" * 32, "b" * 32, path, set()))) as client:
        with sqlite3.connect(path) as db:
            db.execute("UPDATE alembic_version SET version_num = 'future'")
        assert client.get("/health/ready").status_code == 503
        with pytest.raises(RuntimeError, match="revision"):
            check(path)
