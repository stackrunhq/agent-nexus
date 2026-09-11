"""Portable connection/transaction boundary for configuration storage."""

import hashlib
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    event,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool
from .identity_schema import define_identity_tables
from .application_schema import define_application_tables
from .knowledge_schema import define_knowledge_tables
from .vector_schema import define_vector_tables
from .index_job_schema import define_index_job_tables
from .quota_schema import define_quota_tables
from .model_usage_schema import define_model_usage_tables

metadata = MetaData()
models = Table(
    "models",
    metadata,
    Column("alias", Text, primary_key=True),
    Column("config", Text, nullable=False),
)
model_audit = Table(
    "model_audit",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", Text, nullable=False),
    Column("actor", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("alias", Text, nullable=False),
    Column("changed_fields", Text, nullable=False),
    Column("request_id", Text),
)
Index("ix_model_audit_alias_id", model_audit.c.alias, model_audit.c.id)
tenants = Table(
    "tenants",
    metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("enabled", Integer, nullable=False, server_default="1"),
    Column("key_hash", Text, nullable=False, unique=True),
)
tenant_models = Table(
    "tenant_models",
    metadata,
    Column("tenant_id", Text, ForeignKey("tenants.id"), primary_key=True),
    Column("alias", Text, ForeignKey("models.alias"), primary_key=True),
)
tenant_events = Table(
    "tenant_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", Text, nullable=False),
    Column("tenant_id", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("alias", Text),
)


define_identity_tables(metadata)
define_application_tables(metadata)
define_knowledge_tables(metadata)
define_vector_tables(metadata)
define_index_job_tables(metadata)
define_quota_tables(metadata)
define_model_usage_tables(metadata)


def connection_url(target: str):
    if "://" not in target:
        path = Path(target).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return URL.create("sqlite", database=str(path))
    url = make_url(target)
    if url.drivername not in {"sqlite", "postgresql+psycopg"}:
        raise ValueError("Use a SQLite path or postgresql+psycopg:// URL")
    return url


def run(db, sql, **params):
    return db.execute(text(sql), params)


class Database:
    def __init__(self, target: str, *, prepare=True):
        url = connection_url(target)
        self.sqlite = url.get_backend_name() == "sqlite"
        options = (
            {"connect_args": {"timeout": 10}, "poolclass": NullPool}
            if self.sqlite
            else {"pool_pre_ping": True, "pool_timeout": 5, "connect_args": {"connect_timeout": 10}}
        )
        self.engine = create_engine(url, hide_parameters=True, **options)
        if self.sqlite:

            @event.listens_for(self.engine, "connect")
            def foreign_keys(connection, _):
                connection.execute("PRAGMA foreign_keys = ON")

        if prepare:
            try:
                if self.sqlite:
                    # Preserve the zero-setup development path, including legacy databases.
                    with self.write("schema") as db:
                        if inspect(db).has_table("alembic_version") and (
                            run(db, "SELECT version_num FROM alembic_version").scalar_one()
                            != "0008"
                        ):
                            raise RuntimeError("Run the explicit schema upgrade first")
                        metadata.create_all(db)
                else:
                    with self.read() as db:
                        revision = run(db, "SELECT version_num FROM alembic_version").scalar_one()
                        if revision != "0008":
                            raise RuntimeError("Database schema is not at the supported revision")
            except Exception:
                self.engine.dispose()
                raise RuntimeError(
                    "Database unavailable or schema not ready; run python -m agent_nexus.db_cli upgrade"
                ) from None

    @contextmanager
    def read(self):
        with self.engine.connect() as db:
            yield db

    def check(self):
        """Check required columns without scanning or parsing business records."""
        with self.read() as db:
            for table in metadata.sorted_tables:
                db.execute(select(table).limit(0)).close()
            if inspect(db).has_table("alembic_version"):
                revision = run(db, "SELECT version_num FROM alembic_version").scalar_one()
                if revision != "0008":
                    raise RuntimeError("Unsupported schema revision")
            elif self.sqlite:
                revision = "unversioned"
            else:
                raise RuntimeError("Missing schema revision")
        return {
            "status": "ok",
            "backend": "sqlite" if self.sqlite else "postgresql",
            "revision": revision,
        }

    @contextmanager
    def write(self, key: str):
        with self.engine.begin() as db:
            if self.sqlite:
                db.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                run(db, "SELECT set_config('lock_timeout', '5000', true)")
                lock = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
                run(db, "SELECT pg_advisory_xact_lock(:key)", key=lock)
            yield db

    def close(self):
        self.engine.dispose()
