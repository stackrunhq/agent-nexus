from alembic import op
from sqlalchemy import MetaData, inspect
from sqlalchemy import Column, ForeignKey, Integer, Table, Text


def define_index_progress_tables(metadata):
    Table(
        "knowledge_content_revisions",
        metadata,
        Column("version_id", Text, ForeignKey("application_versions.id"), primary_key=True),
        Column("revision", Integer, nullable=False),
    )
    Table(
        "knowledge_index_batches",
        metadata,
        Column("job_id", Text, ForeignKey("knowledge_index_checkpoints.job_id"), primary_key=True),
        Column("start", Integer, primary_key=True),
        Column("payload", Text, nullable=False),
    )


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    schema = MetaData()
    Table("application_versions", schema, Column("id", Text, primary_key=True))
    Table("knowledge_index_checkpoints", schema, Column("job_id", Text, primary_key=True))
    define_index_progress_tables(schema)
    db = op.get_bind()
    for name in ("knowledge_content_revisions", "knowledge_index_batches"):
        table = schema.tables[name]
        inspector = inspect(db)
        if inspector.has_table(name):
            actual = {column["name"] for column in inspector.get_columns(name)}
            if db.dialect.name != "sqlite" or actual != set(table.columns.keys()):
                raise RuntimeError("Existing progress schema does not match migration")
        else:
            table.create(db)
    # Old checkpoints lack monotonic revision binding; discard only derived progress.
    # Final indexes and job leases remain intact; interrupted jobs restart normally.
    from sqlalchemy import text

    db.execute(text("DELETE FROM knowledge_index_batches"))
    db.execute(text("DELETE FROM knowledge_index_checkpoints"))


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
