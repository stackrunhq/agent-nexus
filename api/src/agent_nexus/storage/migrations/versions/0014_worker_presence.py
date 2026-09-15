from alembic import op
from sqlalchemy import MetaData, inspect
from sqlalchemy import Column, Integer, Table, Text


def define_worker_presence_tables(metadata):
    Table(
        "knowledge_index_workers",
        metadata,
        Column("id", Text, primary_key=True),
        Column("strategy", Text, nullable=False),
        Column("last_seen", Integer, nullable=False),
    )


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    schema = MetaData()
    define_worker_presence_tables(schema)
    db = op.get_bind()
    table = schema.tables["knowledge_index_workers"]
    inspector = inspect(db)
    if inspector.has_table(table.name):
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        if db.dialect.name != "sqlite" or actual != set(table.columns.keys()):
            raise RuntimeError("Existing worker presence schema does not match migration")
    else:
        table.create(db)


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
