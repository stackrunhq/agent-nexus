from alembic import op
from sqlalchemy import MetaData, inspect
from sqlalchemy import Column, Integer, Table, Text


def define_index_scheduler_tables(metadata):
    Table(
        "knowledge_index_scheduler",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("last_tenant_id", Text, nullable=False),
    )


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    schema = MetaData()
    define_index_scheduler_tables(schema)
    db = op.get_bind()
    table = schema.tables["knowledge_index_scheduler"]
    inspector = inspect(db)
    if inspector.has_table(table.name):
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        if db.dialect.name != "sqlite" or actual != set(table.columns.keys()):
            raise RuntimeError("Existing scheduler schema does not match migration")
    else:
        table.create(db)


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
