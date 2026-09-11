from alembic import op
from sqlalchemy import MetaData, inspect
from sqlalchemy import Column, ForeignKey, Integer, Table, Text


def define_model_quota_tables(metadata):
    Table(
        "tenant_model_quotas",
        metadata,
        Column("tenant_id", Text, ForeignKey("tenants.id"), primary_key=True),
        Column("daily_limit", Integer),
    )


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    schema = MetaData()
    Table("tenants", schema, Column("id", Text, primary_key=True))
    define_model_quota_tables(schema)
    db = op.get_bind()
    table = schema.tables["tenant_model_quotas"]
    inspector = inspect(db)
    if inspector.has_table(table.name):
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        if db.dialect.name != "sqlite" or actual != set(table.columns.keys()):
            raise RuntimeError("Existing quota schema does not match migration")
    else:
        table.create(db)


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
