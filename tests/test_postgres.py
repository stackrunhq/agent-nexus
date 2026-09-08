"""Runs only against an explicitly supplied test server, in a disposable schema."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from agent_nexus.database import Database
from agent_nexus.db_cli import import_sqlite, upgrade
from agent_nexus.store import ConfigurationConflict, ModelStore
from agent_nexus.tenant_store import TenantStore
from test_database import seed


@pytest.mark.skipif(
    not os.getenv("NEXUS_TEST_POSTGRES_URL"),
    reason="No dedicated PostgreSQL test server configured",
)
def test_postgres_migration_import_grants_and_concurrency(tmp_path):
    base = make_url(os.environ["NEXUS_TEST_POSTGRES_URL"])
    schema = "nexus_test_" + uuid4().hex
    admin = create_engine(base, hide_parameters=True)
    with admin.begin() as db:
        db.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    url = base.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(
        hide_password=False
    )
    database = None
    try:
        with pytest.raises(RuntimeError, match="schema"):
            Database(url)
        upgrade(url)
        upgrade(url)
        source = str(tmp_path / "source.db")
        original, tenant = seed(source)
        counts = import_sqlite(source, url)
        assert counts["tenant_events"] == 2
        database = Database(url)
        store, tenants = ModelStore(database), TenantStore(database)
        assert store.get("local") == original
        assert tenants.authenticate(tenant["api_key"]) == tenant["id"]
        assert tenants.allowed(tenant["id"]) == {"local"}
        tenants.status(tenant["id"], False)
        assert tenants.authenticate(tenant["api_key"]) is None
        assert tenants.events(tenant["id"])[0]["id"] > 2
        tag, barrier = store.etag(original), Barrier(2)

        def write(name):
            barrier.wait(timeout=5)
            try:
                store.put(original.model_copy(update={"model": name}), expected_etag=tag)
                return "saved"
            except ConfigurationConflict:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(write, ["a", "b"])) == ["conflict", "saved"]
        assert len(store.audit()["data"]) == 2
        assert store.audit()["data"][0]["id"] > 1
    finally:
        if database:
            database.close()
        with admin.begin() as db:
            db.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()
