"""Portable small-corpus vector snapshots; not an approximate nearest-neighbor index."""

from alembic import op
from sqlalchemy import Column, ForeignKey, Table, Text, Integer, MetaData, inspect


def define_vector_tables(metadata):
    Table(
        "knowledge_vector_indexes",
        metadata,
        Column("version_id", Text, ForeignKey("application_versions.id"), primary_key=True),
        Column("model", Text, primary_key=True),
        Column("model_fingerprint", Text, nullable=False),
        Column("content_fingerprint", Text, nullable=False),
        Column("dimensions", Integer, nullable=False),
        Column("payload", Text, nullable=False),
    )


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    schema = MetaData()
    Table("application_versions", schema, Column("id", Text, primary_key=True))
    define_vector_tables(schema)
    db = op.get_bind()
    table = schema.tables["knowledge_vector_indexes"]
    inspector = inspect(db)
    if inspector.has_table(table.name):
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        if db.dialect.name != "sqlite" or actual != set(table.columns.keys()):
            raise RuntimeError("Existing vector schema does not match migration")
    else:
        table.create(db)


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
