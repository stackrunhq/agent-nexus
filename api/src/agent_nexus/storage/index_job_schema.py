"""Durable, fenced index build jobs."""

from sqlalchemy import Column, ForeignKey, Integer, Table, Text


def define_index_job_tables(metadata):
    Table(
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
