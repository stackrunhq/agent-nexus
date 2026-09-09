"""Real pg_dump/pg_restore rehearsal in two newly created disposable databases."""

import os
import shutil
import secrets
import subprocess
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from agent_nexus.app import Settings, create_app
from agent_nexus.storage.database import Database, metadata
from agent_nexus_cli.database import digest, upgrade
from agent_nexus.models.schemas import ModelConfig
from agent_nexus.models.store import ModelStore
from agent_nexus.tenants.store import TenantStore
from agent_nexus.identity.store import IdentityStore
from agent_nexus.identity.schemas import UserCreate
from agent_nexus.applications.store import ApplicationStore
from agent_nexus.applications.schemas import ApplicationCreate, VersionCreate


def pg_tool(name):
    directory = os.getenv("NEXUS_TEST_PG_BIN")
    if directory:
        return str(Path(directory) / (name + (".exe" if os.name == "nt" else "")))
    return shutil.which(name)


@pytest.mark.skipif(
    not os.getenv("NEXUS_TEST_POSTGRES_URL") or not pg_tool("pg_dump") or not pg_tool("pg_restore"),
    reason="Dedicated PostgreSQL server and matching pg_dump/pg_restore required",
)
def test_backup_restore_data_auth_api_and_sequences(tmp_path):
    base = make_url(os.environ["NEXUS_TEST_POSTGRES_URL"])
    admin = create_engine(base, isolation_level="AUTOCOMMIT", hide_parameters=True)
    names = ["nexus_backup_" + uuid4().hex, "nexus_restore_" + uuid4().hex]
    created, databases = [], []
    runtime_role = None
    try:
        with admin.connect() as connection:
            for name in names:
                connection.exec_driver_sql(f'CREATE DATABASE "{name}" TEMPLATE template0')
                created.append(name)
        urls = [base.set(database=name).render_as_string(hide_password=False) for name in names]
        upgrade(urls[0])
        source = Database(urls[0])
        databases.append(source)
        model = ModelConfig(
            alias="restore-help",
            provider="ollama",
            model="test",
            base_url="http://provider.test",
            deployment="local",
            capabilities=["chat"],
        )
        ModelStore(source).put(model)
        tenant = TenantStore(source).create("恢复演练企业")
        TenantStore(source).grant(tenant["id"], model.alias, True)
        member = IdentityStore(source).create(
            UserCreate(
                username="restore-member",
                password="restore-test-password",
                role="tenant_user",
                tenant_id=tenant["id"],
            ),
            "platform_admin",
        )
        member_token = IdentityStore(source).login("restore-member", "restore-test-password")[
            "access_token"
        ]
        source_hashes, counts = {}, {}
        application = ApplicationStore(source).create(
            tenant["id"], ApplicationCreate(slug="erp", name="ERP"), "platform_admin", "restore"
        )
        version = ApplicationStore(source).create_version(
            tenant["id"],
            application["id"],
            VersionCreate(version="1.0"),
            "platform_admin",
            "restore",
        )
        ApplicationStore(source).transition(
            tenant["id"], application["id"], version["id"], "published", "platform_admin", "restore"
        )
        with source.read() as connection:
            for table in metadata.sorted_tables:
                source_hashes[table.name] = digest(connection, table)
                counts[table.name] = connection.execute(
                    select(func.count()).select_from(table)
                ).scalar_one()

        archive = tmp_path / "nexus.backup"
        environment = os.environ.copy()
        for key in ("PGOPTIONS", "PGSERVICE", "PGSERVICEFILE"):
            environment.pop(key, None)
        environment.update(
            PGHOST=base.host or "localhost",
            PGPORT=str(base.port or 5432),
            PGUSER=base.username or "postgres",
            PGPASSWORD=base.password or "",
            PGCONNECT_TIMEOUT="10",
        )
        # Password is passed in the child environment, never in command arguments or logs.
        for command in (
            [
                pg_tool("pg_dump"),
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--dbname",
                names[0],
                "--file",
                str(archive),
            ],
            [
                pg_tool("pg_restore"),
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-acl",
                "--dbname",
                names[1],
                str(archive),
            ],
        ):
            completed = subprocess.run(command, env=environment, capture_output=True, timeout=120)
            assert completed.returncode == 0, (
                "PostgreSQL backup/restore command failed (output withheld)"
            )
        assert archive.stat().st_size > 0
        restored = Database(urls[1])
        databases.append(restored)
        assert restored.check()["revision"] == "0003"
        assert IdentityStore(restored).authenticate(member_token)["id"] == member["id"]
        with restored.read() as connection:
            for table in metadata.sorted_tables:
                assert digest(connection, table) == source_hashes[table.name]
        assert TenantStore(restored).authenticate(tenant["api_key"]) == tenant["id"]
        assert TenantStore(restored).allowed(tenant["id"]) == {model.alias}

        # Rehearse a runtime account without migration or DDL privileges.
        runtime_role = "nexus_app_" + uuid4().hex
        runtime_password = secrets.token_hex(32)
        with admin.connect() as connection:
            connection.exec_driver_sql(
                f"CREATE ROLE {runtime_role} LOGIN PASSWORD '{runtime_password}'"
            )
        with restored.engine.begin() as connection:
            connection.exec_driver_sql(f'GRANT CONNECT ON DATABASE "{names[1]}" TO {runtime_role}')
            connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {runtime_role}")
            connection.exec_driver_sql(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON models, model_audit, tenants, tenant_models, tenant_events, users, user_sessions, user_events, applications, application_versions, application_events TO {runtime_role}"
            )
            connection.exec_driver_sql(f"GRANT SELECT ON alembic_version TO {runtime_role}")
            connection.exec_driver_sql(
                f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {runtime_role}"
            )
        runtime_url = (
            make_url(urls[1])
            .set(username=runtime_role, password=runtime_password)
            .render_as_string(hide_password=False)
        )
        restricted = Database(runtime_url)
        databases.append(restricted)
        with pytest.raises(ProgrammingError), restricted.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE forbidden_ddl (id INTEGER)")
        with pytest.raises(ProgrammingError), restricted.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE alembic_version SET version_num = 'forbidden'")
        settings = Settings("a" * 32, "", "unused", {"provider.test"}, "tenant", runtime_url)

        def upstream(request):
            return httpx.Response(200, json={"done": True, "message": {"content": "restored"}})

        with TestClient(create_app(settings, httpx.MockTransport(upstream))) as client:
            headers = {"Authorization": "Bearer " + tenant["api_key"]}
            assert client.get("/health/ready").status_code == 200
            published = client.get(
                f"/api/v1/applications/{application['id']}/versions",
                headers={"Authorization": "Bearer " + member_token},
            )
            assert (
                published.status_code == 200 and published.json()["data"][0]["id"] == version["id"]
            )
            assert (
                client.get("/api/v1/models", headers=headers).json()["data"][0]["id"] == model.alias
            )
            result = client.post(
                "/api/v1/chat/completions",
                headers=headers,
                json={"model": model.alias, "messages": [{"role": "user", "content": "test"}]},
            )
            assert result.status_code == 200 and result.json()["content"] == "restored"
        store = ModelStore(restricted)
        ApplicationStore(restricted).status(
            tenant["id"], application["id"], False, "platform_admin", "restore"
        )
        assert (
            ApplicationStore(restricted).events(tenant["id"], application["id"])[0]["id"]
            > counts["application_events"]
        )
        store.put(model.model_copy(update={"enabled": False}), expected_etag=store.etag(model))
        TenantStore(restricted).status(tenant["id"], False)
        assert store.audit()["data"][0]["id"] > counts["model_audit"]
        assert TenantStore(restored).events(tenant["id"])[0]["id"] > counts["tenant_events"]
    finally:
        for database in databases:
            database.close()
        with admin.connect() as connection:
            for name in reversed(created):
                connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
            if runtime_role:
                connection.exec_driver_sql(f'DROP ROLE "{runtime_role}"')
        admin.dispose()
