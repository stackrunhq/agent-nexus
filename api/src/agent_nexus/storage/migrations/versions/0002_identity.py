"""Personal identity tables; frozen revision, no application metadata imports."""

from alembic import op
from sqlalchemy import MetaData, inspect
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Table, Text


def define_identity_tables(metadata):
    Table(
        "users",
        metadata,
        Column("id", Text, primary_key=True),
        Column("username", Text, nullable=False, unique=True),
        Column("password_hash", Text, nullable=False),
        Column("role", Text, nullable=False),
        Column("tenant_id", Text, ForeignKey("tenants.id")),
        Column("enabled", Integer, nullable=False, server_default="1"),
        Column("failed_attempts", Integer, nullable=False, server_default="0"),
        Column("blocked_until", BigInteger, nullable=False, server_default="0"),
    )
    Table(
        "user_sessions",
        metadata,
        Column("key_hash", Text, primary_key=True),
        Column("user_id", Text, ForeignKey("users.id"), nullable=False, index=True),
        Column("expires_at", BigInteger, nullable=False),
    )
    Table(
        "user_events",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", Text, nullable=False),
        Column("actor", Text, nullable=False),
        Column("action", Text, nullable=False),
        Column("created_at", BigInteger, nullable=False),
    )


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    schema = MetaData()
    Table("tenants", schema, Column("id", Text, primary_key=True))
    define_identity_tables(schema)
    db = op.get_bind()
    inspector = inspect(db)
    for table in schema.sorted_tables:
        if table.name == "tenants":
            continue
        if inspector.has_table(table.name):
            actual = {column["name"] for column in inspector.get_columns(table.name)}
            if db.dialect.name != "sqlite" or actual != set(table.columns.keys()):
                raise RuntimeError("Existing identity schema does not match migration")
        else:
            table.create(db)


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade")
