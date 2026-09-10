"""Durable, fenced index build jobs."""

from sqlalchemy import Column, ForeignKey, Integer, Table, Text
from alembic import op
from sqlalchemy import MetaData, inspect


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



revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    schema = MetaData()
    for name in ("tenants", "applications", "application_versions"):
        Table(name, schema, Column("id", Text, primary_key=True))
    define_index_job_tables(schema)
    db = op.get_bind()
    table = schema.tables["knowledge_index_jobs"]
    inspector = inspect(db)
    if inspector.has_table(table.name):
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        if db.dialect.name != "sqlite" or actual != set(table.columns.keys()):
            raise RuntimeError("Existing index job schema does not match migration")
    else:
        table.create(db)


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
