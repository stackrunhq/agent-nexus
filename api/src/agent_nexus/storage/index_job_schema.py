"""Durable, fenced index build jobs."""

from sqlalchemy import Column, ForeignKey, Integer, Table, Text, Index


def define_index_job_tables(metadata):
    table = Table(
        "knowledge_index_jobs",
        metadata,
        Column("id", Text, primary_key=True),
        Column("tenant_id", Text, ForeignKey("tenants.id"), nullable=False),
        Column("app_id", Text, ForeignKey("applications.id"), nullable=False),
        Column("version_id", Text, ForeignKey("application_versions.id"), nullable=False),
        Column("model", Text, nullable=False),
        Column("status", Text, nullable=False),
        Column("attempts", Integer, nullable=False),
        Column("lease_until", Integer, nullable=False),
        Column("claim_token", Text, nullable=False),
        Column("created_at", Integer, nullable=False),
        Column("actor", Text, nullable=False),
        Column("request_id", Text, nullable=False),
        Column("error", Text),
    )
    Index(
        "ix_index_history_scope",
        table.c.tenant_id,
        table.c.app_id,
        table.c.version_id,
        table.c.created_at.desc(),
        table.c.id,
    )
    Index(
        "ix_index_history_model",
        table.c.tenant_id,
        table.c.app_id,
        table.c.version_id,
        table.c.model,
        table.c.created_at.desc(),
        table.c.id,
    )
