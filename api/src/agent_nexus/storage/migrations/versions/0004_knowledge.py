"""Frozen knowledge document and chunk schema."""

from alembic import op
from sqlalchemy import MetaData, inspect

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    LargeBinary,
    Table,
    Text,
    UniqueConstraint,
)


def define_knowledge_tables(metadata):
    Table(
        "knowledge_documents",
        metadata,
        Column("id", Text, primary_key=True),
        Column(
            "version_id", Text, ForeignKey("application_versions.id"), nullable=False, index=True
        ),
        Column("filename", Text, nullable=False),
        Column("sha256", Text, nullable=False),
        Column("content", LargeBinary, nullable=False),
        Column("status", Text, nullable=False, server_default="queued", index=True),
        Column("error", Text),
        Column("warnings", Text, nullable=False, server_default="[]"),
        Column("published", Integer, nullable=False, server_default="0"),
        Column("claim_token", Text),
        Column("lease_until", BigInteger, nullable=False, server_default="0"),
        Column("attempts", Integer, nullable=False, server_default="0"),
        Column("created_at", BigInteger, nullable=False),
        Column("actor", Text, nullable=False),
        Column("request_id", Text, nullable=False),
        UniqueConstraint("version_id", "sha256", "filename", name="uq_document_upload"),
        CheckConstraint(
            "status IN ('queued','processing','ready','failed')", name="ck_document_status"
        ),
        CheckConstraint(
            "published IN (0,1) AND (published=0 OR status='ready')", name="ck_document_publication"
        ),
    )
    Table(
        "knowledge_chunks",
        metadata,
        Column("document_id", Text, ForeignKey("knowledge_documents.id"), primary_key=True),
        Column("chunk_index", Integer, primary_key=True),
        Column("text", Text, nullable=False),
        Column("source_kind", Text, nullable=False),
        Column("source_index", Integer, nullable=False),
        Column("start", Integer, nullable=False),
        Column("end", Integer, nullable=False),
    )


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    schema = MetaData()
    Table("application_versions", schema, Column("id", Text, primary_key=True))
    define_knowledge_tables(schema)
    db = op.get_bind()
    inspector = inspect(db)
    for table in schema.sorted_tables:
        if table.name == "application_versions":
            continue
        if inspector.has_table(table.name):
            actual = {column["name"] for column in inspector.get_columns(table.name)}
            if db.dialect.name != "sqlite" or actual != set(table.columns.keys()):
                raise RuntimeError("Existing knowledge schema does not match migration")
        else:
            table.create(db)


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
