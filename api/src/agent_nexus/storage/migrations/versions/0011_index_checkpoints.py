from alembic import op
from sqlalchemy import MetaData, inspect
from sqlalchemy import Column, ForeignKey, Integer, Table, Text


def define_index_checkpoint_tables(metadata):
    Table(
        "knowledge_index_checkpoints",
        metadata,
        Column("job_id", Text, ForeignKey("knowledge_index_jobs.id"), primary_key=True),
        Column("content_revision", Text, nullable=False),
        Column("model_revision", Text, nullable=False),
        Column("dimensions", Integer, nullable=False),
        Column("payload", Text, nullable=False),
    )


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    schema = MetaData()
    Table("knowledge_index_jobs", schema, Column("id", Text, primary_key=True))
    define_index_checkpoint_tables(schema)
    db = op.get_bind()
    table = schema.tables["knowledge_index_checkpoints"]
    inspector = inspect(db)
    if inspector.has_table(table.name):
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        if db.dialect.name != "sqlite" or actual != set(table.columns.keys()):
            raise RuntimeError("Existing checkpoint schema does not match migration")
    else:
        table.create(db)


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
