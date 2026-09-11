from alembic import op
from sqlalchemy import MetaData, inspect
from sqlalchemy import Column, ForeignKey, Integer, Table, Text, Index


def define_model_usage_tables(metadata):
    table = Table(
        "model_calls",
        metadata,
        Column("id", Text, primary_key=True),
        Column("tenant_id", Text, ForeignKey("tenants.id"), nullable=False),
        Column("request_id", Text, nullable=False),
        Column("model", Text, nullable=False),
        Column("model_fingerprint", Text, nullable=False),
        Column("capability", Text, nullable=False),
        Column("created_at", Integer, nullable=False),
        Column("status", Text, nullable=False),
        Column("elapsed_ms", Integer),
        Column("input_tokens", Integer),
        Column("output_tokens", Integer),
        Column("error", Text),
    )
    Index("ix_model_calls_tenant_created", table.c.tenant_id, table.c.created_at)


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    schema = MetaData()
    Table("tenants", schema, Column("id", Text, primary_key=True))
    define_model_usage_tables(schema)
    db = op.get_bind()
    table = schema.tables["model_calls"]
    inspector = inspect(db)
    if inspector.has_table(table.name):
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        if db.dialect.name != "sqlite" or actual != set(table.columns.keys()):
            raise RuntimeError("Existing model usage schema does not match migration")
    else:
        table.create(db)


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
